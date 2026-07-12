---
name: Architecture des agents
description: Décisions d'architecture pour les agents du studio cinématographique (initialisation, erreurs, orchestrateur).
---

# Architecture des agents

## Règle

Tous les agents héritent d'une classe de base `BaseAgent` qui centralise :
- la vérification de la clé API OpenAI (lève `RuntimeError` si manquante) ;
- l'initialisation du LLM, du parser Pydantic et du prompt ;
- l'identifiant de l'agent pour les messages d'erreur.

Aucune classe d'agent ne doit appeler `sys.exit()` : elle lève une exception claire, et c'est l'orchestrateur qui décide d'arrêter ou de continuer.

**Why:** Avant la refactorisation, chaque agent dupliquait l'initialisation du LLM/parser et utilisait `sys.exit()` en cas d'erreur, ce qui rendait impossible une reprise propre, un test unitaire, ou un traitement différencié selon la criticité de l'agent.

**How to apply:**
- Lors de la création d'un nouvel agent, hériter de `BaseAgent`, passer `output_schema` et `agent_id`, puis appeler `self._build_prompt()`.
- Dans l'orchestrateur, envelopper instanciation + exécution de l'agent dans un même `try/except`.
- Pour les agents critiques (01–05), sauvegarder l'état partiel et arrêter proprement.
- Pour les agents optionnels (06–07), logger l'erreur et continuer sans bloquer le pipeline.

## Orchestrateur central déclaratif

Le pipeline est décrit comme des données (`Etape` : agent, entrées, sorties, criticité, nb de tentatives) et exécuté par un moteur générique (`Orchestrateur`) qui gère retry, validation des clés de sortie dans l'état partagé, reprise (`--reprendre` saute les étapes dont les sorties existent déjà), et bilan final.

**Why:** L'ancien `main.py` dupliquait 7 blocs quasi identiques (charge module → instancie → try/except → sauvegarde → affiche) ; toute évolution transversale (retry, reprise, timing) devait être copiée 7 fois. Le moteur est en stdlib pur (aucun import projet/LangChain) pour rester testable sans clé API ni pydantic installé.

**How to apply:**
- Nouvel agent dans le pipeline = ajouter une `Etape` dans `construire_pipeline()` (main.py), rien d'autre.
- La validation « sortie remplie » compare à `""` (et non à la truthiness) car `False` et `0` sont des sorties valides (bools/scores de l'audit).
- Les chemins des fichiers générés (`*_saved_path`) sont persistés dans l'état pour que le récap final et la reprise fonctionnent après un redémarrage.
- Échec définitif d'une étape optionnelle → ses clés `purger` sont réinitialisées, sinon le récap final ressortirait les données d'une production précédente.
- `--reprendre` refuse une `--idea` différente de celle en cours (sinon état mixte : nouvelle idée + anciens artefacts).
- `state.load()` uniquement sous `--reprendre` : sans lui, production vierge qui écrase l'ancien fichier — c'est ce qui empêche tout mélange inter-productions lors des skips de reprise.
- Une révision HITL échouée déclenche un rollback complet (snapshot `to_dict()` avant le tour) ; les callbacks `enregistrer` doivent écrire un jeu de clés stable pour que le rollback soit exhaustif.

## Worker d'exécution distant (--worker)

Les rendus lourds (Blender, Unreal, FFmpeg) s'exécutent sur une autre machine via un couple client/serveur HTTP en stdlib pur (pas SSH) : `worker_distant.py` (autonome, copiable seul) + `client_worker.py`. Auth par jeton `X-Jeton` (hmac.compare_digest), lanceurs whitelistés (blender --background --python / bash pour les .sh), un seul travail à la fois, chaînage `poursuivre` (un travail s'exécute dans le dossier d'un travail terminé — l'export FFmpeg y retrouve la vidéo du rendu Blender).

**Why:** HTTP stdlib = zéro dépendance des deux côtés et testable dans cet environnement (SSH ne l'était pas). Le modèle de confiance est assumé : le worker exécute des scripts arbitraires par fonction, donc **le jeton équivaut à un accès shell** — la doc ne doit jamais prétendre que la liste blanche empêche l'exécution de code arbitraire. Les vidéos rendues pèsent des Go : tout transfert (journal, fichiers) doit être en flux (morceaux 64 Kio, fichier `.partiel` renommé à la fin), jamais un `read()` complet en mémoire.

**How to apply:**
- Étape non-LLM dans le pipeline = `Etape.fabrique` (callable retournant l'« agent » pré-construit, court-circuite importlib).
- Les étapes distantes (8–10, `critique=False, essais=1`) ne sont ajoutées que pour les outils déclarés par `GET /sante` ; connexion vérifiée fail-fast AVANT tout appel LLM.
- Clés d'état `rendu_<outil>_{statut,travail_id,journal,fichiers}` ; seule `_statut` est `cles_sortie`, les quatre vont dans `purger`.
- Journaux + fichiers rapatriés dans `output/rendus/<outil>/` MÊME en cas d'échec (diagnostic), l'exception ErreurWorker est levée après.
- Flux recommandé : produire en local puis `--reprendre --worker URL` (ne relance que les rendus manquants).

## Journal de production (BDD SQLite + logs structurés JSONL)

Chaque exécution est tracée dans `journal_production.py` (stdlib pur : sqlite3 + json) : base `output/studio.db` (tables productions / etapes / evenements, interrogeable pour les futures interfaces web/Android) + un JSONL par production `output/journaux/<id>.jsonl` (un événement par ligne, streamable). L'orchestrateur reçoit un `journal` optionnel et le notifie aux points clés (etape_demarree/reussie/ignoree/echouee/revisee) ; par défaut c'est un **objet nul** (`_JournalNul` dans orchestrateur.py) — toutes méthodes no-op.

**Why:** l'objet nul garde l'orchestrateur sans dépendance et testable sans journal (les tests le construisent sans `journal=`). La journalisation ne doit JAMAIS casser une production : toute erreur d'E/S (disque plein, dossier lecture seule, base verrouillée) est absorbée et signalée une fois, puis le journal passe en **mode dégradé** (writes no-op) — l'observabilité ne réduit pas la fiabilité.

**How to apply:**
- Nouvel événement à tracer = appeler `self.journal.<methode>(...)` dans l'orchestrateur ; ajouter la méthode à `_JournalNul` ET à `JournalProduction` (mêmes signatures).
- L'identifiant de production est persisté dans `world_state.json` (`production_id`) : `--reprendre` le réutilise → les étapes de la reprise s'ajoutent à la même ligne production (demarrer_production fait INSERT OR IGNORE puis UPDATE statut='en_cours').
- Cohérence SQLite/JSONL en best-effort : `evenement()` écrit les deux sous un même `RLock` (ordre identique entre les flux) ; si un support est en panne, l'autre continue seul. Une donnée non sérialisable ne dégrade que sa propre ligne, jamais tout le flux (default=str + repli), et n'est jamais fatale.
- Consultation : `python main.py --historique` (lecture seule, ne crée pas de production).

## Authentification et sécurité (securite.py)

Fondation d'auth stdlib pur, base dédiée séparée du journal, pour les futures API/interfaces : comptes (mots de passe hachés pbkdf2), rôles→permissions, jetons de session signés HMAC **autonomes** (vérifiables sans la base) + révocation en base.

**Why (le principe qui gouverne tout) :** contrairement au journal (mode dégradé = writes no-op pour ne jamais casser une production), la sécurité **ÉCHOUE FERMÉ** — toute vérif qui ne peut aboutir (base HS, signature invalide, jeton expiré, révocation invérifiable, jti absent/non-str, claim mal typé) REFUSE. Un doute n'autorise jamais. Corollaire testé en revue : un jeton forgé mais bien signé ne doit JAMAIS faire remonter une exception native — tout parsing/typage de claim est normalisé en `ErreurSecurite`, sinon l'API tomberait en 500/DoS.

**How to apply:**
- Nouveau droit = éditer le dict `PERMISSIONS` (source unique), puis contrôler via `a_permission`/`jeton_autorise`.
- Clé de signature = secret `SESSION_SECRET` (jamais affiché) ; sans lui la gestion des comptes marche mais toute opération jeton lève `ErreurSecurite`. Le constructeur retombe sur l'env → pour tester l'absence de clé, `os.environ.pop("SESSION_SECRET")` d'abord.
- Itérations pbkdf2 stockées PAR utilisateur = on peut durcir plus tard sans invalider les comptes existants.
- **Décision de périmètre :** la CLI locale n'exige volontairement PAS encore de connexion (ne pas verrouiller l'utilisateur hors de son propre outil) ; l'activation des contrôles est reportée à l'API (étape 7).

## API HTTP (api_serveur.py) — décisions durables

API HTTP stdlib pur qui met en service l'auth de l'étape 6. Trois invariants qui doivent survivre à toute évolution :

- **Aucun refus de sécurité ne doit produire une 500.** Jeton absent/invalide/expiré/révoqué → 401 ; rôle insuffisant → 403. Toute `ErreurSecurite` reste confinée dans le handler. Un filet anti-500 enveloppe le routage pour les cas de bord (en-tête malformé, client coupé). **Why:** le « échoue fermé » n'a de valeur que si le serveur ne tombe pas — une 500 non contrôlée = fuite d'info + DoS potentiel.
- **L'API refuse de démarrer sans clé de signature (`SESSION_SECRET`).** Une porte d'auth incapable de vérifier un jeton ne doit pas être exposée.
- **Lancement asynchrone, jamais bloquant.** Produire dure des minutes : l'API génère l'id, lance le pipeline en sous-processus détaché et répond aussitôt ; le client suit via lecture du journal. **Why:** un handler HTTP qui attendrait la fin d'une production monopoliserait un thread des minutes et expirerait côté client.

**How to apply:**
- Nouvelle route protégée = appeler le contrôle de permission en premier et retourner immédiatement s'il refuse ; ne jamais laisser une `ErreurSecurite` s'échapper d'un handler.
- Nouveau droit = éditer `PERMISSIONS` dans securite.py (source unique), pas l'API.
- Testable sans dépendance : construire le serveur sur port 0, injecter la clé de signature à `Securite`, et remplacer `main.py` par un stub côté `config.main_script` (le vrai pipeline exige langchain, l'API non).
- L'API n'ÉCRIT jamais dans `studio.db` (lecture d'historique seule) ; les écritures viennent des sous-processus → voir la note SQLite concurrent ci-dessous.

## Concurrence SQLite (bases partagées entre processus)

`studio.db` (et `securite.db`) sont désormais lus par l'API pendant que des sous-processus écrivent. Deux garde-fous à conserver sur toute connexion partagée : **WAL** (lecteurs + un écrivain simultanés) et **busy_timeout** (attendre une contention au lieu d'échouer). Surtout : dans `journal_production._executer`, un verrou transitoire (`database is locked/busy`) NE doit PAS faire basculer le journal en mode dégradé permanent — sinon une seule contention rend l'API aveugle (listes vides / 404) durablement ; on saute l'opération et la suivante réessaie. **Why:** le mode dégradé est conçu pour les pannes vraies (disque, base corrompue), pas pour la contention normale du multi-processus.

## Agents « logiciels » : ils GÉNÈRENT des scripts, ils n'EXÉCUTENT rien

Les agents créatifs (04 Blender, 05 Unreal, 06 GIMP/Krita/…, 07 FFmpeg, 08 son) produisent des **scripts/fichiers texte** via LLM, sauvegardés dans `output/`, puis affichés comme **commandes headless** prêtes à copier-coller (`utils_headless.py`). Aucun logiciel n'est ouvert automatiquement en local. La seule exécution réelle possible est **déléguée au worker distant** (`worker_distant.py`), sur liste blanche stricte `OUTILS_STUDIO` (blender/unreal/ffmpeg/csound). Il n'existe **aucun** pilotage souris/clavier/logiciel local.

**Why:** rester zéro-dépendance et honnête sur les limites ; ne jamais faire croire qu'un rendu se lance seul. Le worker est le seul point d'exécution, et il est volontairement fermé (liste blanche, jeton).

**How to apply:** nouvel agent « logiciel » = choisir un outil **réellement headless piloté par script** (ex. Csound `.csd` pour la musique : orchestre+partition dans un seul fichier texte, aucun échantillon externe, `csound f.csd -o out.wav`). Le brancher : schéma dans `shared_state.py` (+ validateur de forme), `Etape` `critique=False` dans `construire_pipeline`, callback `_enregistrer_*`, commande dans `utils_headless.py`. Pour l'exécution distante : ajouter l'outil à `OUTILS_STUDIO`, `ConfigWorker`, `outils_disponibles`, `construire_commande`, l'extension de fichier, le flag CLI, et une méthode `executer_<outil>` dans `ExecuteurDistant` + une étape dans `etapes_rendu_distant`.

## Interfaces PWA (étape 9) et bureau (étape 10)

Décisions durables pour les deux interfaces clientes, toutes deux au-dessus de l'API (étape 7), en gardant la philosophie zéro-dépendance.

- **Brique commune `client_api.py` (stdlib urllib)** : cœur client testable (jeton Bearer, JSON, `ErreurAPI(message,code)`). Le bureau l'utilise ; la PWA en fait l'équivalent en JS. Toute évolution de contrat API se répercute ici en premier.
- **PWA servie EN STATIQUE par l'API via liste blanche** (`FICHIERS_PWA` route→(fichier,MIME) dans api_serveur.py) : jamais de chemin construit depuis l'URL → zéro traversée de répertoire. Servie même origine → fetch en chemins relatifs, pas de CORS. Ressources publiques, mais les appels API qu'elles déclenchent restent protégés par jeton. `sw.js` renvoyé avec `Cache-Control: no-cache`.
- **Service worker seulement en contexte sécurisé** (`isSecureContext`) : sur `http://IP:port` (LAN), le navigateur refuse le SW → app utilisable mais NON installable / NON hors-ligne. **Caveat à toujours documenter, ce n'est pas un bug.** Le SW ne cache jamais les appels API (`/connexion`,`/deconnexion`,`/productions`,`/sante`,`/productions/*`).
- **Bureau Tkinter, import Tk gardé (try/except)** : le module reste importable/testable sans écran ; les helpers d'affichage (`libelle_statut`,`formater_duree`,`resumer_production`) sont **purs** et testés séparément. Appels réseau dans un thread + `after` (Tk non thread-safe).
- **Ne jamais stubber les fonctions « vision » non couvertes par l'API** (pilotage/pause/arrêt en cours, gestion agents/mémoire) : elles exigent de nouveaux endpoints → documentées « à venir ». Masquer les actions selon le rôle (ex. cacher « Nouvelle production » si observateur).

**Why:** rester testable dans cet environnement (ni Tk ni langchain requis pour l'infra), et honnête sur les limites (pas d'illusion de fonctionnalité). La liste blanche + secure-context sont des invariants de sécurité, pas des détails.

**How to apply:** nouvelle capacité d'interface = d'abord un endpoint dans api_serveur.py, puis une méthode dans `client_api.py` (+ équivalent JS dans `pwa/app.js`), puis l'UI. Nouveau fichier PWA = l'ajouter à `FICHIERS_PWA` (route+MIME) ET à la coquille de `sw.js`. Icônes régénérables sans dépendance via `pwa/icons/generer_icones.py` (encodeur PNG zlib+struct).

## Human-in-the-loop (--interactif)

Les étapes créatives (01–05) portent `point_validation=True` + `champ_feedback` : après exécution réussie, l'utilisateur valide, demande une révision, ou arrête proprement (`ArretUtilisateur` → exit 0, reprise via `--reprendre`). Les directives de révision sont réinjectées en APPEND dans le kwarg d'entrée désigné par `champ_feedback` — aucun agent ni prompt n'a été modifié.

**Why:** Réinjecter le feedback dans un kwarg textuel existant évite de toucher aux 7 agents ; un arrêt volontaire n'est pas une erreur (exit 0, contrairement à l'échec critique exit 1) ; une révision qui échoue conserve le résultat précédent au lieu de casser le pipeline.

**How to apply:**
- Étape validable = `point_validation=True` + `champ_feedback="<kwarg textuel principal>"` (01→idea, 02→vision_globale, 03→synopsis, 04→screenplay_excerpt, 05→visual_style).
- Les directives s'accumulent entre révisions d'une même étape (l'agent voit tout l'historique).
- EOF sur stdin (pipe/CI) = validation automatique, jamais de crash.
