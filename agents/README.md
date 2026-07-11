# Système Multi-Agents Cinématographique — LangChain

Un pipeline de production de films automatisé avec 7 agents IA spécialisés.

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
```

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
| `utils_headless.py` | Génère les commandes headless (Blender, Unreal, GIMP, montage, export FFmpeg) prêtes à copier-coller |
| `main.py` | Orchestrateur — `lancer_studio()` lie les 7 agents via `WorldState` |

Chaque agent expose une classe avec une méthode métier dédiée (`generer_vision()`,
`construire_structure()`, `ecrire_scenario()`, `creer_scene_blender()`,
`creer_setup_unreal()`, `analyser_conformite()`, `generer_exports()`). Les
fichiers commencent par un chiffre pour l'ordre de lecture ; `main.py` les
charge via `importlib.util` car Python n'autorise pas `import 01_...`
directement.

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
