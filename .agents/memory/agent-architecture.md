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

## Human-in-the-loop (--interactif)

Les étapes créatives (01–05) portent `point_validation=True` + `champ_feedback` : après exécution réussie, l'utilisateur valide, demande une révision, ou arrête proprement (`ArretUtilisateur` → exit 0, reprise via `--reprendre`). Les directives de révision sont réinjectées en APPEND dans le kwarg d'entrée désigné par `champ_feedback` — aucun agent ni prompt n'a été modifié.

**Why:** Réinjecter le feedback dans un kwarg textuel existant évite de toucher aux 7 agents ; un arrêt volontaire n'est pas une erreur (exit 0, contrairement à l'échec critique exit 1) ; une révision qui échoue conserve le résultat précédent au lieu de casser le pipeline.

**How to apply:**
- Étape validable = `point_validation=True` + `champ_feedback="<kwarg textuel principal>"` (01→idea, 02→vision_globale, 03→synopsis, 04→screenplay_excerpt, 05→visual_style).
- Les directives s'accumulent entre révisions d'une même étape (l'agent voit tout l'historique).
- EOF sur stdin (pipe/CI) = validation automatique, jamais de crash.
