"""
config.py — Configuration portable et déplaçable du Générateur d'Univers.

Tous les chemins sont résolus par rapport à ce fichier, ce qui garantit que
l'application reste 100 % portable d'un PC à l'autre (zip, clé USB, cloud).
Les valeurs par défaut peuvent être surchargées par des variables d'environnement
ou par l'interface Streamlit (onglet Configuration).
"""

import os
from dataclasses import dataclass, field


# Répertoire racine du module univers (agents/univers/)
RACINE_UNIVERS = os.path.dirname(os.path.abspath(__file__))

# Répertoire racine des agents (agents/)
RACINE_AGENTS = os.path.dirname(RACINE_UNIVERS)

# Dossier par défaut des projets, sous `agents/output/projects/` pour rester
# cohérent avec le reste du studio (output partagé).
DOSSIER_DEFAUT = os.path.join(RACINE_AGENTS, "output", "projects")


@dataclass
class ConfigUnivers:
    """Paramètres de connexion aux services externes."""

    # Stable Diffusion
    sd_backend: str = "comfyui"          # "comfyui" | "automatic1111" | "forge"
    sd_url: str = "http://127.0.0.1:8188"  # ComfyUI par défaut
    sd_url_alt: str = "http://127.0.0.1:7860"  # A1111/Forge

    # Civitai
    civitai_url: str = "https://civitai.com/api/v1"
    civitai_api_key: str = ""  # optionnel pour certains téléchargements

    # OpenAI (pour les agents rédacteurs)
    model_openai: str = "gpt-4o-mini"

    # Préférences de génération
    width: int = 768
    height: int = 768
    steps: int = 25
    cfg_scale: float = 7.0
    sampler_name: str = "DPM++ 2M Karras"
    seed: int = -1

    # Fichiers de persistence de la config (un par projet + global)
    def chemin_config(self, slug_projet: str = "") -> str:
        """Chemin du fichier de config JSON."""
        if slug_projet:
            return os.path.join(DOSSIER_DEFAUT, slug_projet, "config.json")
        return os.path.join(RACINE_AGENTS, "output", "config_univers.json")


def config_defaut() -> ConfigUnivers:
    """Renvoie une configuration avec les valeurs d'environnement appliquées."""
    cfg = ConfigUnivers()
    cfg.sd_backend = os.environ.get("STUDIO_SD_BACKEND", cfg.sd_backend).lower()
    cfg.sd_url = os.environ.get("STUDIO_SD_URL", cfg.sd_url)
    cfg.sd_url_alt = os.environ.get("STUDIO_SD_URL_ALT", cfg.sd_url_alt)
    cfg.civitai_url = os.environ.get("STUDIO_CIVITAI_URL", cfg.civitai_url)
    cfg.civitai_api_key = os.environ.get("STUDIO_CIVITAI_API_KEY", cfg.civitai_api_key)
    cfg.model_openai = os.environ.get("STUDIO_MODEL_OPENAI", cfg.model_openai)
    return cfg
