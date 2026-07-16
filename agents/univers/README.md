# Studio IA - Générateur d'Univers

Nouveau workflow indépendant du pipeline cinéma (agents 01-08). Il génère, par projet cloisonné, des fiches d'identité JSON et des croquis techniques via Stable Diffusion.

## Structure par projet

```
agents/output/projects/[NOM_DU_PROJET]/
├── universe_bible/
│   ├── characters/     # Fiches JSON (humains, animaux, insectes)
│   ├── objects/        # Fiches JSON (reliques, outils)
│   └── flora/          # Fiches JSON (végétation)
├── sketches/
│   ├── characters/     # Croquis PNG
│   ├── objects/
│   └── flora/
└── models/             # Modèles .safetensors téléchargés depuis Civitai
```

## Agents du workflow

- **Rédacteur de Fiche** — génère une fiche JSON structurée (physique, lore, tags visuels).
- **Curateur Civitai** — recherche et télécharge un modèle de style adapté.
- **Prompteur** — traduit la fiche en un prompt Stable Diffusion strictement limité à un croquis technique isolé.
- **Dessinateur SD** — génère le croquis via ComfyUI ou AUTOMATIC1111/Forge.
- **Découpeur 3D** — découpe le croquis en vues orthographiques (face, profil, dos).

## Lancement

### Interface Streamlit (recommandée)

```bash
cd agents
streamlit run streamlit_app.py --server.port 5000
```

Dans l'environnement Replit, le workflow **Studio IA - Générateur d'Univers** est déjà configuré.

### Ligne de commande

```bash
cd agents
python generateur_univers.py \
  --projet "MonJeu" \
  --nom "Kael" \
  --categorie characters \
  --type "Humain" \
  --description "Guerrier aux cheveux blancs, manteau en cuir, cicatrice sous l'œil gauche"

# Mode scénario (génère toutes les entités automatiquement)
python generateur_univers.py --scenario \
  --projet "MonFilm" \
  --fichier-scenario "output/projects/MonFilm/scenario.md"
```

Le mode scénario lit un fichier Markdown (ou texte), détecte automatiquement les
personnages, objets, bâtiments et végétation, puis génère chaque entité l'une
après l'autre sans intervention.

Options utiles :
- `--no-sd` : génère uniquement la fiche JSON
- `--no-civitai` : ne télécharge pas de modèle Civitai
- `--no-decoupe` : ne découpe pas le croquis
- `--model gpt-4o` : force un modèle OpenAI

## Configuration

Variables d'environnement (facultatives) :
- `STUDIO_SD_BACKEND` : `comfyui` (défaut), `automatic1111`, `forge` ou `auto`
- `STUDIO_SD_URL` : URL de ComfyUI (défaut `http://127.0.0.1:8188`)
- `STUDIO_SD_URL_ALT` : URL d'A1111/Forge (défaut `http://127.0.0.1:7860`)
- `STUDIO_CIVITAI_URL` : URL de l'API Civitai
- `STUDIO_CIVITAI_API_KEY` : clé API Civitai (optionnel)
- `STUDIO_MODEL_OPENAI` : modèle OpenAI pour les agents rédacteurs

## Prérequis réseau

- **Stable Diffusion** : ComfyUI ou A1111/Forge doit être lancé en local ou sur une machine accessible.
- **Civitai** : connexion Internet (téléchargement de modèles).
- **OpenAI** : clé personnelle ou intégration Replit AI activée.

## Règles de génération

Les prompts imposent systématiquement :
- `pencil sketch, technical drawing, isolated on white background`
- un `negative prompt` interdisant arrière-plans, scènes, couleurs et illustrations finales.

Aucune scène complexe, aucun paysage, aucune illustration finale n'est générée.
