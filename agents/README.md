# Système Multi-Agents Cinématographique — LangChain

Un pipeline de production de films automatisé avec 8 agents IA spécialisés.

## Architecture

```
Votre idée
    │
    ▼
[Agent 01 - Directeur]          → Vision artistique, genre, ton
    │
    ▼
[Agent 02 - Architecte Narratif] → Synopsis, structure en actes, scènes clés
    │
    ▼
[Agent 03 - Scénariste]         → Dialogues, fiches personnages, extrait scénario
    │
    ▼
[Agent 04 - Dir. Artistique]    → Script Python pour Blender (.py) ← sauvegardé dans output/
    │
    ▼
[Agent 05 - Dir. Technique]     → Script Shell pour Unreal Engine (.sh) ← sauvegardé dans output/
    │
    ▼
  [Agent 06 - Superviseur Post-Prod] → Audit de conformité, outils conditionnels
    │
    ▼
  [Agent 07 - Exporteur Multi-Format] → Script FFmpeg multi-format (.sh) ← sauvegardé dans output/
  [Agent 08 - Ingénieur du Son]      → Bande son Csound (.csd) ← sauvegardée dans output/
    │
    ▼
  output/
    ├── rapport_production_YYYYMMDD_HHMMSS.md
    ├── state_YYYYMMDD_HHMMSS.json
    ├── scene_01_opening.py       (script Blender)
    ├── setup_scene_01.sh         (script Unreal)
    ├── retouche_gimp.py          (script GIMP, si nécessaire)
    ├── concept_krita.py          (script Krita, si nécessaire)
    ├── export_multi_format.sh    (script FFmpeg)
    ├── bande_son.csd             (bande son Csound, rendue en audio par csound)
    └── notes_*.txt               (instructions optionnelles)
```

## Installation

```bash
cd agents/
pip install -r requirements.txt
```

## Configuration

```bash
# Copiez le fichier exemple
cp .env.example .env

# Éditez .env et ajoutez votre clé OpenAI
# OPENAI_API_KEY=sk-votre-clé-ici
```

## Utilisation

```bash
cd agents/

# Avec l'idée par défaut
python main.py

# Avec votre propre idée
python main.py --idea "Un détective robot enquête dans une ville néon sous la pluie"

# Avec un modèle plus puissant
python main.py --model gpt-4o --idea "Un moine shaolin découvre que son temple est une simulation"

# Reprendre une production interrompue (saute les étapes déjà complétées)
python main.py --reprendre

# Mode Human-in-the-loop : valider, réviser ou arrêter à chaque étape créative
python main.py --interactif

# Exécuter Blender / Unreal / FFmpeg sur une machine de rendu distante
python main.py --reprendre --worker http://192.168.1.50:8765 --worker-jeton JETON

# Laisser le studio lancer LUI-MÊME les rendus sur CETTE machine (headless)
python main.py --reprendre --local
```

En cas d'échec d'une étape critique (Agents 01 à 05), l'état partiel est
sauvegardé automatiquement : corrigez le problème puis relancez avec
`--reprendre` pour continuer là où la production s'était arrêtée. Sans
`--reprendre`, chaque lancement démarre une production vierge (l'état
précédent est écrasé — jamais de mélange entre deux productions). Chaque
appel LLM est retenté une fois automatiquement avant de déclarer l'échec.
Les Agents 06, 07 et 08 sont optionnels : leur échec n'arrête jamais le pipeline
(et leurs sorties sont alors réinitialisées pour ne jamais afficher de
données d'une production précédente).

### Human-in-the-loop (`--interactif`)

Avec `--interactif`, la production s'arrête après chaque étape créative
(Agents 01 à 05) pour vous laisser la main :

| Choix | Effet |
|---|---|
| `[Entrée]` | Valider le résultat et continuer la production |
| `r` | Demander une révision — vos directives sont réinjectées dans l'entrée de l'agent, qui régénère une nouvelle version |
| `q` | Arrêter proprement — l'état est sauvegardé, reprise avec `--reprendre --interactif` |

Les directives de révision s'accumulent (l'agent voit toutes vos remarques
précédentes) et une révision qui échoue ne casse rien : le résultat précédent
reste en vigueur. Sans terminal interactif (pipe, CI), les validations sont
acceptées automatiquement.

### Exécution locale automatique (`--local`)

Par défaut, les agents *génèrent* les scripts sans jamais les exécuter :
c'est à vous (ou au worker distant) de lancer les rendus. Avec `--local`, le
studio lance lui-même les logiciels installés sur cette machine, en mode
headless — l'agent « ouvre » réellement le logiciel et produit le fichier
final, sans intervention :

```bash
# Produire d'abord, puis laisser le studio rendre tout seul
python main.py --idea "..."
python main.py --reprendre --local
```

Les mêmes étapes optionnelles que le worker s'ajoutent, mais seulement pour
les outils réellement installés ici (détectés via `which`) : le cas d'usage
principal est **Csound** pour la bande son (`bande_son.csd` → `bande_son.wav`),
et Blender/FFmpeg s'ils sont présents. Les fichiers et journaux atterrissent
dans `agents/output/rendus_local/<outil>/`. Un rendu qui échoue n'invalide
jamais la production (journal complet conservé pour diagnostic).

> ⚠️ **Sécurité — à comprendre avant d'utiliser `--local`.** Exécuter en
> local un script Blender (`.py`) ou Unreal/FFmpeg (`.sh`) *généré par IA*,
> c'est exécuter du code arbitraire sur votre propre machine. Csound (`.csd`,
> langage de synthèse musicale) est nettement moins risqué. Les mêmes
> garde-fous que le worker s'appliquent : liste blanche stricte des outils,
> commande construite par le studio (jamais par l'IA) et exécutée sans shell,
> nom de fichier assaini, dossier isolé, délai maximal. `--local` et
> `--worker` sont mutuellement exclusifs.

### Exécution distante sur un worker (`--worker`)

Le studio génère les scripts, mais la machine qui les exécute (Blender,
Unreal Engine, FFmpeg) est rarement la même. Le worker fait le pont.

**Sur la machine de rendu** — un seul fichier à copier, aucune dépendance :

```bash
python3 worker_distant.py --hote 0.0.0.0 --port 8765 --blender /chemin/vers/blender
```

Le worker affiche son jeton d'accès au démarrage (ou fixez-le vous-même :
variable `WORKER_JETON` ou option `--jeton`).

**Côté studio** :

```bash
# Production complète puis rendu distant dans la foulée
python main.py --idea "..." --worker http://IP:8765 --worker-jeton JETON

# Ou : produire d'abord, rendre ensuite (recommandé)
python main.py --idea "..."
python main.py --reprendre --worker http://IP:8765 --worker-jeton JETON
```

Le jeton peut aussi être placé dans `.env` (`WORKER_JETON=...`). La
connexion au worker est vérifiée avant de lancer le pipeline : machine
injoignable = arrêt immédiat, aucun appel LLM consommé.

Trois étapes optionnelles s'ajoutent alors au pipeline, uniquement pour les
outils que le worker déclare disponibles :

| Étape | Script envoyé | Exécution sur le worker |
|---|---|---|
| Rendu Blender | `output/scene_*.py` | `blender --background --python ...` |
| Setup Unreal | `output/setup_*.sh` | `bash ...` (nécessite UE5 installé sur le worker) |
| Exports FFmpeg | `output/export_multi_format.sh` | `bash ...` — chaîné dans le dossier du rendu Blender pour y retrouver la vidéo master |
| Rendu bande son | `output/bande_son.csd` | `csound bande_son.csd -o bande_son.wav` (nécessite Csound installé sur le worker) |

Chaque travail s'exécute dans un dossier isolé sur le worker ; les journaux
et les fichiers produits sont rapatriés en flux — sans limite de taille,
même pour des vidéos de plusieurs Go — dans `agents/output/rendus/<outil>/`.
Un rendu qui échoue n'invalide jamais la production : le journal complet est
rapatrié pour diagnostic, et `--reprendre --worker ...` ne relance que les
rendus manquants.

Sécurité : jeton obligatoire (en-tête `X-Jeton`), lanceurs limités aux trois
outils du studio, un seul travail à la fois, écoute locale par défaut
(`127.0.0.1`). À bien comprendre avant d'exposer le worker : sa fonction est
d'exécuter les scripts qu'on lui envoie — posséder le jeton équivaut donc à
pouvoir exécuter du code sur la machine de rendu. Traitez le jeton comme un
mot de passe SSH (secret, jamais commité, régénéré au moindre doute) et
n'exposez le worker (`--hote 0.0.0.0`) que sur un réseau de confiance,
derrière un pare-feu ou un tunnel SSH.

## Historique et journaux (base de données + logs structurés)

Chaque exécution est tracée automatiquement, sans configuration, dans deux
supports complémentaires :

- **Base SQLite `output/studio.db`** — historique interrogeable : productions,
  étapes (statut, durée, révisions), événements. C'est la matière des futures
  interfaces web et Android (tableau de bord, rapports).
- **Journal structuré `output/journaux/<id>.jsonl`** — un événement JSON par
  ligne (démarrage, étape démarrée/réussie/ignorée/échouée, révision, fin).
  Facile à suivre en direct (`tail -f`) ou à consommer par une interface.

```bash
python main.py --historique          # liste les dernières productions puis quitte
python main.py --lister-projets      # liste les projets (films/séries) puis quitte
```

### Dossiers par projet et écriture d'une suite

Par défaut, tout va dans `output/`. L'option `--projet` range plutôt le film
dans son **propre dossier** `output/projets/<nom>/` : scripts générés,
`meta.json` (nom, dates) et `world_state.json` (la « bible » créative archivée en
fin de production). Le reste (historique `studio.db`, comptes, objectifs, canal
de pilotage) demeure partagé.

Pour écrire une **suite**, `--inspiration` (alias `--suite-de`) réutilise l'état
archivé d'un projet existant comme référence (univers, personnages, ton) injectée
aux agents :

```bash
# Saison 1 — rangée dans son propre dossier
python main.py --projet "Alien" --idea "Un équipage réveillé face à une créature"

# Saison 2 — inspirée de la saison 1
python main.py --projet "Alien 2" --inspiration "Alien" \
  --idea "Cinquante ans plus tard, une colonie perd le contact"
```

`--inspiration` **échoue franchement** si le projet source est absent ou n'a pas
encore d'état créatif (on ne produit jamais une fausse « suite »), et il est
incompatible avec `--reprendre`.

Une reprise (`--reprendre`) réutilise le même identifiant de production : ses
nouvelles étapes s'ajoutent à l'historique existant au lieu d'en créer un
nouveau. La journalisation ne peut jamais interrompre une production : si la
base ou le fichier de log est indisponible, le studio le signale une fois et
continue sans traces.

## Comptes et sécurité (authentification)

Fondation d'authentification — la brique qui permet à l'API (voir plus bas) puis
aux interfaces web/Android de savoir **qui** a le droit de commander le studio.
Tout est en bibliothèque standard (aucune dépendance) et stocké dans une base
dédiée `output/securite.db`, séparée de l'historique créatif.

- **Mots de passe jamais en clair** : hachage pbkdf2-hmac-sha256 avec sel
  aléatoire par utilisateur.
- **Trois rôles** : `admin` (tout, y compris gérer les comptes), `operateur`
  (lancer et piloter des productions), `observateur` (lecture seule).
- **Jetons de session signés et autonomes** : à la connexion, un jeton signé
  (via le secret `SESSION_SECRET`) contient l'utilisateur, son rôle et une date
  d'expiration. Un service peut le vérifier avec la seule clé de signature, sans
  interroger la base. Révocables.

```bash
python main.py --creer-utilisateur alice --role admin   # mot de passe demandé au clavier
python main.py --lister-utilisateurs
python main.py --connexion alice                        # affiche un jeton de session
python main.py --changer-mdp alice
python main.py --definir-role alice --role operateur
python main.py --supprimer-utilisateur alice
```

> Les mots de passe sont toujours saisis au clavier (masqués), jamais passés en
> argument (sinon ils resteraient dans l'historique du shell). Ces commandes
> s'exécutent puis quittent, sans lancer de production. La CLI locale n'exige pas
> de connexion ; ce sont **l'API et les interfaces** qui activent ces contrôles.
>
> Principe : le module **échoue fermé** — toute vérification qui ne peut pas
> aboutir (base indisponible, signature invalide, jeton expiré ou révoqué)
> refuse l'accès. On ne laisse jamais un doute autoriser quelqu'un.

## API HTTP (`api_serveur.py`)

L'API met en service l'authentification ci-dessus : elle expose le studio
par-dessus HTTP pour les futures interfaces (web, Android, bureau). Tout est en
bibliothèque standard (aucune dépendance), comme le worker et le journal.

```bash
# Prérequis : au moins un compte (voir ci-dessus) et le secret SESSION_SECRET.
python api_serveur.py --hote 0.0.0.0 --port 8000
```

| Méthode & route | Permission | Rôle |
|---|---|---|
| `GET /sante` | publique | Vérifier que l'API répond |
| `POST /connexion` | publique | `{nom, mot_de_passe}` → `{jeton, role, expire_dans_s}` |
| `POST /deconnexion` | jeton valide | Révoque le jeton présenté |
| `GET /productions` | `consulter` | Historique des productions |
| `GET /productions/<id>` | `consulter` | Détail : étapes + événements |
| `GET /projets` | `consulter` | Liste des projets (films/séries) + état archivé |
| `POST /productions` | `lancer_production` | `{idee, modele?, projet?, inspiration?}` → `202 {id}` (`404` si `inspiration` introuvable) |
| `POST /productions/<id>/pause` | `piloter_production` | Mettre en pause à distance |
| `POST /productions/<id>/reprendre` | `piloter_production` | Reprendre une production en pause |
| `POST /productions/<id>/arreter` | `piloter_production` | Arrêter proprement (reprise possible via `--reprendre`) |
| `GET /agents` | `consulter` | Catalogue des agents + état d'activation |
| `POST /agents/<numero>` | `gerer_utilisateurs` | `{actif}` — activer/désactiver un agent **optionnel** |
| `GET /objectifs` | `consulter` | Note d'objectifs persistants |
| `POST /objectifs` | `piloter_production` | `{texte}` — objectifs injectés aux futures productions |
| `GET /memoire` | `consulter` | Objectifs + résumé de l'état de travail |
| `POST /memoire/reset` | `gerer_utilisateurs` | Efface l'état de travail (refusé si une prod tourne) |
| `POST /chat` | `piloter_production` | `{agent, message}` → `{reponse}` (discussion hors production) |

Toutes les routes (sauf `/sante` et `/connexion`) exigent l'en-tête
`Authorization: Bearer <jeton>`.

> **Pilotage à distance (pause / reprise / arrêt).** L'orchestrateur consulte un
> petit **fichier de commande** (`output/controle/<id>.json`) au début de chaque
> étape : une commande prend donc effet **à la fin de l'étape en cours**, pas
> instantanément. La lecture « échoue sûr » — un fichier illisible n'interrompt
> jamais une production. Les agents **1 à 5** (chaîne créative) sont
> indispensables et ne peuvent pas être désactivés ; seuls **6, 7 et 8** le sont.

```bash
# 1) Se connecter et récupérer un jeton
JETON=$(curl -s -X POST http://localhost:8000/connexion \
        -d '{"nom":"alice","mot_de_passe":"..."}' | python -c 'import sys,json;print(json.load(sys.stdin)["jeton"])')

# 2) Lancer une production (renvoie l'identifiant immédiatement)
curl -X POST http://localhost:8000/productions \
     -H "Authorization: Bearer $JETON" \
     -d '{"idee":"Un détective robot dans une ville néon"}'

# 3) Suivre l'avancement
curl -H "Authorization: Bearer $JETON" http://localhost:8000/productions/<id>
```

> **Lancement asynchrone.** Produire un film dure plusieurs minutes ; l'API ne
> bloque pas. Elle génère l'identifiant, démarre `main.py --production-id <id>`
> **en arrière-plan** et répond aussitôt (`202`). Le client suit ensuite via
> `GET /productions/<id>`, qui lit le journal alimenté par le sous-processus. La
> sortie du lancement est journalisée dans `output/lancements_api/<id>.log`.
>
> **Jamais de 500 pour un problème de sécurité** : jeton absent/invalide → `401`,
> rôle insuffisant → `403`. Toute `ErreurSecurite` est convertie en réponse
> propre. L'API refuse de démarrer si `SESSION_SECRET` est absent (échoue fermé).
> Note : le sous-processus de production a besoin des dépendances du pipeline
> (langchain…) installées ; l'API et l'authentification, elles, n'en ont pas.

## Application mobile (PWA — étape 9) + APK Android

Une **télécommande mobile** (Progressive Web App) servie directement par l'API :
aucun magasin d'applications, aucune dépendance. Elle permet, depuis un
téléphone Android, de se connecter, lancer une production et suivre son
avancement (étapes + journal de l'orchestrateur). Pour les rôles habilités, elle
ajoute le **pilotage à distance** (pause / reprise / arrêt), la **gestion des
agents** optionnels, les **objectifs & mémoire** et un **chat** avec un agent.

```bash
# Exposer l'API au réseau local (0.0.0.0), puis ouvrir sur le téléphone :
python api_serveur.py --hote 0.0.0.0 --port 8000
#   → http://<IP-du-PC>:8000/   (même réseau Wi-Fi)
```

Les fichiers de l'app vivent dans `agents/pwa/` (page unique + style + logique +
service worker + icônes). L'API les sert en statique via une **liste blanche**
de chemins — aucune traversée de répertoire possible.

> **Installation sur l'écran d'accueil / mode hors-ligne** : ils nécessitent un
> « contexte sécurisé » (HTTPS ou `localhost`). Sur un simple
> `http://<IP>:8000`, l'app **fonctionne comme une page web normale** mais n'est
> ni installable ni disponible hors-ligne. Pour l'installer réellement, placez
> l'API derrière du HTTPS (reverse-proxy, ou un tunnel type `cloudflared` /
> `ngrok`). Détails dans **MANUEL.md**.

### Générer un APK installable

Le dossier `agents/mobile-apk/` empaquette la PWA en application Android native
via **Capacitor**. Le résultat est un fichier `.apk` qu'on installe directement
sur un téléphone, sans passer par Google Play ni par un navigateur.

```bash
cd agents/mobile-apk
nix-shell shell.nix --run 'python build_apk.py --api-url http://<IP-du-PC>:8000'
# APK produit : agents/mobile-apk/dist/studio-ia-regie-debug.apk
```

La documentation exhaustive (prérequis, build release, signature, installation,
CI/CD, dépannage) se trouve dans **`agents/mobile-apk/README.md`**.

## Application de bureau (étape 10)

Interface graphique pour **Windows et Linux** (`bureau.py`), écrite en
**Tkinter** — inclus dans Python, donc rien à installer (sous Linux : paquet
système `python3-tk`). Elle réutilise la brique commune `client_api.py`.

```bash
python bureau.py --url http://127.0.0.1:8000
```

Elle offre : connexion, tableau de bord des productions (rafraîchissement
automatique), lancement d'une nouvelle production (si le rôle l'autorise), et
un panneau de détail montrant les étapes ET le journal des événements de
l'orchestrateur (son « raisonnement »). S'y ajoutent, pour les rôles habilités,
le **pilotage** (pause / reprise / arrêt), la **gestion des agents** optionnels,
les **objectifs & mémoire** et le **chat**. Voir **MANUEL.md** pour le détail.

## Modèles disponibles

| Modèle | Coût | Qualité | Recommandé pour |
|--------|------|---------|-----------------|
| `gpt-4o-mini` | Faible | Bon | Tests et prototypes |
| `gpt-4o` | Moyen | Excellent | Production finale |
| `gpt-3.5-turbo` | Très faible | Correct | Tests rapides |

## Structure des fichiers

| Fichier | Rôle |
|---------|------|
| `shared_state.py` | `WorldState` (mémoire commune) + schémas Pydantic par agent |
| `agent_base.py` | Classe de base `BaseAgent` partagée par tous les agents (initialisation LLM, parser, gestion d'erreurs) |
| `01_directeur_creatif.py` | Agent 01 — classe `DirecteurCreatif` : vision, genre, ton |
| `02_architecte_narratif.py` | Agent 02 — classe `ArchitecteNarratif` : synopsis, actes, scènes clés |
| `03_scenariste.py` | Agent 03 — classe `Scenariste` : fiches personnages, extrait scénario |
| `04_directeur_artistique.py` | Agent 04 — classe `DirecteurArtistique` : script Python Blender |
| `05_directeur_technique.py` | Agent 05 — classe `DirecteurTechnique` : script Shell Unreal Engine |
| `06_superviseur_post_production.py` | Agent 06 — classe `SuperviseurPostProduction` : audit de conformité, déclenche GIMP/montage **seulement si nécessaire** |
| `07_exporteur_multi_format.py` | Agent 07 — classe `ExporteurMultiFormat` : déclinaison multi-format (TV, téléphone, réseaux sociaux) via FFmpeg |
| `08_ingenieur_son.py` | Agent 08 — classe `IngenieurSon` : compose la bande originale sous forme d'un fichier Csound (.csd) autonome, rendu-able en audio sans interface |
| `utils_headless.py` | Génère les commandes headless (Blender, Unreal, GIMP, montage, export FFmpeg, bande son Csound) prêtes à copier-coller |
| `worker_distant.py` | Serveur d'exécution distant (stdlib pur, fichier autonome) — à lancer sur la machine de rendu ; API HTTP protégée par jeton |
| `client_worker.py` | Client du worker + `ExecuteurDistant` branché dans le pipeline (étapes de rendu distantes, rapatriement journaux/fichiers) |
| `executeur_local.py` | `ExecuteurLocal` (option `--local`, stdlib pur) — lance les rendus automatiquement sur cette machine, mêmes garde-fous et même liste blanche que le worker |
| `orchestrateur.py` | Moteur d'exécution central — `Etape` (description déclarative) + `Orchestrateur` (retry, validation des sorties, reprise `--reprendre`, bilan, notification du journal) |
| `journal_production.py` | Journal de production (stdlib pur) — base SQLite `output/studio.db` (historique interrogeable) + logs structurés JSONL `output/journaux/<id>.jsonl` ; mode dégradé si l'écriture échoue |
| `securite.py` | Fondation d'authentification (stdlib pur) — comptes + mots de passe hachés (pbkdf2), rôles/permissions, jetons de session signés (base `output/securite.db`) ; échoue fermé |
| `api_serveur.py` | API HTTP (stdlib pur) — connexion, historique et lancement de productions, protégés par les jetons de `securite.py` ; lancement asynchrone via sous-processus `main.py --production-id` ; échoue fermé (jamais de 500 pour un refus) ; sert aussi la PWA en statique |
| `client_api.py` | Client Python de l'API (stdlib pur, urllib) — brique **commune** aux interfaces (bureau, scripts) ; masque le jeton Bearer, l'encodage JSON et les codes d'erreur (`ErreurAPI`) |
| `bureau.py` | Application de bureau Tkinter (étape 10) — connexion, tableau de bord, lancement et suivi détaillé ; s'appuie sur `client_api.py` |
| `pwa/` | Application mobile PWA (étape 9) — `index.html`, `style.css`, `app.js`, `sw.js` (service worker), `manifest.webmanifest`, `icons/` ; servie en statique par l'API |
| `main.py` | Point d'entrée CLI — définit le pipeline déclaratif (7 `Etape`), crée le journal et délègue l'exécution à l'`Orchestrateur` |

Chaque agent expose une classe avec une méthode métier dédiée (`generer_vision()`,
`construire_structure()`, `ecrire_scenario()`, `creer_scene_blender()`,
`creer_setup_unreal()`, `analyser_conformite()`, `generer_exports()`). Les
fichiers commencent par un chiffre pour l'ordre de lecture ; l'orchestrateur
les charge via `importlib.util` car Python n'autorise pas `import 01_...`
directement.

### Orchestrateur central

Le pipeline n'est plus un script linéaire : chaque étape est décrite par un
objet `Etape` (agent, entrées, sorties, criticité, tentatives) et le moteur
`Orchestrateur` exécute la liste de façon générique :

- **Retry** : chaque appel LLM est retenté (2 tentatives par défaut) ;
- **Validation** : après chaque étape, les clés de sortie attendues sont
  vérifiées dans `WorldState` — une étape qui ne produit pas ses sorties est
  déclarée en échec ;
- **Criticité** : un échec d'étape critique (01–05) sauvegarde l'état partiel
  et arrête proprement ; un échec d'étape optionnelle (06–07) est journalisé
  et le pipeline continue ;
- **Reprise** : `--reprendre` saute les étapes dont les sorties sont déjà
  dans `world_state.json` ;
- **Human-in-the-loop** : `--interactif` insère des arrêts contrôlés après
  chaque étape créative (valider / réviser avec directives / arrêter) ;
- **Bilan** : un récapitulatif final liste les étapes réussies / ignorées /
  échouées avec leur durée et le nombre de révisions humaines ;
- **Étapes non-LLM** : le champ `fabrique` d'une `Etape` injecte un objet
  déjà construit (ex : l'`ExecuteurDistant` des étapes de rendu) au lieu de
  charger un module d'agent.

Pour ajouter un agent au pipeline : créer le fichier de l'agent (hériter de
`BaseAgent`), puis ajouter une `Etape` dans `construire_pipeline()` de
`main.py` — aucun autre code à modifier.

### Agent 06 — Superviseur Post-Production (conditionnel)

Ce dernier agent n'exécute jamais un outil "juste au cas où". Il audite le
résultat des Agents 04/05 et ne déclenche que ce qui est réellement
nécessaire, parmi 6 logiciels open source :

| Outil | Usage | Déclenché quand... | Sortie |
|---|---|---|---|
| **GIMP** | Retouche image | un écart visuel doit être corrigé | `output/retouche_gimp.py` (Python-Fu, exécutable en batch) |
| **Kdenlive / Shotcut** | Montage vidéo | un assemblage est requis pour rendre le rendu final conforme | `output/notes_montage.txt` |
| **Inkscape** | Illustration vectorielle | une affiche, un logo ou un titre stylisé est nécessaire | `output/notes_inkscape.txt` |
| **Darktable** | Développement RAW | des textures/références haute qualité manquent de réalisme | `output/notes_darktable.txt` |
| **Krita** | Dessin/peinture numérique | un concept art ou matte painting est requis | `output/concept_krita.py` (API Krita, exécutable en batch) |
| **OBS Studio** | Capture/streaming | le rendu final doit être capturé en direct | `output/notes_obs.txt` |

Kdenlive/Shotcut, Inkscape, Darktable et OBS n'ont pas de vrai mode headless
"un clic" (Kdenlive/Shotcut reposent sur le moteur MLT, `melt` permet un rendu
automatisé une fois le projet construit ; les autres nécessitent une scène ou
un profil déjà configuré) — le studio sauvegarde donc des notes d'instructions
claires plutôt qu'une commande one-shot pour ces cas.

Si le résultat est déjà cohérent, aucun outil n'est proposé — seuls
Blender et Unreal Engine (déjà générés par les Agents 04/05) apparaissent
dans le récapitulatif final. La majorité des projets n'auront besoin que
d'un sous-ensemble de ces outils, voire d'aucun.

### Agent 07 — Exporteur Multi-Format (conditionnel)

Cet agent détermine les formats de diffusion pertinents pour le projet et
génère un script FFmpeg unique qui décline la vidéo master en plusieurs
formats : 16:9 (TV/YouTube), 9:16 (TikTok/Reels/Shorts), 1:1 (Instagram
feed), 4:5 (Instagram vertical) ou 21:9 (cinémascope). Le script est
sauvegardé dans `output/export_multi_format.sh` et est prêt à être exécuté
une fois le master vidéo disponible.

## Tester un agent seul

Chaque agent peut être lancé indépendamment pour tester :

```bash
cd agents/
python 01_directeur_creatif.py
python 04_directeur_artistique.py
```

## Points d'attention LangChain

- **Tokens** : le pipeline complet consomme ~3000-6000 tokens par exécution avec `gpt-4o-mini`
- **Parseurs Pydantic** : si un agent renvoie un JSON malformé, LangChain lèvera une `OutputParserException`
- **Version** : le projet cible `langchain>=0.2.0` — évitez de monter en version sans tester
