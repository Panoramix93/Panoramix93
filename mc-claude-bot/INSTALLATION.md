# Bot d'aide ATM10 — installation

Un bot qui répond aux questions de jeu dans le chat Minecraft. Il lit le chat
dans `latest.log`, interroge l'API Claude, et répond par RCON.

Il ne peut **rien faire d'autre que parler** : aucune commande, aucun objet
donné, aucune modification du monde. Si on lui pose une question sur le serveur
lui-même, il renvoie vers toi.

Zéro dépendance : uniquement Python 3, déjà présent.

---

## Avant de commencer

Les sauvegardes du conteneur Minecraft doivent fonctionner. Ce bot demande un
redémarrage du serveur, et on ne redémarre pas un serveur sans filet.

---

## 1. Activer RCON sur le serveur Minecraft

Dans le conteneur du serveur (`pct enter 100`), édite
`/opt/atm10/server.properties` et mets ces trois lignes :

```properties
enable-rcon=true
rcon.port=25575
rcon.password=CHOISIS_UN_MOT_DE_PASSE_ICI
```

Choisis un vrai mot de passe, pas `minecraft`. RCON donne un accès complet aux
commandes du serveur.

Profites-en pour faire le changement de pack de ressources dans le même
redémarrage :

```properties
resource-pack-sha1=373b95b07d6c40e8768d4d9adb8cb3de25cb8ccb
```

Puis redémarre le serveur Minecraft.

**Vérifie que RCON n'écoute que sur la machine locale.** Si le bot tourne dans le
même conteneur, c'est le cas par défaut et il n'y a rien à faire. S'il tourne
ailleurs, n'ouvre pas le port 25575 sur le réseau sans y réfléchir.

---

## 2. Installer le bot

Le plus simple est de le mettre dans le même conteneur que le serveur
Minecraft : il y lit le log directement et parle à RCON en local.

```bash
# dans le conteneur 100
mkdir -p /opt/claude-mc
cd /opt/claude-mc
# copie ici claude_mc.py, config.json, atm10.md, claude-mc.service
```

Crée l'utilisateur dédié et pose les droits :

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin claudemc
chown -R claudemc:claudemc /opt/claude-mc
chmod 750 /opt/claude-mc
```

L'utilisateur `claudemc` doit pouvoir **lire** le log du serveur :

```bash
chmod o+rx /opt/atm10 /opt/atm10/logs
chmod o+r /opt/atm10/logs/latest.log
```

---

## 3. La clé API

Va sur [console.anthropic.com](https://console.anthropic.com), crée une clé API,
et charge quelques euros de crédit prépayé. C'est **séparé de ton abonnement
Claude** : le crédit s'épuise et s'arrête, il n'y a pas de prélèvement surprise.

Sur le serveur :

```bash
echo 'sk-ant-TA-CLE-ICI' > /opt/claude-mc/cle_api
chown claudemc:claudemc /opt/claude-mc/cle_api
chmod 600 /opt/claude-mc/cle_api
```

La clé n'est jamais dans le script ni dans la config, uniquement dans ce fichier.

---

## 4. Régler la config

Dans `/opt/claude-mc/config.json`, les seules lignes à changer pour démarrer :

| Clé | À mettre |
|---|---|
| `rcon.mot_de_passe` | le mot de passe choisi à l'étape 1 |
| `joueurs_autorises` | ton pseudo, seul, pour les premiers essais |
| `fichier_log` | le chemin du `latest.log` si ce n'est pas `/opt/atm10/logs/latest.log` |

Les garde-fous, déjà réglés prudemment :

| Clé | Défaut | Ce que ça fait |
|---|---|---|
| `questions_par_joueur_par_jour` | 20 | quota individuel, remis à zéro à minuit UTC |
| `plafond_usd_par_jour` | 0,25 $ | au-delà, le bot dort jusqu'au lendemain |
| `delai_entre_questions_s` | 20 | anti-spam, par joueur |
| `max_tokens_reponse` | 300 | plafonne la longueur, donc le coût |
| `longueur_max_question` | 256 | la limite du chat Minecraft de toute façon |
| `en_pause` | false | mets `true` et redémarre pour tout couper |

---

## 5. Lancer

```bash
cp /opt/claude-mc/claude-mc.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now claude-mc
systemctl status claude-mc
```

Premier essai : connecte-toi au jeu et écris dans le chat

```
!claude ou je trouve l'allthemodium
```

Il doit répondre en français en trois phrases.

---

## Au quotidien

**Voir ce qui se passe :**

```bash
journalctl -u claude-mc -f
```

**Voir les questions posées et ce qu'elles ont coûté :**

```bash
tail -20 /opt/claude-mc/journal.log
```

Chaque ligne donne le pseudo, les tokens, le coût de la question en centimes, et
le total de la journée.

**Voir où en est la journée :**

```bash
cat /opt/claude-mc/etat.json
```

**Ouvrir aux copains :** ajoute leurs pseudos dans `joueurs_autorises`, ou passe
`ouvert_a_tous` à `true`. Puis `systemctl restart claude-mc`.

**Tout arrêter :**

```bash
systemctl stop claude-mc
```

---

## Si ça ne marche pas

**Il ne répond à rien.** Regarde `journalctl -u claude-mc -f` pendant que tu
écris dans le chat. Si rien n'apparaît, c'est qu'il ne lit pas le bon fichier :
vérifie `fichier_log` et les droits de lecture.

**« RCON : mot de passe refuse ».** Le mot de passe de `config.json` ne
correspond pas à celui de `server.properties`, ou le serveur n'a pas été
redémarré depuis que RCON a été activé.

**« ERREUR API 401 ».** La clé est mauvaise ou le fichier `cle_api` contient
autre chose que la clé (un retour à la ligne en trop est sans importance, un
espace au début non).

**« ERREUR API 400 ».** Le nom du modèle dans `config.json` n'existe pas ou
n'est plus disponible. Vérifie sur console.anthropic.com.

**Il répond mais en anglais.** La fiche `atm10.md` n'est pas lue : vérifie que
le fichier est bien dans `/opt/claude-mc/` et lisible par `claudemc`.

---

## Faire évoluer la fiche

`atm10.md` est ce qui rend le bot utile plutôt que générique. Quand vous
découvrez quelque chose que le wiki dit faux, ajoute-le dedans et redémarre le
service. C'est le fichier qui mérite d'être enrichi avec le temps, pas le code.
