# Système Multi-Agents Cinématographique — LangChain

Un pipeline de production de films automatisé avec 5 agents IA spécialisés.

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
  output/
    ├── rapport_production_YYYYMMDD_HHMMSS.md
    ├── state_YYYYMMDD_HHMMSS.json
    ├── scene_01_opening.py   (script Blender)
    └── setup_scene_01.sh     (script Unreal)
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
| `01_directeur_creatif.py` | Agent 01 — classe `DirecteurCreatif` : vision, genre, ton |
| `02_architecte_narratif.py` | Agent 02 — classe `ArchitecteNarratif` : synopsis, actes, scènes clés |
| `03_scenariste.py` | Agent 03 — classe `Scenariste` : fiches personnages, extrait scénario |
| `04_directeur_artistique.py` | Agent 04 — classe `DirecteurArtistique` : script Python Blender |
| `05_directeur_technique.py` | Agent 05 — classe `DirecteurTechnique` : script Shell Unreal Engine |
| `06_superviseur_post_production.py` | Agent 06 — classe `SuperviseurPostProduction` : audit de conformité, déclenche GIMP/montage **seulement si nécessaire** |
| `utils_headless.py` | Génère les commandes headless (Blender, Unreal, GIMP, montage) prêtes à copier-coller |
| `main.py` | Orchestrateur — `lancer_studio()` lie les 6 agents via `WorldState` |

Chaque agent expose une classe avec une méthode métier dédiée (`generer_vision()`,
`construire_structure()`, `ecrire_scenario()`, `creer_scene_blender()`,
`creer_setup_unreal()`, `analyser_conformite()`). Les fichiers commencent par un
chiffre pour l'ordre de lecture ; `main.py` les charge via `importlib.util` car
Python n'autorise pas `import 01_...` directement.

### Agent 06 — Superviseur Post-Production (conditionnel)

Ce dernier agent n'exécute jamais un outil "juste au cas où". Il audite le
résultat des Agents 04/05 et ne déclenche que ce qui est réellement
nécessaire :

- **GIMP** (retouche image) — uniquement si un écart visuel doit être corrigé.
  Un script Python-Fu est sauvegardé dans `output/retouche_gimp.py`.
- **Kdenlive / Shotcut** (montage) — uniquement si un assemblage est requis
  pour rendre le rendu final conforme. Les instructions sont sauvegardées
  dans `output/notes_montage.txt` (ces logiciels n'ont pas de vrai mode
  headless : ils reposent sur le moteur MLT, d'où l'usage de `melt` pour un
  rendu automatisé une fois le projet construit).

Si le résultat est déjà cohérent, aucun outil n'est proposé — seuls
Blender et Unreal Engine (déjà générés par les Agents 04/05) apparaissent
dans le récapitulatif final.

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
