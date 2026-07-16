"""
civitai_client.py — Recherche et téléchargement de modèles sur Civitai.

L'Agent Curateur l'utilise pour trouver un modèle adapté à la direction
artistique (ex : pencil sketch), le télécharger dans le dossier du projet, puis
en informer Stable Diffusion.
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

from .config import ConfigUnivers


class ErreurCivitai(Exception):
    """Erreur lors de l'appel à l'API Civitai."""


class CivitaiClient:
    """Client minimal pour l'API publique de Civitai."""

    def __init__(self, config: ConfigUnivers):
        self.config = config
        self.base_url = config.civitai_url.rstrip("/")
        self.api_key = config.civitai_api_key

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise ErreurCivitai(f"Civitai HTTP {e.code}: {body}") from e
        except Exception as e:
            raise ErreurCivitai(f"Erreur Civitai {url}: {e}") from e

    def chercher_modele(self, query: str, model_type: str = "Checkpoint",
                        sort: str = "Highest Rated", limit: int = 5) -> dict:
        """Interroge Civitai pour trouver des modèles correspondant à `query`."""
        params = {
            "query": query,
            "types": model_type,
            "sort": sort,
            "limit": limit,
            "nsfw": "false",
        }
        return self._get("/models", params)

    def selectionner_meilleur(self, query: str, style_cible: str = "pencil sketch") -> Optional[dict]:
        """Cherche le meilleur modèle et retourne les métadonnées du premier
        fichier .safetensors disponible."""
        data = self.chercher_modele(query)
        items = data.get("items", [])
        if not items:
            return None

        for modele in items:
            modele_id = modele.get("id")
            nom = modele.get("name", "modele")
            for version in modele.get("modelVersions", []):
                for fichier in version.get("files", []):
                    if fichier.get("name", "").endswith(".safetensors"):
                        return {
                            "id": modele_id,
                            "nom": nom,
                            "version_id": version.get("id"),
                            "version_nom": version.get("name", ""),
                            "fichier_nom": fichier.get("name"),
                            "download_url": fichier.get("downloadUrl"),
                            "format": fichier.get("format", "SafeTensor"),
                            "type": modele.get("type", "Checkpoint"),
                            "description_courte": (modele.get("description") or "")[:200],
                        }
        return None

    def telecharger_modele(self, url: str, chemin_sortie: str) -> str:
        """Télécharge un fichier .safetensors depuis Civitai."""
        os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
        headers = {"Accept": "application/octet-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                with open(chemin_sortie, "wb") as f:
                    while True:
                        chunk = r.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            return chemin_sortie
        except Exception as e:
            raise ErreurCivitai(f"Échec du téléchargement Civitai : {e}") from e
