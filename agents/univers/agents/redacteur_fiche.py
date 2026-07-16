"""
redacteur_fiche.py — Agent Rédacteur de Fiches (équivalent Agent 01 : Lore).

Génère une fiche JSON d'identité complète pour une entité de l'univers
(humain, animal, insecte, objet, plante). La fiche est ensuite enregistrée dans
`/projects/[projet]/universe_bible/[categorie]/`.
"""

import sys
import os

# Import relatif depuis agents/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent
from univers.schemas import FicheEntite


class RedacteurFiche(BaseAgent):
    """Agent qui rédige les fiches JSON de la bible de l'univers."""

    SYSTEM_PROMPT = """Tu es un Rédacteur de Fiches d'Univers pour un studio de création.
Le producteur te donne une idée d'entité (nom, type, catégorie, description brute).
Tu dois produire une fiche d'identité complète et structurée en JSON.

Règles strictes :
- La catégorie doit être exactement l'une de : characters, objects, flora.
- Le type précise la nature : Humain, Animal, Insecte, Objet, Plante, Arbre, etc.
- Donne des mesures physiques crédibles (taille_cm, poids_kg) quand c'est pertinent.
- Décris l'apparence avec suffisamment de détails pour un dessinateur technique.
- Le lore doit être court (1-2 phrases) mais mémorable.
- Les tags_visuels doivent être des mots-clés bruts, en anglais, adaptés à un prompt Stable Diffusion.
- Le style_souhaite doit orienter vers un croquis technique isolé (pencil sketch, technical drawing, white background, isolated subject).

Ne génère JAMAIS de scène, d'arrière-plan ou d'illustration finale : uniquement la fiche descriptive.
"""

    USER_PROMPT = """Rédige la fiche d'identité complète pour cette entité :

Nom : {nom}
Catégorie : {categorie}
Type : {type}
Description brute : {description}

{format_instructions}
"""

    def __init__(self, model="gpt-4o-mini", temperature=0.7):
        super().__init__(model, temperature, FicheEntite, agent_id="Rédacteur de Fiche")
        self.prompt = self._build_prompt(self.SYSTEM_PROMPT, self.USER_PROMPT)

    def rediger(self, nom: str, categorie: str, type_entite: str,
                description: str) -> FicheEntite:
        """Génère une fiche structurée à partir d'une description brute."""
        chaine = self.prompt | self.llm | self.parser
        return chaine.invoke({
            "nom": nom,
            "categorie": categorie,
            "type": type_entite,
            "description": description,
        })

    def discuter(self, message: str, role: str = "", contexte: str = "") -> str:
        return super().discuter(message, role or "Rédacteur de Fiche", contexte)
