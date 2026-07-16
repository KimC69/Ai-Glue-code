---
name: Générateur d'Univers
description: Workflow indépendant de génération de fiches + croquis techniques Stable Diffusion, cloisonné par projet.
---

# Générateur d'Univers

## Règle d'architecture

Le Générateur d'Univers est un **workflow indépendant** du pipeline cinéma (agents 01-08). Il vit dans `agents/univers/` et a son propre point d'entrée (`agents/generateur_univers.py` en CLI, `agents/streamlit_app.py` en interface).

**Why :** l'utilisateur a explicitement demandé un nouveau workflow d'agents dédiés à la génération d'univers, sans réutiliser la numérotation des agents cinéma. Mélanger les deux aurait cassé le pipeline existant et rendu le code incompréhensible.

## Structure de dossiers imposée

Tout est cloisonné par projet sous `agents/output/projects/[slug]/` :

- `universe_bible/{characters,objects,flora}/` : fiches JSON
- `sketches/{characters,objects,flora}/` : croquis PNG
- `models/` : modèles `.safetensors` téléchargés depuis Civitai

## Règle absolue sur les générations

Les prompts SD sont contraints à des **croquis techniques isolés** uniquement : `pencil sketch, technical drawing, isolated on white background`. Les prompts négatifs interdisent arrière-plans, scènes, couleurs, illustrations finales.

**Why :** directive utilisateur pour économiser le temps GPU et éviter les générations inutiles.

## Dépendances

Le workflow utilise les mêmes dépendances LangChain/OpenAI que le pipeline cinéma. **Version bloquée** : `langchain>=0.2.0,<1.0.0` ; les versions 1.x+ déplacent/suppriment `langchain.prompts` et cassent `agent_base.py`.

**How to apply :** si un futur agent doit importer `ChatPromptTemplate`, utiliser `from langchain.prompts import ChatPromptTemplate` (valide en 0.2.x) ; ne pas upgrader langchain sans tester `main.py` et `streamlit_app.py`.

## Interface

- Streamlit : workflow `Studio IA - Generateur dUnivers` configuré sur le port 5000.
- CLI : `python agents/generateur_univers.py --projet ... --nom ... --categorie ...`.
- Le workflow Streamlit doit être lancé avec `--server.headless true --browser.gatherUsageStats false` (ou un fichier `.streamlit/config.toml`) pour éviter le prompt d'onboarding email qui bloque le démarrage non-interactif.