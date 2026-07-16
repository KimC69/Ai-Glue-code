"""
scenariste_univers.py — Agent Scénariste d'Univers.

Lit un fichier de scénario (Markdown/texte) et extrait automatiquement la liste
des entités visuelles à générer : personnages, objets, animaux, végétation,
structures / bâtiments.

Chaque entité est retournée avec :
- nom
- categorie (characters, objects, flora)
- type (Humain, Animal, Arme, Relique, Bâtiment, Plante, etc.)
- description (description brute pour le rédacteur de fiche)
- raison (pourquoi cette entité est importante dans le scénario)
"""

from typing import List

from agent_base import BaseAgent
from pydantic import BaseModel, Field


class EntiteExtraite(BaseModel):
    nom: str = Field(description="Nom exact de l'entité dans le scénario")
    categorie: str = Field(
        description="Catégorie : 'characters' (personnages, animaux, insectes), "
                    "'objects' (objets, armes, bâtiments, structures), "
                    "'flora' (plantes, végétation)")
    type: str = Field(description="Type précis : Humain, Animal, Arme, Relique, Bâtiment, Plante, etc.")
    description: str = Field(
        description="Description brute et complète de l'entité, extraite ou inférée du scénario")
    raison: str = Field(description="Pourquoi cette entité est visuellement importante dans le scénario")


class ExtractionScenario(BaseModel):
    entites: List[EntiteExtraite] = Field(description="Liste des entités visuelles à générer")
    resume: str = Field(description="Résumé du scénario en 2-3 phrases")
    style_univers: str = Field(
        description="Style visuel global de l'univers (épique, post-apo, cyberpunk, etc.)")


class ScenaristeUnivers(BaseAgent):
    """Agent qui analyse un scénario et extrait les entités visuelles à générer."""

    SYSTEM_PROMPT = (
        "Tu es un scénariste technique. Tu lis un scénario de film ou de jeu "
        "et tu en extrais toutes les entités visuelles qui méritent d'être "
        "dessinées : personnages, animaux, créatures, insectes, objets, armes, "
        "reliques, bâtiments, structures, plantes, végétation.\n\n"
        "Règles de catégorisation :\n"
        "- characters : tout être vivant ou personnifié (humain, animal, créature, insecte).\n"
        "- objects : objets, outils, armes, reliques, véhicules, bâtiments, structures.\n"
        "- flora : plantes, arbres, fleurs, végétation.\n\n"
        "Pour chaque entité, donne un nom unique, la catégorie, le type précis, "
        "une description brute complète et la raison de son importance visuelle.\n"
        "Ne crée pas d'entités redondantes. Si un personnage porte un objet, "
        "crée l'objet séparément s'il est important dans l'histoire."
    )

    USER_PROMPT = (
        "Voici le scénario :\n\n"
        "---\n"
        "{scenario}\n"
        "---\n\n"
        "Extrais la liste complète des entités visuelles à générer.\n\n"
        "{format_instructions}"
    )

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        super().__init__(model, temperature, ExtractionScenario, agent_id="Scenariste Univers")
        self.prompt = self._build_prompt(self.SYSTEM_PROMPT, self.USER_PROMPT)

    def analyser(self, chemin_scenario: str) -> ExtractionScenario:
        """Lit un fichier de scénario et retourne les entités extraites."""
        with open(chemin_scenario, "r", encoding="utf-8") as f:
            texte = f.read()

        if not texte.strip():
            raise ValueError(f"Le scénario est vide : {chemin_scenario}")

        chaine = self.prompt | self.llm | self.parser
        return chaine.invoke({
            "scenario": texte,
            "format_instructions": self.base_parser.get_format_instructions(),
        })

    def analyser_texte(self, texte: str) -> ExtractionScenario:
        """Analyse un texte directement (sans fichier)."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(texte)
            chemin = f.name
        try:
            return self.analyser(chemin)
        finally:
            os.unlink(chemin)
