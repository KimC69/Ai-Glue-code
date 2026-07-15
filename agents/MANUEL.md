# Manuel complet — Studio IA multi-agents

> Manuel de référence exhaustif du projet, pensé pour une publication sur
> **GitHub** : il explique le rôle et le fonctionnement de **chaque fichier**,
> comment tout lancer (pipeline, API, application mobile, application de bureau),
> le modèle de sécurité, les tests, et la marche à suivre pour publier
> proprement. Le `README.md` reste le guide de prise en main rapide ; ce document
> est la référence détaillée.

---

## Table des matières

1. [Ce que fait le projet](#1-ce-que-fait-le-projet)
2. [Philosophie technique](#2-philosophie-technique)
3. [Vue d'ensemble de l'architecture](#3-vue-densemble-de-larchitecture)
4. [Prérequis et installation](#4-prérequis-et-installation)
5. [Configuration (secrets et comptes)](#5-configuration-secrets-et-comptes)
6. [Démarrage rapide de bout en bout](#6-démarrage-rapide-de-bout-en-bout)
7. [Concepts transverses](#7-concepts-transverses)
8. [Référence fichier par fichier](#8-référence-fichier-par-fichier)
9. [L'API HTTP en détail](#9-lapi-http-en-détail)
10. [Étape 9 — Application mobile (PWA)](#10-étape-9--application-mobile-pwa)
11. [Étape 10 — Application de bureau](#11-étape-10--application-de-bureau)
12. [Sécurité et modèle de menace](#12-sécurité-et-modèle-de-menace)
13. [Tests](#13-tests)
14. [Dépannage (FAQ)](#14-dépannage-faq)
15. [Publier sur GitHub](#15-publier-sur-github)
16. [Feuille de route](#16-feuille-de-route)

---

## 1. Ce que fait le projet

Le **Studio IA** est une chaîne de production cinématographique automatisée.
À partir d'une simple **idée de film** en une phrase, huit agents IA
spécialisés (basés sur LangChain) collaborent pour produire, étape par étape :
une vision artistique, une structure narrative, un scénario, des scripts de
scène pour **Blender**, un setup pour **Unreal Engine**, un audit de
post-production, des scripts d'export multi-format **FFmpeg**, et une bande
originale **Csound** (`.csd`) rendue en audio sans interface graphique.

Autour de ce cœur créatif, le projet fournit une **infrastructure complète**
pour piloter, tracer et sécuriser ces productions :

- un **orchestrateur** robuste (reprise après panne, retry, validation humaine) ;
- un **worker distant** pour lancer les rendus lourds sur une autre machine ;
- une **exécution locale automatique** (`--local`) : le studio lance lui-même
  les logiciels installés sur cette machine (Csound pour la bande son, etc.) ;
- un **journal** (base SQLite + logs JSONL) pour tracer chaque production ;
- une **authentification** (comptes, rôles, jetons signés) ;
- une **API HTTP** ;
- deux **interfaces** : une application **mobile** (PWA) et une application de
  **bureau** (Tkinter).

Tout est en **français** (code, commentaires, messages) et pensé pour une
utilisation **locale**, sans déploiement cloud obligatoire.

---

## 2. Philosophie technique

Quatre principes guident tout le projet. Les comprendre permet de comprendre
la plupart des décisions de conception.

1. **Zéro dépendance pour l'infrastructure.** Seul le *cœur créatif* (les
   agents) a besoin de bibliothèques externes (`langchain`, `pydantic`,
   `python-dotenv`). Toute l'infrastructure — orchestrateur, worker, journal,
   sécurité, API, client, bureau, PWA — est écrite **uniquement avec la
   bibliothèque standard de Python** (et du JavaScript « vanilla » côté web).
   Conséquence : ces briques s'installent, se lancent et se testent partout,
   sans rien installer.

2. **« Échouer fermé » pour la sécurité.** Toute vérification de sécurité qui
   ne peut pas aboutir (base indisponible, jeton invalide, secret manquant)
   **refuse** l'accès. On ne laisse jamais un doute autoriser quelqu'un.

3. **« Mode dégradé » pour l'observabilité.** À l'inverse, la journalisation ne
   doit **jamais** interrompre une production : si la base ou le fichier de log
   est indisponible, le studio le signale une fois et continue sans traces. La
   sécurité bloque ; l'observabilité s'efface.

4. **Nommage français et lisibilité.** Classes, fonctions, variables et
   messages sont en français. Le code est abondamment commenté pour rester
   compréhensible par un lecteur qui apprend.

---

## 3. Vue d'ensemble de l'architecture

```
                              VOTRE IDÉE
                                  │
   ┌──────────────────────────── CŒUR CRÉATIF (LangChain) ───────────────────┐
   │  Agent 01 Directeur créatif      → vision, genre, ton                    │
   │  Agent 02 Architecte narratif    → synopsis, actes, scènes              │
   │  Agent 03 Scénariste             → personnages, dialogues               │
   │  Agent 04 Directeur artistique   → script Blender (.py)                 │
   │  Agent 05 Directeur technique    → script Unreal (.sh)                  │
   │  Agent 06 Superviseur post-prod  → audit + outils conditionnels         │
   │  Agent 07 Exporteur multi-format → script FFmpeg (.sh)                  │
   │  Agent 08 Ingénieur du son       → bande son Csound (.csd)              │
   └──────────────────────────────────┬──────────────────────────────────────┘
                                       │  piloté par
                            ┌──────────▼───────────┐
                            │    ORCHESTRATEUR      │  retry, reprise, HITL,
                            │  (orchestrateur.py)   │  validation, bilan
                            └──┬───────────┬────────┘
             écrit dans        │           │        peut déléguer les rendus à
        ┌────────────▼──┐   ┌──▼─────────┐  └──►  WORKER DISTANT (worker_distant.py)
        │   JOURNAL     │   │  WORLD     │            via client_worker.py
        │ (SQLite+JSONL)│   │  STATE     │
        └───────┬───────┘   └────────────┘
                │ lu par
   ┌────────────▼─────────────────────────────────────────────────────────────┐
   │                         API HTTP  (api_serveur.py)                         │
   │   protégée par l'AUTHENTIFICATION (securite.py : comptes, rôles, jetons)   │
   │   /connexion  /productions  /productions/<id>  + sert la PWA en statique   │
   └───────┬───────────────────────────────────────────────────┬───────────────┘
           │ via client_api.py (Python)             même origine │ (fetch JS)
   ┌───────▼────────┐                                    ┌───────▼───────────────┐
   │  BUREAU (Tk)   │  étape 10                           │  PWA mobile           │ étape 9
   │  bureau.py     │                                     │  pwa/ (Android)       │
   └────────────────┘                                     └───────────────────────┘
```

Deux familles de fichiers, donc : le **cœur créatif** (dépend de LangChain) et
l'**infrastructure + interfaces** (bibliothèque standard uniquement).

---

## 4. Prérequis et installation

### 4.1 Python

Python **3.10 ou plus récent** est recommandé.

### 4.2 Le cœur créatif (pour lancer de vraies productions)

```bash
cd agents/
pip install -r requirements.txt      # langchain, pydantic, python-dotenv…
```

Ces dépendances ne sont nécessaires **que** pour exécuter le pipeline d'agents
(qui appelle un LLM). L'API, le journal, la sécurité, le client, le bureau et
la PWA fonctionnent **sans** elles.

### 4.3 L'application de bureau (Tkinter)

Tkinter est inclus avec Python sur Windows et macOS. Sous **Linux**, installez
le paquet système :

```bash
sudo apt install python3-tk      # Debian/Ubuntu
```

### 4.4 L'application mobile (PWA)

Rien à installer : elle est servie par l'API et s'ouvre dans le navigateur du
téléphone.

---

## 5. Configuration (secrets et comptes)

### 5.1 Variables d'environnement

| Variable | Utilisée par | Rôle |
|---|---|---|
| `OPENAI_API_KEY` | cœur créatif | Clé du LLM (agents). Placée dans `.env`. |
| `SESSION_SECRET` | sécurité + API | Clé de **signature des jetons** de session. **Obligatoire** pour lancer l'API. |
| `WORKER_JETON` | worker/rendu distant | Jeton d'accès au worker (facultatif). |

Copiez le modèle et complétez :

```bash
cp .env.example .env
# éditez .env : OPENAI_API_KEY=..., SESSION_SECRET=...
```

> **Important** : `SESSION_SECRET` doit être une longue chaîne aléatoire, gardée
> secrète et **stable** (si elle change, tous les jetons émis deviennent
> invalides). Ne la committez jamais (voir le `.gitignore`).

### 5.2 Créer des comptes

L'API et les interfaces exigent une **connexion**. Créez au moins un compte
administrateur (mot de passe demandé au clavier, jamais en argument) :

```bash
python main.py --creer-utilisateur alice --role admin
python main.py --lister-utilisateurs
```

**Trois rôles** existent :

| Rôle | Peut consulter | Peut lancer/piloter | Peut gérer les comptes |
|---|:---:|:---:|:---:|
| `admin` | ✅ | ✅ | ✅ |
| `operateur` | ✅ | ✅ | ❌ |
| `observateur` | ✅ | ❌ | ❌ |

Les interfaces s'adaptent au rôle : un `observateur` ne voit pas le bouton
« Nouvelle production ».

---

## 6. Démarrage rapide de bout en bout

```bash
cd agents/

# 1) Un secret de session pour cette machine (exemple ; gardez-le stable)
export SESSION_SECRET="une-longue-chaine-aleatoire-et-secrete"

# 2) Un compte
python main.py --creer-utilisateur alice --role admin

# 3) L'API (0.0.0.0 pour la rendre accessible au téléphone du même Wi-Fi)
python api_serveur.py --hote 0.0.0.0 --port 8000
```

Ensuite, au choix :

- **Bureau** (sur le PC) : `python bureau.py --url http://127.0.0.1:8000`
- **Mobile** (sur le téléphone) : ouvrir `http://<IP-du-PC>:8000/`

Connectez-vous avec `alice`, lancez une production, suivez ses étapes.

> Rappel : lancer une *vraie* production exige que les dépendances LangChain et
> `OPENAI_API_KEY` soient présentes, car l'API démarre `main.py` en
> arrière-plan pour faire le travail.

---

## 7. Concepts transverses

- **`WorldState` (mémoire commune)** : un objet partagé où chaque agent lit les
  sorties des précédents et écrit les siennes. C'est le « plateau » sur lequel
  toute l'équipe travaille. Sérialisé en `output/world_state.json` pour
  permettre la reprise.

- **Étape déclarative (`Etape`)** : le pipeline n'est pas un script linéaire
  mais une **liste d'objets** décrivant chacun (agent, entrées, sorties
  attendues, criticité, nombre de tentatives). L'orchestrateur exécute cette
  liste de façon générique.

- **Jeton de session signé** : à la connexion, l'API renvoie un jeton contenant
  l'utilisateur, son rôle et une date d'expiration, le tout **signé** avec
  `SESSION_SECRET`. Il se vérifie sans interroger la base. Il s'envoie ensuite
  dans l'en-tête `Authorization: Bearer <jeton>`.

- **Même origine** : la PWA est servie par l'API elle-même, donc elle l'appelle
  avec des chemins relatifs (`/productions`) — pas de configuration d'URL ni de
  problème de CORS.

---

## 8. Référence fichier par fichier

### 8.1 Le cœur créatif

| Fichier | Rôle détaillé |
|---|---|
| `shared_state.py` | Définit `WorldState` (la mémoire commune) et les **schémas Pydantic** de sortie de chaque agent (garantit un JSON structuré et validé). |
| `agent_base.py` | Classe `BaseAgent` : socle commun à tous les agents (initialisation du LLM, parseur de sortie, gestion d'erreurs, retry). Un nouvel agent en hérite. |
| `01_directeur_creatif.py` | Agent 01 `DirecteurCreatif` — définit la vision : genre, ton, intention artistique. |
| `02_architecte_narratif.py` | Agent 02 `ArchitecteNarratif` — synopsis, structure en actes, scènes clés. |
| `03_scenariste.py` | Agent 03 `Scenariste` — fiches personnages, dialogues, extrait de scénario. |
| `04_directeur_artistique.py` | Agent 04 `DirecteurArtistique` — génère un **script Python Blender** (`output/scene_*.py`). |
| `05_directeur_technique.py` | Agent 05 `DirecteurTechnique` — génère un **script Shell Unreal** (`output/setup_*.sh`). |
| `06_superviseur_post_production.py` | Agent 06 `SuperviseurPostProduction` — audite le résultat et ne déclenche **que les outils nécessaires** (GIMP, Krita, montage…). Optionnel. |
| `07_exporteur_multi_format.py` | Agent 07 `ExporteurMultiFormat` — génère un **script FFmpeg** déclinant la vidéo master en 16:9, 9:16, 1:1… Optionnel. |
| `08_ingenieur_son.py` | Agent 08 `IngenieurSon` — compose la **bande originale** sous forme d'un fichier **Csound** (`.csd`) autonome, rendu-able en audio sans interface (`csound bande_son.csd -o bande_son.wav`). Optionnel. |
| `utils_headless.py` | Fabrique les commandes « headless » (Blender, Unreal, FFmpeg, Csound…) prêtes à copier-coller. |

> Les fichiers d'agents commencent par un chiffre pour l'ordre de lecture.
> Comme Python n'autorise pas `import 01_...`, l'orchestrateur les charge via
> `importlib.util`.

### 8.2 L'orchestration

| Fichier | Rôle détaillé |
|---|---|
| `orchestrateur.py` | Moteur central. `Etape` décrit une étape ; `Orchestrateur` exécute la liste : **retry** (2 tentatives), **validation** des sorties, **criticité** (échec critique = arrêt propre + sauvegarde ; optionnel = on continue), **reprise** (`--reprendre`), **human-in-the-loop** (`--interactif`), **bilan** final, et **notification du journal**. |
| `main.py` | Point d'entrée CLI. Construit le pipeline (les 8 `Etape`), crée le journal, gère toutes les options (`--idea`, `--model`, `--reprendre`, `--interactif`, `--worker`, `--historique`, `--projet`, `--inspiration`/`--suite-de`, `--lister-projets`, gestion des comptes…) et délègue à l'orchestrateur. |

### 8.3 L'exécution des rendus (locale ou distante)

Par défaut, les agents génèrent les scripts sans les exécuter. Deux options
permettent de lancer les rendus automatiquement — **mutuellement exclusives** :
`--local` (sur cette machine) ou `--worker` (sur une machine de rendu distante).
Les deux réutilisent la même liste blanche d'outils, la même construction de
commande (jamais par l'IA, jamais via un shell) et les mêmes garde-fous.

| Fichier | Rôle détaillé |
|---|---|
| `worker_distant.py` | Serveur d'exécution à copier **sur la machine de rendu** (fichier autonome, stdlib pur). Reçoit un script + des fichiers, exécute Blender/Unreal/FFmpeg/Csound dans un dossier isolé, renvoie journaux et fichiers produits en flux. Protégé par jeton (`X-Jeton`). |
| `client_worker.py` | Côté studio : client du worker + `ExecuteurDistant`, l'objet injecté comme « étape non-LLM » dans le pipeline pour piloter les rendus distants et rapatrier les résultats. |
| `executeur_local.py` | Côté studio : `ExecuteurLocal` (option `--local`, stdlib pur), même interface que `ExecuteurDistant` mais exécute les rendus **sur cette machine** (headless). ⚠️ exécuter en local un script Blender/Unreal/FFmpeg généré par IA revient à exécuter du code arbitraire sur votre machine — Csound (synthèse musicale) est nettement moins risqué. |

### 8.4 L'observabilité

| Fichier | Rôle détaillé |
|---|---|
| `journal_production.py` | `JournalProduction` : écrit dans **SQLite `output/studio.db`** (productions, étapes, événements — interrogeable) **et** dans un **log JSONL `output/journaux/<id>.jsonl`** (un événement JSON par ligne, facile à suivre en direct). Concurrence gérée (mode WAL + `busy_timeout`). **Mode dégradé** : si l'écriture échoue, on prévient une fois et la production continue. C'est cette base que lisent l'API et les interfaces. |

### 8.5 La sécurité

| Fichier | Rôle détaillé |
|---|---|
| `securite.py` | `Securite` : comptes dans **`output/securite.db`** (séparée de l'historique créatif), mots de passe **hachés** (pbkdf2-hmac-sha256 + sel), **rôles/permissions**, **jetons de session signés** (via `SESSION_SECRET`) et révocables. **Échoue fermé** : tout doute refuse l'accès. Utilisé en CLI (gestion des comptes) et par l'API (vérification des jetons). |

### 8.6 L'API

| Fichier | Rôle détaillé |
|---|---|
| `api_serveur.py` | API HTTP (stdlib `http.server`). Expose connexion/déconnexion, historique et lancement de productions, chaque route protégée par les jetons de `securite.py`. **Lancement asynchrone** : `POST /productions` génère un identifiant, démarre `main.py --production-id <id>` en sous-processus et répond `202` immédiatement. Sert aussi la **PWA en statique** via une liste blanche de chemins. **Échoue fermé** : jamais de 500 pour un refus (401/403), refuse de démarrer sans `SESSION_SECRET`. |

### 8.7 Les interfaces (étapes 9 et 10)

| Fichier | Rôle détaillé |
|---|---|
| `client_api.py` | **Brique commune** aux interfaces Python. Classe `ClientAPI` (urllib pur) : gère l'URL de base, le jeton Bearer, l'encodage/décodage JSON et convertit toute erreur HTTP en `ErreurAPI(message, code)`. Méthodes : `sante`, `connexion`, `deconnexion`, `lister_productions`, `details_production`, `lancer_production`. Entièrement testée. Le bureau s'en sert ; la PWA en reproduit l'équivalent en JavaScript. |
| `bureau.py` | Application de bureau **Tkinter** (étape 10). Import de Tk **protégé** (le module reste importable/testable sans écran). Helpers d'affichage **purs** (`libelle_statut`, `formater_duree`, `resumer_production`) testés à part. Classe `AppBureau` : trois écrans (connexion → tableau → détail), appels réseau dans un thread pour ne pas figer l'interface. |
| `pwa/index.html` | Page unique de la PWA : trois vues (connexion, tableau, détail) + modale « nouvelle production » + zone de notification (« toast »). |
| `pwa/style.css` | Thème « régie » : fond noir cinéma + ambre, mobile-first, badges de statut colorés par classe. |
| `pwa/app.js` | Logique JavaScript **vanilla** : équivalent de `client_api.py` côté navigateur. Jeton dans `localStorage`, gestion des trois vues, rafraîchissement automatique (~5 s), gestion du 401 (reconnexion), masquage du bouton de lancement selon le rôle, enregistrement du service worker **si contexte sécurisé**. |
| `pwa/sw.js` | Service worker : met en cache la **coquille statique** (installable + hors-ligne) mais **jamais les appels API** (données vivantes + sécurité toujours par le réseau). |
| `pwa/manifest.webmanifest` | Métadonnées d'installation (nom, couleurs, icônes, mode `standalone`, orientation portrait). |
| `pwa/icons/generer_icones.py` | Génère `icon-192.png` et `icon-512.png` **sans dépendance** (encodeur PNG maison : `zlib` + `struct`). Relancer le script régénère les icônes. |

---

## 9. L'API HTTP en détail

Toutes les routes (sauf `/sante` et `/connexion`) exigent l'en-tête
`Authorization: Bearer <jeton>`.

| Méthode & route | Permission | Corps / réponse |
|---|---|---|
| `GET /sante` | publique | `{ok:true, ...}` — l'API répond |
| `POST /connexion` | publique | `{nom, mot_de_passe}` → `{jeton, role, expire_dans_s}` |
| `POST /deconnexion` | jeton valide | révoque le jeton présenté |
| `GET /productions` | `consulter` | `{productions:[{..., etapes_reussies}]}` |
| `GET /productions/<id>` | `consulter` | `{production, etapes:[...], evenements:[...]}` ou `404` |
| `GET /projets` | `consulter` | `{projets:[{slug, nom, cree_le, a_un_etat}]}` |
| `POST /productions` | `lancer_production` | `{idee, modele?, projet?, inspiration?}` → `202 {id, statut, suivi}` ; `404` si `inspiration` introuvable, `400` si `inspiration` invalide |
| `POST /productions/<id>/pause` | `piloter_production` | met la production en pause (effet fin d'étape) |
| `POST /productions/<id>/reprendre` | `piloter_production` | reprend une production en pause |
| `POST /productions/<id>/arreter` | `piloter_production` | arrêt propre ; reprise possible via `--reprendre` |
| `GET /agents` | `consulter` | `{agents:[{numero, nom, optionnel, actif}]}` |
| `POST /agents/<numero>` | `gerer_utilisateurs` | `{actif}` — désactivable **seulement** pour les agents 6/7/8 (`409` sinon) |
| `GET /objectifs` | `consulter` | `{texte, modifie_le, par}` |
| `POST /objectifs` | `piloter_production` | `{texte}` — injectés au lancement des futures productions |
| `GET /memoire` | `consulter` | `{objectifs, etat:{present, production_id, cles}}` |
| `POST /memoire/reset` | `gerer_utilisateurs` | efface `world_state` (`409` si une prod est active) |
| `POST /chat` | `piloter_production` | `{agent, message, modele?}` → `{reponse}` |
| `GET /` `/app.js` `/style.css` … | publique | fichiers statiques de la PWA (liste blanche) |

**Codes d'erreur clés** : `400` corps invalide, `401` jeton absent/invalide,
`403` rôle insuffisant, `404` route/production/agent inconnu, `409` action
incompatible avec l'état courant (prod déjà terminée, agent indispensable, prod
active), `411` longueur manquante, `502/503` le chat n'a pas pu joindre le
modèle. **Jamais de `500` pour un refus de sécurité.**

**Statuts** : production = `en_cours | en_pause | terminee | echec | arretee` ;
étape = `reussie | ignoree | echouee`. Un événement peut avoir un niveau
`critique`.

**Pilotage à distance — comment ça marche.** Une production tourne dans un
sous-processus détaché : on ne peut plus lui « parler » au clavier. Le canal de
commande est un **fichier JSON par production** (`output/controle/<id>.json`).
Les interfaces y écrivent `pause`/`reprendre`/`arreter` ; l'orchestrateur le lit
au **début de chaque étape**. Conséquences : (1) l'effet arrive **à la fin de
l'étape en cours** ; (2) la lecture « échoue sûr » — un fichier corrompu n'arrête
jamais une production ; (3) l'écriture « échoue fermé » — si la commande ne peut
pas être écrite, l'API le signale honnêtement au lieu de faire croire à un arrêt.

**Objectifs & mémoire.** Les *objectifs* (`output/objectifs.json`) sont une note
persistante injectée au Directeur Créatif au lancement de chaque **nouvelle**
production. La *mémoire de travail* est le `world_state` de la dernière
production : `GET /memoire` en donne un résumé (clés remplies, valeurs longues
tronquées) et `POST /memoire/reset` l'efface (refusé tant qu'une prod tourne).

**Projets & suites.** Un *projet* (`--projet "Nom"` en CLI, champ `projet` sur
`POST /productions`) range un film dans son propre dossier
`output/projets/<slug>/` : scripts générés (via `STUDIO_OUTPUT_DIR` lu par
`shared_state.dossier_sortie()`), `meta.json` et `world_state.json` archivé en
fin de production (écrit depuis l'état **en mémoire** de la production, pour
rester correct même si plusieurs productions tournent en parallèle). Écrire une
*suite* se fait avec `--inspiration "Projet source"` (champ `inspiration`) : on
lit le `world_state.json` archivé du projet source, on en tire un bloc RÉFÉRENCE
(clés créatives : synopsis, personnages, style… ; scripts techniques exclus) et
on l'injecte à l'Agent 01. **Échoue fermé** : projet source absent ou sans état
→ refus explicite (`404`/erreur CLI), jamais de fausse suite ; incompatible avec
`--reprendre`. `world_state` global (`output/world_state.json`) reste inchangé,
donc `/memoire` continue de fonctionner comme avant.

Exemple complet :

```bash
JETON=$(curl -s -X POST http://localhost:8000/connexion \
  -d '{"nom":"alice","mot_de_passe":"..."}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["jeton"])')

curl -X POST http://localhost:8000/productions \
  -H "Authorization: Bearer $JETON" \
  -d '{"idee":"Un détective robot dans une ville néon"}'

curl -H "Authorization: Bearer $JETON" http://localhost:8000/productions/<id>
```

---

## 10. Étape 9 — Application mobile (PWA + APK Android)

### 10.1 Qu'est-ce qu'une PWA ?

Une **Progressive Web App** est une page web qui, servie en HTTPS, peut
s'**installer** sur l'écran d'accueil et fonctionner **hors-ligne** comme une
application native — sans passer par un magasin d'applications.

### 10.2 Lancer et ouvrir

```bash
python api_serveur.py --hote 0.0.0.0 --port 8000
```

Sur le téléphone (même réseau Wi-Fi), ouvrir `http://<IP-du-PC>:8000/`.
Trouver l'IP du PC : `ip addr` (Linux) ou `ipconfig` (Windows).

### 10.3 Ce qu'elle permet

Connexion, tableau de bord des productions (auto-rafraîchi), lancement d'une
production (si le rôle l'autorise), et vue détail avec les **étapes** et le
**journal des événements** de l'orchestrateur. Plus, pour les rôles habilités :
**pilotage à distance** (pause / reprise / arrêt depuis la vue détail),
**gestion des agents** optionnels, **objectifs & mémoire**, et **chat** avec un
agent choisi.

### 10.4 Caveat important : HTTPS pour installer en PWA

L'**installation** et le **mode hors-ligne** exigent un « contexte sécurisé »
(HTTPS, ou `localhost`). En `http://<IP>:8000`, le navigateur **refuse
d'enregistrer le service worker** : l'app marche comme une page web normale
mais n'est **ni installable ni disponible hors-ligne**. C'est volontaire côté
navigateur (sécurité), pas un bug.

Pour l'installer réellement, exposez l'API derrière du HTTPS :

- un **reverse-proxy** (Caddy, Nginx) avec un certificat, ou
- un **tunnel** (`cloudflared`, `ngrok`) qui fournit une URL `https://…`.

Une fois en HTTPS, le navigateur mobile proposera « Ajouter à l'écran
d'accueil » et l'app s'ouvrira en plein écran (mode `standalone`).

### 10.5 APK Android (installation directe sans navigateur)

Le dossier `agents/mobile-apk/` transforme la PWA en **APK Android natif**
avec [Capacitor](https://capacitorjs.com/). Cela donne un fichier `.apk` que
l'on transfère et installe directement sur un téléphone, sans Google Play et
sans avoir besoin de HTTPS pour l'installation.

Build debug (recommandé pour les tests) :

```bash
cd agents/mobile-apk
nix-shell shell.nix --run 'python build_apk.py --api-url http://<IP-du-PC>:8000'
```

Le APK est produit dans :

```
agents/mobile-apk/dist/studio-ia-regie-debug.apk
```

Build release (non signé par défaut, à signer ensuite) :

```bash
nix-shell shell.nix --run 'python build_apk.py --release --api-url http://<IP-du-PC>:8000'
```

**Principe :** l'APK embarque les fichiers web (HTML/CSS/JS) et se connecte à
l'API distante dont l'adresse est injectée dans `www/config.js` au moment du
build. Le téléphone et le serveur doivent être sur le même réseau (ou l'API
doit être accessible publiquement via HTTPS).

La documentation complète — prérequis, installation du SDK, signature du release,
transfert sur téléphone, CI/CD GitHub Actions et dépannage — se trouve dans
**`agents/mobile-apk/README.md`**.

---

## 11. Étape 10 — Application de bureau

### 11.1 Lancer

```bash
python bureau.py --url http://127.0.0.1:8000
```

L'adresse de l'API est aussi modifiable dans l'écran de connexion.

### 11.2 Ce qu'elle permet

- **Connexion** (nom + mot de passe → jeton géré automatiquement).
- **Tableau de bord** : liste des productions, rafraîchissement automatique
  (~5 s), bouton manuel.
- **Nouvelle production** : fenêtre dédiée (idée + modèle facultatif), visible
  seulement si le rôle est `admin` ou `operateur`.
- **Détail** : entête (statut, modèle, dates), tableau des **étapes**
  (numéro, nom, statut, durée) et **journal** des événements de l'orchestrateur.
- **Pilotage** : boutons Pause / Reprendre / Arrêter, activés selon le statut
  de la production et le rôle (`piloter_production`).
- **Agents** : fenêtre listant les 8 agents avec un interrupteur par agent
  optionnel (6/7/8), réservé aux administrateurs.
- **Mémoire & objectifs** : édition des objectifs persistants, consultation de
  l'état de travail, réinitialisation (admin).
- **Chat** : fenêtre de discussion avec l'agent choisi (hors production).
- **Déconnexion** : révoque le jeton côté serveur.

### 11.3 Détails techniques

- **Tkinter** (bibliothèque standard) : rien à installer côté utilisateur
  (sauf `python3-tk` sous Linux).
- L'import de Tk est **protégé** : le module reste importable et ses helpers
  d'affichage restent testables même sans environnement graphique.
- Les appels réseau tournent dans un **thread** ; l'interface ne se fige
  jamais. Un `401` (jeton expiré) ramène proprement à l'écran de connexion.

### 11.4 Limites honnêtes

Les interfaces ne font que ce que **l'API expose**. Sont désormais disponibles :
pause / reprise / arrêt d'une production, activation/désactivation des agents
optionnels, objectifs & mémoire, et chat avec un agent. Restent volontairement
**hors périmètre** (non simulés) :

- ajouter ou retirer des agents « à chaud » (le catalogue des 8 agents est fixe ;
  seuls 6/7/8 sont activables/désactivables) ;
- réviser le contenu **au milieu** d'une étape (l'équivalent fin du mode
  `--interactif` de la CLI) — le pilotage agit à la **granularité de l'étape** ;
- discuter **avec la production en cours** (le chat est hors production).

---

## 12. Sécurité et modèle de menace

- **Mots de passe** : jamais en clair, hachés pbkdf2-hmac-sha256 + sel par
  utilisateur. Jamais passés en argument de ligne de commande.
- **Jetons** : signés avec `SESSION_SECRET`, avec expiration, révocables à la
  déconnexion. Sans le secret, l'API refuse de démarrer.
- **Rôles** : moindre privilège (observateur < operateur < admin).
- **API** : échoue fermé (401/403, jamais 500 pour un refus). La PWA est servie
  via une **liste blanche** de chemins → aucune traversée de répertoire.
- **Worker distant** : posséder son jeton = pouvoir exécuter du code sur la
  machine de rendu. À traiter comme un mot de passe SSH ; n'exposer
  (`--hote 0.0.0.0`) que sur un réseau de confiance.
- **Ce qui ne va JAMAIS sur GitHub** : `.env`, `SESSION_SECRET`,
  `OPENAI_API_KEY`, et tout `output/` (dont `securite.db`, qui contient les
  comptes et les empreintes de mots de passe). Voir le `.gitignore`.

Un modèle de menace plus détaillé peut être généré séparément (`threat_model.md`).

---

## 13. Tests

L'infrastructure est testable **sans aucune dépendance ni clé LLM** (elle
n'utilise que la bibliothèque standard). Les suites couvrent :

- **l'API** : routes, permissions, codes d'erreur, lancement asynchrone ;
- **la concurrence SQLite** du journal (mode WAL, contention transitoire,
  mode dégradé) ;
- **le client `client_api.py`** : de bout en bout contre un vrai serveur de
  test (connexion, liste, détail, lancement, 401/403, serveur injoignable) ;
- **le service statique de la PWA** : présence des fichiers, types MIME,
  en-tête `no-cache` du service worker, refus des routes non déclarées ;
- **les helpers du bureau** : fonctions pures d'affichage.

Chaque test démarre un serveur réel sur un port éphémère, avec un
`SESSION_SECRET` de test, des comptes en mémoire et un `main.py` factice pour
ne jamais consommer d'appel LLM. `bureau.py` et les modules d'infra passent
aussi `python -m py_compile`.

---

## 14. Dépannage (FAQ)

**L'API refuse de démarrer.** → `SESSION_SECRET` est absent. Définissez-le
(`export SESSION_SECRET=...`). C'est volontaire (échoue fermé).

**« Connexion refusée » sur le téléphone.** → l'API écoute-t-elle bien sur
`--hote 0.0.0.0` ? Le téléphone est-il sur le **même Wi-Fi** ? L'IP est-elle la
bonne ? Un pare-feu bloque-t-il le port ?

**Le téléphone ne propose pas « Installer / Ajouter à l'écran d'accueil ».** →
attendu en HTTP simple (pas de contexte sécurisé). Passez en HTTPS (§10.4).

**Le bureau affiche « Tkinter introuvable ».** → sous Linux :
`sudo apt install python3-tk`.

**La production reste bloquée « en cours ».** → une *vraie* production exige les
dépendances LangChain + `OPENAI_API_KEY` (le sous-processus `main.py` en a
besoin). Vérifiez `output/lancements_api/<id>.log`.

**J'ai changé `SESSION_SECRET` et tout le monde est déconnecté.** → normal : le
secret signe les jetons ; le changer invalide tous les jetons existants.

---

## 15. Publier sur GitHub

1. **Vérifiez le `.gitignore`** (fourni dans `agents/.gitignore`) : il exclut
   `.env`, `output/` et les caches Python. **Ne committez jamais** de secret ni
   la base `securite.db`.
2. Vérifiez qu'aucun secret ne traîne :
   ```bash
   git status            # .env et output/ ne doivent PAS apparaître
   git ls-files | grep -Ei 'env|secret|\.db$'   # ne doit rien renvoyer de sensible
   ```
3. Committez le code + `README.md` + `MANUEL.md` + `.env.example`.
4. Pour pousser depuis Replit, utilisez le flux Git intégré (voir la
   fonctionnalité de dépôt distant / le skill `git-remote`).

> Le `.env.example` documente les variables **sans** leurs valeurs : c'est lui
> qu'on committe, jamais `.env`.

---

## 16. Feuille de route

Le projet suit une feuille de route en 10 étapes.

| Étape | Sujet | État |
|---|---|:---:|
| 1–5 | Cœur créatif, orchestrateur, worker distant, journal | ✅ |
| 6 | Authentification (comptes, rôles, jetons) | ✅ |
| 7 | API HTTP | ✅ |
| 8 | Interface web complète | ⏭️ abandonnée au profit de la PWA |
| 9 | Application mobile (PWA Android) | ✅ |
| 10 | Application de bureau (Tkinter) | ✅ |

Le pilotage à distance (pause / reprise / arrêt), la gestion des agents
optionnels, les objectifs & mémoire et le chat sont désormais exposés par l'API
et branchés dans la PWA comme dans le bureau.
