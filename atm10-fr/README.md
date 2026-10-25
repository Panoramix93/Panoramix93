# Traduction française ATM10

## Les fichiers

- **`ATM10-Francais.zip`** — pack de ressources. Traduit les noms d'objets et de
  blocs, les infobulles, les interfaces, les configs, ainsi que les guides lus
  en jeu : les 26 livres Patchouli, le guide AE2 et ses add-ons, le Manuel de
  l'ingénieur d'Immersive Engineering et le bestiaire d'Ice and Fire.
  À poser côté client, ou mieux : distribué automatiquement par le serveur via
  `server-resource-pack`.

- **`ATM10-quetes-fr.zip`** — traduction des quêtes FTB Quests.
  Côté serveur, à décompresser dans `config/ftbquests/quests/lang/`.

- **`ATM10-infobulles-fr.zip`** — deux scripts KubeJS côté client
  (`kubejs/client_scripts/`). Ce sont des scripts, pas des ressources : ils ne
  peuvent pas voyager dans le pack de ressources, chaque joueur doit les copier
  dans son instance. Une mise à jour du modpack les remet en anglais.

## Configuration serveur

Dans `server.properties` :

```properties
resource-pack=https://raw.githubusercontent.com/Panoramix93/Panoramix93/main/atm10-fr/ATM10-Francais.zip
resource-pack-sha1=373b95b07d6c40e8768d4d9adb8cb3de25cb8ccb
require-resource-pack=false
```

Le SHA1 doit être mis à jour à chaque fois que le zip change, sinon les clients
qui ont déjà l'ancienne version ne retéléchargeront pas.

## Ce que ça couvre

| | |
|---|---|
| Fichiers de langue des mods | 348 fichiers, 140 189 clés |
| Livres Patchouli | 26 livres, 1 474 fichiers |
| Guide AE2 et add-ons | 223 pages |
| Manuel de l'ingénieur (IE) | 114 pages |
| Bestiaire (Ice and Fire) | 80 pages |

Taille du pack : 3,48 Mo — `pack_format` 34 (Minecraft 1.21.1).

## Ce qui reste en anglais

- Le **titre et la page de garde de 17 livres Patchouli** (« Big Book of Bees »,
  « The Extreme Book »…). Patchouli lit ces deux champs directement dans le jar
  du mod : ni un pack de ressources ni un datapack ne peuvent les remplacer.
- L'**aide des ordinateurs ComputerCraft** (199 fichiers), qui vit dans `data/`
  et non dans les ressources.
