"""
dessinateur_sd.py — Agent Dessinateur SD (équivalent Agent 04).

Envoie le prompt à l'API de Stable Diffusion, récupère le croquis technique
généré et le range dans le dossier `/projects/[projet]/sketches/[categorie]/`.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent
from univers.sd_client import StableDiffusionClient, ErreurSD
from univers.config import ConfigUnivers


class DessinateurSD(BaseAgent):
    """Agent qui génère un croquis via Stable Diffusion."""

    def __init__(self, config: ConfigUnivers, model="gpt-4o-mini", temperature=0.0):
        # L'agent Dessinateur n'a pas besoin de LLM pour sa tâche principale,
        # mais hérite de BaseAgent pour le chat et la cohérence du studio.
        super().__init__(model, temperature, dict, agent_id="Dessinateur SD")
        self.config = config
        self.client = StableDiffusionClient(config)

    def dessiner(self, prompt_positif: str, prompt_negatif: str,
                 chemin_sortie: str, modele_checkpoint: str = "") -> dict:
        """Génère une image et l'enregistre sur le disque."""
        if modele_checkpoint:
            try:
                self.client.charger_modele(modele_checkpoint)
            except ErreurSD as e:
                # On ne bloque pas : le backend utilisera son modèle par défaut.
                return {"success": False, "warning": f"Chargement modèle impossible : {e}"}

        try:
            resultat = self.client.generer_image(
                prompt_positif=prompt_positif,
                prompt_negatif=prompt_negatif,
                width=self.config.width,
                height=self.config.height,
                steps=self.config.steps,
                cfg_scale=self.config.cfg_scale,
                sampler_name=self.config.sampler_name,
                seed=self.config.seed,
                chemin_sortie=chemin_sortie,
            )
            resultat["success"] = True
            return resultat
        except ErreurSD as e:
            return {"success": False, "error": str(e)}

    def discuter(self, message: str, role: str = "", contexte: str = "") -> str:
        return super().discuter(message, role or "Dessinateur SD", contexte)
