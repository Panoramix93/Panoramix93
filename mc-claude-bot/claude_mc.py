#!/usr/bin/env python3
"""
Bot d'aide ATM10 pour le chat Minecraft.

Lit le chat du serveur dans latest.log, repere les messages qui commencent par
le declencheur (par defaut !claude), interroge l'API Claude et renvoie la
reponse dans le chat par RCON.

Aucune dependance : uniquement la bibliotheque standard de Python 3.
Le bot n'execute aucune commande serveur autre que l'envoi de messages.
"""

import json
import os
import re
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ICI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ICI, "config.json")
ETAT = os.path.join(ICI, "etat.json")
JOURNAL = os.path.join(ICI, "journal.log")
API = "https://api.anthropic.com/v1/messages"


# --------------------------------------------------------------------------
# journal
# --------------------------------------------------------------------------

def log(msg):
    ligne = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(ligne, flush=True)
    try:
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# configuration et etat
# --------------------------------------------------------------------------

def charger_config():
    with open(CONFIG, encoding="utf-8") as f:
        c = json.load(f)
    cle = c.get("fichier_cle_api") or os.path.join(ICI, "cle_api")
    if not os.path.isabs(cle):
        cle = os.path.join(ICI, cle)
    with open(cle, encoding="utf-8") as f:
        c["cle_api"] = f.read().strip()
    if not c["cle_api"]:
        raise SystemExit(f"La cle API est vide. Mets-la dans {cle}")
    fiche = c.get("fichier_connaissances") or "atm10.md"
    if not os.path.isabs(fiche):
        fiche = os.path.join(ICI, fiche)
    c["connaissances"] = ""
    if os.path.exists(fiche):
        with open(fiche, encoding="utf-8") as f:
            c["connaissances"] = f.read()
    else:
        log(f"ATTENTION : fiche de connaissances absente ({fiche}), "
            "le bot repondra sans contexte ATM10.")
    return c


def jour():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def charger_etat():
    if os.path.exists(ETAT):
        try:
            with open(ETAT, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError):
            e = {}
    else:
        e = {}
    if e.get("jour") != jour():
        e = {"jour": jour(), "par_joueur": {}, "cout_usd": 0.0, "questions": 0}
    e.setdefault("par_joueur", {})
    e.setdefault("cout_usd", 0.0)
    e.setdefault("questions", 0)
    e.setdefault("dernier_appel", {})
    return e


def ecrire_etat(e):
    tmp = ETAT + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ETAT)
    except OSError as exc:
        log(f"Impossible d'ecrire l'etat : {exc}")


# --------------------------------------------------------------------------
# RCON
# --------------------------------------------------------------------------

class Rcon:
    """Client RCON minimal (protocole Source)."""

    AUTH = 3
    COMMANDE = 2

    def __init__(self, hote, port, mot_de_passe, timeout=10):
        self.hote, self.port = hote, port
        self.mdp = mot_de_passe
        self.timeout = timeout
        self.s = None
        self.id = 0

    def connecter(self):
        self.fermer()
        self.s = socket.create_connection((self.hote, self.port), self.timeout)
        self.s.settimeout(self.timeout)
        rid, _ = self._aller_retour(self.AUTH, self.mdp)
        if rid == -1:
            self.fermer()
            raise RuntimeError("RCON : mot de passe refuse")

    def fermer(self):
        if self.s:
            try:
                self.s.close()
            except OSError:
                pass
        self.s = None

    def _envoyer(self, type_, corps):
        self.id += 1
        donnees = corps.encode("utf-8") + b"\x00\x00"
        paquet = struct.pack("<ii", self.id, type_) + donnees
        self.s.sendall(struct.pack("<i", len(paquet)) + paquet)
        return self.id

    def _lire_exact(self, n):
        buf = b""
        while len(buf) < n:
            bout = self.s.recv(n - len(buf))
            if not bout:
                raise ConnectionError("RCON : connexion fermee")
            buf += bout
        return buf

    def _aller_retour(self, type_, corps):
        self._envoyer(type_, corps)
        taille = struct.unpack("<i", self._lire_exact(4))[0]
        charge = self._lire_exact(taille)
        rid, _rtype = struct.unpack("<ii", charge[:8])
        return rid, charge[8:-2].decode("utf-8", "replace")

    def commande(self, texte):
        if self.s is None:
            self.connecter()
        try:
            return self._aller_retour(self.COMMANDE, texte)[1]
        except (OSError, ConnectionError, struct.error):
            # une reconnexion, une seule
            self.connecter()
            return self._aller_retour(self.COMMANDE, texte)[1]


def echapper_json_mc(texte, couleur):
    return json.dumps({"text": texte, "color": couleur}, ensure_ascii=False)


def dire(rcon, texte, couleur, destinataire="@a"):
    """Envoie du texte dans le chat, decoupe en lignes raisonnables."""
    for ligne in decouper(texte, 220):
        rcon.commande(f"tellraw {destinataire} {echapper_json_mc(ligne, couleur)}")


def decouper(texte, taille):
    """Decoupe sur les espaces, sans casser les mots."""
    sorties = []
    for paragraphe in texte.split("\n"):
        paragraphe = paragraphe.strip()
        if not paragraphe:
            continue
        courant = ""
        for mot in paragraphe.split(" "):
            if len(courant) + len(mot) + 1 > taille:
                if courant:
                    sorties.append(courant)
                courant = mot
            else:
                courant = f"{courant} {mot}".strip()
        if courant:
            sorties.append(courant)
    return sorties or [texte[:taille]]


# --------------------------------------------------------------------------
# API Claude
# --------------------------------------------------------------------------

def demander_a_claude(cfg, question, pseudo):
    consigne = (
        "Tu es un assistant de jeu pour un serveur Minecraft prive qui tourne "
        "sur le modpack All the Mods 10 (ATM10), en version 1.21.1.\n\n"
        "Regles :\n"
        "- Reponds TOUJOURS en francais, en tutoyant le joueur.\n"
        "- Sois tres bref : 3 phrases maximum. Le texte s'affiche dans le chat "
        "du jeu, personne ne lit un pave.\n"
        "- Tu ne reponds QU'AUX questions de jeu : recettes, objets, machines, "
        "dimensions, ou trouver quoi, comment progresser.\n"
        "- Si on te demande quelque chose sur le serveur lui-meme (lag, "
        "redemarrage, plantage, sauvegardes, qui est admin, droits, plaintes "
        "entre joueurs), reponds exactement : \"Ca c'est pour Adel, pas pour "
        "moi.\" et rien d'autre.\n"
        "- Si on te demande d'executer une commande, de donner des objets ou "
        "de modifier le monde, refuse : tu ne peux que parler.\n"
        "- Si tu n'es pas sur, DIS-LE. Une mauvaise reponse confiante fait "
        "perdre une soiree a creuser au mauvais endroit. Mieux vaut \"je ne "
        "suis pas sur, verifie dans JEI\" qu'une invention.\n"
        "- La fiche ci-dessous prime sur tes souvenirs : elle corrige des "
        "erreurs connues du livre en jeu et du wiki.\n"
    )
    if cfg["connaissances"]:
        consigne += "\n--- FICHE ATM10 ---\n" + cfg["connaissances"]

    corps = {
        "model": cfg["modele"],
        "max_tokens": int(cfg["max_tokens_reponse"]),
        "system": consigne,
        "messages": [{"role": "user", "content": f"[{pseudo}] {question}"}],
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(corps).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": cfg["cle_api"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.get("timeout_api", 45)) as r:
        rep = json.loads(r.read().decode("utf-8"))

    # On prend tout bloc qui porte du texte, quel que soit son type : selon le
    # modele la reponse peut contenir des blocs de reflexion avant le texte.
    blocs = rep.get("content", [])
    texte = "".join(b.get("text", "") for b in blocs if isinstance(b, dict)).strip()
    u = rep.get("usage", {})

    if not texte:
        # On veut savoir POURQUOI c'est vide, pas juste que ca l'est.
        types = [b.get("type") for b in blocs if isinstance(b, dict)]
        log(f"REPONSE VIDE | stop_reason={rep.get('stop_reason')} | "
            f"blocs={types} | modele={rep.get('model')} | "
            f"tokens={u.get('input_tokens')}+{u.get('output_tokens')}")
        log(f"REPONSE VIDE (brut) : {json.dumps(rep, ensure_ascii=False)[:600]}")

    return texte, u.get("input_tokens", 0), u.get("output_tokens", 0)


def cout(cfg, entree, sortie):
    t = cfg["tarif_usd_par_million"]
    return entree / 1e6 * t["entree"] + sortie / 1e6 * t["sortie"]


# --------------------------------------------------------------------------
# lecture du chat
# --------------------------------------------------------------------------

# [20:13:44] [Server thread/INFO] [minecraft/MinecraftServer]: <Pseudo> message
CHAT = re.compile(r"\]: <([A-Za-z0-9_]{1,16})> (.+)$")


def suivre(chemin):
    """Generateur de lignes, qui survit a la rotation du fichier."""
    f = None
    inode = None
    while True:
        try:
            if f is None:
                f = open(chemin, "r", encoding="utf-8", errors="replace")
                f.seek(0, os.SEEK_END)
                inode = os.fstat(f.fileno()).st_ino
                log(f"Lecture du chat : {chemin}")
            ligne = f.readline()
            if ligne:
                yield ligne.rstrip("\n")
                continue
            # rien de neuf : le fichier a-t-il tourne ?
            try:
                if os.stat(chemin).st_ino != inode:
                    log("Le fichier de log a tourne, reouverture.")
                    f.close()
                    f = None
                    continue
            except FileNotFoundError:
                f.close()
                f = None
                time.sleep(2)
                continue
            time.sleep(0.4)
        except OSError as exc:
            log(f"Lecture impossible ({exc}), nouvel essai dans 5 s.")
            if f:
                f.close()
            f = None
            time.sleep(5)


# --------------------------------------------------------------------------
# boucle principale
# --------------------------------------------------------------------------

def main():
    cfg = charger_config()
    rcon = Rcon(cfg["rcon"]["hote"], int(cfg["rcon"]["port"]), cfg["rcon"]["mot_de_passe"])
    declencheur = cfg["declencheur"].lower()
    autorises = {p.lower() for p in cfg["joueurs_autorises"]}
    ouvert_a_tous = bool(cfg.get("ouvert_a_tous", False))

    log(f"Demarrage. Declencheur « {declencheur} », modele {cfg['modele']}.")
    log(f"Autorises : {'tout le monde' if ouvert_a_tous else ', '.join(sorted(autorises)) or 'personne'}")

    for ligne in suivre(cfg["fichier_log"]):
        m = CHAT.search(ligne)
        if not m:
            continue
        pseudo, message = m.group(1), m.group(2).strip()
        if not message.lower().startswith(declencheur):
            continue
        question = message[len(declencheur):].strip()

        etat = charger_etat()

        if cfg.get("en_pause"):
            continue

        if not ouvert_a_tous and pseudo.lower() not in autorises:
            dire(rcon, "Tu n'es pas sur la liste. Demande a Adel.", "gray", pseudo)
            log(f"REFUS liste blanche : {pseudo}")
            continue

        if not question:
            dire(rcon, f"Pose ta question apres {cfg['declencheur']}.", "gray", pseudo)
            continue

        if len(question) > int(cfg["longueur_max_question"]):
            dire(rcon, "Question trop longue, fais plus court.", "gray", pseudo)
            continue

        maintenant = time.time()
        dernier = etat["dernier_appel"].get(pseudo.lower(), 0)
        attente = int(cfg["delai_entre_questions_s"])
        if maintenant - dernier < attente:
            reste = int(attente - (maintenant - dernier)) + 1
            dire(rcon, f"Doucement, encore {reste} s.", "gray", pseudo)
            continue

        utilise = etat["par_joueur"].get(pseudo.lower(), 0)
        if utilise >= int(cfg["questions_par_joueur_par_jour"]):
            dire(rcon, "Tu as atteint ton quota du jour. Demain.", "gray", pseudo)
            log(f"QUOTA ATTEINT : {pseudo}")
            continue

        if etat["cout_usd"] >= float(cfg["plafond_usd_par_jour"]):
            dire(rcon, "Plafond du jour atteint, le bot dort jusqu'a demain.", "gray", pseudo)
            log("PLAFOND JOURNALIER ATTEINT")
            continue

        # tout est bon, on appelle
        try:
            reponse, e_in, e_out = demander_a_claude(cfg, question, pseudo)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            log(f"ERREUR API {exc.code} : {detail}")
            dire(rcon, "Je n'arrive pas a repondre la tout de suite.", "gray", pseudo)
            continue
        except Exception as exc:  # reseau, timeout, json
            log(f"ERREUR appel : {exc!r}")
            dire(rcon, "Je n'arrive pas a repondre la tout de suite.", "gray", pseudo)
            continue

        if not reponse:
            dire(rcon, "Je n'ai pas reussi a repondre, Adel a les details.",
                 "gray", pseudo)
            continue

        c = cout(cfg, e_in, e_out)
        etat["par_joueur"][pseudo.lower()] = utilise + 1
        etat["dernier_appel"][pseudo.lower()] = maintenant
        etat["cout_usd"] = round(etat["cout_usd"] + c, 6)
        etat["questions"] += 1
        ecrire_etat(etat)

        prive = bool(cfg.get("reponse_privee", False))
        try:
            if not prive:
                dire(rcon, f"<{pseudo}> {question}", "dark_gray")
            dire(rcon, reponse, cfg.get("couleur_reponse", "aqua"),
                 pseudo if prive else "@a")
        except Exception as exc:
            log(f"ERREUR RCON : {exc!r}")
            continue

        log(f"{pseudo} | {e_in}+{e_out} tok | {c*100:.4f} ct | "
            f"jour {etat['questions']} q / {etat['cout_usd']*100:.2f} ct | {question[:80]}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Arret demande.")
        sys.exit(0)
