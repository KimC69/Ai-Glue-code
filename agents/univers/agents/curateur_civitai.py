"""
curateur_civitai.py — Agent Curateur Civitai (équivalent Agent 02).

Reçoit la direction artistique, interroge l'API Civitai, sélectionne le meilleur
modèle (ex : pencil sketch), télécharge le fichier .safetensors dans le dossier
`/projects/[projet]/models/`, et prépare le chargement auprès de Stable Diffusion.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent
from univers.civitai_client import CivitaiClient, ErreurCivitai
from univers.config import ConfigUnivers
from pydantic import BaseModel, Field


class CurateurCivitai(BaseAgent):
    """Agent qui trouve et télécharge les modèles de style Civitai."""

    SYSTEM_PROMPT = """Tu es un Curateur de Modèles Civitai pour un studio de génération d'images IA.
On te donne une fiche d'entité et tu dois choisir les meilleurs mots-clés pour
chercher un modèle Stable Diffusion adapté à un croquis technique.

Règles :
- Privilégie les mots-clés en anglais.
- Cible un modèle de style "pencil sketch", "line art", "technical drawing", "concept art sketch".
- Ne renvoie que la QUERY de recherche (3-6 mots-clés) et le TYPE de modèle (Checkpoint ou LORA).

Sortie JSON obligatoire avec deux clés : "query" et "type_modele".
"""

    USER_PROMPT = """Fiche d'entité :
{json_fiche}

{format_instructions}
"""

    def __init__(self, config: ConfigUnivers, model="gpt-4o-mini", temperature=0.3):
        super().__init__(model, temperature, _CivitaiSearchQuery, agent_id="Curateur Civitai")
        self.config = config
        self.client = CivitaiClient(config)
        self.prompt = self._build_prompt(self.SYSTEM_PROMPT, self.USER_PROMPT)

    def preparer_recherche(self, json_fiche: str) -> dict:
        """Génère la query de recherche optimale pour Civitai."""
        chaine = self.prompt | self.llm | self.parser
        resultat = chaine.invoke({"json_fiche": json_fiche})
        return {"query": resultat.query, "type_modele": resultat.type_modele}

    def trouver_et_telecharger(self, projet: dict, json_fiche: dict) -> dict:
        """Pipeline complet : recherche Civitai + téléchargement dans le projet."""
        query_data = self.preparer_recherche(json.dumps(json_fiche, ensure_ascii=False))
        query = query_data.get("query", "pencil sketch")
        model_type = query_data.get("type_modele", "Checkpoint")

        modele = self.client.selectionner_meilleur(query, style_cible="pencil sketch")
        if not modele:
            return {
                "success": False,
                "query": query,
                "error": "Aucun modèle .safetensors trouvé sur Civitai pour cette recherche.",
            }

        dossier_modeles = os.path.join(projet["chemin"], "models")
        os.makedirs(dossier_modeles, exist_ok=True)
        chemin_local = os.path.join(dossier_modeles, modele["fichier_nom"])

        try:
            self.client.telecharger_modele(modele["download_url"], chemin_local)
        except ErreurCivitai as e:
            return {
                "success": False,
                "query": query,
                "modele": modele,
                "error": str(e),
            }

        return {
            "success": True,
            "query": query,
            "modele": modele,
            "chemin_local": chemin_local,
            "nom_checkpoint": modele["fichier_nom"],
        }

    def discuter(self, message: str, role: str = "", contexte: str = "") -> str:
        return super().discuter(message, role or "Curateur Civitai", contexte)


class _CivitaiSearchQuery(BaseModel):
    query: str = Field(description="Query de recherche Civitai en anglais, 3-6 mots-clés")
    type_modele: str = Field(default="Checkpoint", description="Type de modèle : Checkpoint ou LORA")
