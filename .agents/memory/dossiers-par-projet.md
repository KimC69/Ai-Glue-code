---
name: Dossiers par projet + mode suite/inspiration
description: Comment un film est isolé dans output/projets/<slug>/ et comment une suite réutilise l'état d'un projet source.
---

# Dossiers par projet et écriture d'une suite (projet `agents/`)

## Règle
- **Projet = archive créative par dossier** `output/projets/<slug>/` : scripts générés, `meta.json`, `world_state.json` (archivé en fin de production).
- **Le `world_state.json` global (`output/world_state.json`) reste VIVANT et global** pendant la production → `/memoire` et `/memoire/reset` inchangés.
- **Journal (`studio.db`, `journaux/`), comptes, objectifs, canal de pilotage restent GLOBAUX.** Seule une colonne `projet` (nullable) est ajoutée à la table `productions` pour la traçabilité (migration idempotente via `ALTER TABLE ADD COLUMN`, car `CREATE TABLE IF NOT EXISTS` ne modifie pas une table existante).
- **Scripts project-aware via variable d'env** : `shared_state.dossier_sortie()` lit `STUDIO_OUTPUT_DIR` (sinon `agents/output`). `main.py` positionne `STUDIO_OUTPUT_DIR` = dossier du projet quand `--projet` est actif. Les agents 04–08 appellent `dossier_sortie()` au lieu d'un chemin codé en dur.
- **Archivage depuis l'état EN MÉMOIRE** : `projets.archiver_etat(slug, state.to_dict())`, PAS une copie du fichier global.

**Why:** deux réserves d'une revue architecte. (1) `--projet` redirigeait `OUTPUT_DIR` côté `main.py` mais les agents écrivaient en dur dans `agents/output/` → films non isolés. (2) Copier le `world_state.json` global en fin de production peut archiver l'état d'une AUTRE production concurrente (le fichier global est partagé) ; l'objet `state` en mémoire est propre au processus, donc correct sous concurrence.

**How to apply:** tout nouvel agent qui écrit un fichier de sortie doit passer par `shared_state.dossier_sortie()`. Toute archive « par production » doit venir de l'état en mémoire, jamais du fichier global partagé.

## Mode suite / inspiration
- CLI `--inspiration`/`--suite-de <projet>` (API : champ `inspiration`) lit le `world_state.json` archivé du projet source, construit un bloc RÉFÉRENCE (clés créatives seulement : synopsis, personnages, style… ; scripts techniques exclus, valeurs tronquées) et l'injecte dans `_idee_avec_objectifs` (ordre : idée → RÉFÉRENCE-suite → OBJECTIFS).
- **Échoue-fermé** : projet source absent/sans état → refus explicite (`404` API, erreur + exit CLI). Jamais de fausse « non-suite ». Incompatible avec `--reprendre`.
- Rétrocompat impérative : sans `--projet`, comportement historique (tout dans `output/`).

## Sécurité
- `slugifier` restreint à `[a-z0-9-]` (accents translittérés) → pas de path traversal via le slug.
