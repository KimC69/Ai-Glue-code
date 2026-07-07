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
| `shared_state.py` | Schéma Pydantic — état partagé entre agents |
| `01_directeur.py` | Agent 01 — Vision artistique globale |
| `02_architecte_narratif.py` | Agent 02 — Structure dramaturgique |
| `03_scenariste.py` | Agent 03 — Scénario et personnages |
| `04_directeur_artistique.py` | Agent 04 — Script Python Blender |
| `05_directeur_technique.py` | Agent 05 — Script Shell Unreal Engine |
| `main.py` | Orchestrateur — lie tous les agents en chaîne |

## Tester un agent seul

Chaque agent peut être lancé indépendamment pour tester :

```bash
cd agents/
python 01_directeur.py
python 04_directeur_artistique.py
```

## Points d'attention LangChain

- **Tokens** : le pipeline complet consomme ~3000-6000 tokens par exécution avec `gpt-4o-mini`
- **Parseurs Pydantic** : si un agent renvoie un JSON malformé, LangChain lèvera une `OutputParserException`
- **Version** : le projet cible `langchain>=0.2.0` — évitez de monter en version sans tester
