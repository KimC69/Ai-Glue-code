"""
sd_client.py — Client unifié pour Stable Diffusion (ComfyUI / AUTOMATIC1111 / Forge).

Détecte automatiquement le backend disponible, envoie les prompts et rapatrie
l'image générée. Conçu pour les croquis techniques isolés : pas de scène, pas
d'arrière-plan, pas d'illustration finale.
"""

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

from .config import ConfigUnivers


class ErreurSD(Exception):
    """Erreur de communication avec Stable Diffusion."""


class StableDiffusionClient:
    """Client Stable Diffusion capable de parler à ComfyUI ou à A1111/Forge."""

    def __init__(self, config: ConfigUnivers):
        self.config = config
        self.backend = config.sd_backend
        self.url = config.sd_url
        self._detecte_si_necessaire()

    # ── Détection du backend ───────────────────────────────────────────────

    def _detecte_si_necessaire(self) -> None:
        """Si le backend est 'auto', tente de détecter ComfyUI puis A1111."""
        if self.backend != "auto":
            return
        if self._ping("http://127.0.0.1:8188/system_stats"):
            self.backend = "comfyui"
            self.url = "http://127.0.0.1:8188"
            return
        if self._ping("http://127.0.0.1:7860/sdapi/v1/samplers"):
            self.backend = "automatic1111"
            self.url = "http://127.0.0.1:7860"
            return
        raise ErreurSD(
            "Aucun backend Stable Diffusion détecté. "
            "Lancez ComfyUI (8188) ou A1111/Forge (7860), ou vérifiez la configuration.")

    def _ping(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def _post(self, endpoint: str, payload: dict) -> dict:
        """POST JSON générique."""
        url = f"{self.url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise ErreurSD(f"SD HTTP {e.code}: {body}") from e
        except Exception as e:
            raise ErreurSD(f"Impossible de contacter SD à {url}: {e}") from e

    def _get(self, endpoint: str) -> dict:
        """GET JSON générique."""
        url = f"{self.url}{endpoint}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise ErreurSD(f"Impossible de contacter SD à {url}: {e}") from e

    # ── API publique : génération d'image ───────────────────────────────────

    def generer_image(self, prompt_positif: str, prompt_negatif: str = "",
                      width: int = 768, height: int = 768,
                      steps: int = 25, cfg_scale: float = 7.0,
                      sampler_name: str = "DPM++ 2M Karras",
                      seed: int = -1,
                      chemin_sortie: str = "output.png") -> dict:
        """Génère une image et l'écrit sur le disque. Retourne les métadonnées."""
        os.makedirs(os.path.dirname(chemin_sortie) or ".", exist_ok=True)
        debut = time.time()

        if self.backend == "comfyui":
            return self._generer_comfyui(
                prompt_positif, prompt_negatif, width, height, steps,
                cfg_scale, sampler_name, seed, chemin_sortie, debut)

        return self._generer_a1111(
            prompt_positif, prompt_negatif, width, height, steps,
            cfg_scale, sampler_name, seed, chemin_sortie, debut)

    # ── ComfyUI ─────────────────────────────────────────────────────────────

    def _generer_comfyui(self, positive: str, negative: str, width: int, height: int,
                         steps: int, cfg: float, sampler: str, seed: int,
                         chemin_sortie: str, debut: float) -> dict:
        """Utilise un workflow minimaliste KSampler + Empty Latent + Save Image."""
        # Génère un workflow JSON dynamique pour un simple txt2img
        workflow = self._workflow_comfyui_minimal(
            positive, negative, width, height, steps, cfg, sampler, seed)
        payload = {"prompt": workflow}
        resp = self._post("/prompt", payload)
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            raise ErreurSD(f"ComfyUI n'a pas renvoyé de prompt_id : {resp}")

        # Attente du résultat
        image_data = self._attendre_image_comfyui(prompt_id)
        with open(chemin_sortie, "wb") as f:
            f.write(image_data)

        duree = time.time() - debut
        return {
            "chemin": chemin_sortie,
            "seed": seed if seed != -1 else "aléatoire",
            "duree_s": duree,
            "backend": "comfyui",
        }

    def _workflow_comfyui_minimal(self, positive: str, negative: str, width: int,
                                   height: int, steps: int, cfg: float,
                                   sampler_name: str, seed: int) -> dict:
        """Construit un workflow ComfyUI simple en mémoire."""
        # Mapping basique des noms de samplers ComfyUI
        sampler_map = {
            "DPM++ 2M Karras": "dpmpp_2m",
            "Euler a": "euler_ancestral",
            "Euler": "euler",
            "DPM++ SDE Karras": "dpmpp_sde",
        }
        sampler = sampler_map.get(sampler_name, "dpmpp_2m")
        scheduler = "karras" if "Karras" in sampler_name else "normal"

        # IDs arbitraires mais cohérents
        return {
            "1": {
                "inputs": {"text": positive, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
            },
            "2": {
                "inputs": {"text": negative, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
            },
            "3": {
                "inputs": {
                    "seed": seed if seed != -1 else int(time.time() * 1000) % 2**32,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "4": {
                "inputs": {"ckpt_name": self._modele_comfyui_defaut()},
                "class_type": "CheckpointLoaderSimple",
            },
            "5": {
                "inputs": {"width": width, "height": height, "batch_size": 1},
                "class_type": "EmptyLatentImage",
            },
            "6": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode",
            },
            "7": {
                "inputs": {"filename_prefix": "sketch", "images": ["6", 0]},
                "class_type": "SaveImage",
            },
        }

    def _modele_comfyui_defaut(self) -> str:
        """Renvoie le premier checkpoint disponible sur ComfyUI."""
        try:
            data = self._get("/object_info/CheckpointLoaderSimple")
            models = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
            return models[0] if models else "model.safetensors"
        except Exception:
            return "model.safetensors"

    def _attendre_image_comfyui(self, prompt_id: str, timeout: int = 300) -> bytes:
        """Attend que l'historique ComfyUI contienne l'image et la télécharge."""
        debut = time.time()
        while time.time() - debut < timeout:
            time.sleep(1)
            hist = self._get(f"/history/{prompt_id}")
            entry = hist.get(prompt_id, {})
            outputs = entry.get("outputs", {})
            for node_id, node_out in outputs.items():
                images = node_out.get("images", [])
                if images:
                    img = images[0]
                    filename = img.get("filename")
                    subfolder = img.get("subfolder", "")
                    ptype = img.get("type", "output")
                    params = urllib.parse.urlencode({
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": ptype,
                    })
                    url = f"{self.url}/view?{params}"
                    with urllib.request.urlopen(url, timeout=60) as r:
                        return r.read()
        raise ErreurSD(f"ComfyUI n'a pas produit d'image dans le délai imparti ({timeout}s).")

    # ── AUTOMATIC1111 / Forge ─────────────────────────────────────────────

    def _generer_a1111(self, positive: str, negative: str, width: int, height: int,
                       steps: int, cfg: float, sampler: str, seed: int,
                       chemin_sortie: str, debut: float) -> dict:
        """Utilise l'API txt2img d'A1111."""
        payload = {
            "prompt": positive,
            "negative_prompt": negative,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        resp = self._post("/sdapi/v1/txt2img", payload)
        images = resp.get("images", [])
        if not images:
            raise ErreurSD("A1111 n'a pas renvoyé d'image.")

        import base64
        image_data = base64.b64decode(images[0].split(",")[-1])
        with open(chemin_sortie, "wb") as f:
            f.write(image_data)

        duree = time.time() - debut
        return {
            "chemin": chemin_sortie,
            "seed": resp.get("parameters", {}).get("seed", seed),
            "duree_s": duree,
            "backend": self.backend,
        }

    # ── Chargement d'un modèle (checkpoint) ─────────────────────────────────

    def charger_modele(self, nom_checkpoint: str) -> None:
        """Demande au backend de charger un checkpoint spécifique."""
        if self.backend == "comfyui":
            # ComfyUI charge le modèle dans le workflow ; rien à faire globalement.
            return
        # A1111/Forge : POST /sdapi/v1/options
        self._post("/sdapi/v1/options", {"sd_model_checkpoint": nom_checkpoint})

    def lister_modeles_disponibles(self) -> list:
        """Liste les checkpoints disponibles sur le backend."""
        try:
            if self.backend == "comfyui":
                data = self._get("/object_info/CheckpointLoaderSimple")
                models = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                return models
            data = self._get("/sdapi/v1/sd-models")
            return [m.get("title", "") for m in data if isinstance(m, dict)]
        except Exception:
            return []
