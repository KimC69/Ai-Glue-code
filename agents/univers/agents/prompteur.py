"""
prompteur.py — Agent Prompteur (équivalent Agent 03).

Traduit une fiche JSON d'entité en un prompt Stable Diffusion épuré, strictement
limité à un croquis technique multi-angles (turnaround) isolé sur fond blanc.

Règle absolue : aucune scène, aucun arrière-plan, aucune illustration finale.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent
from univers.schemas import PromptSD


class Prompteur(BaseAgent):
    """Agent qui traduit une fiche d'entité en prompt SD de croquis."""

    SYSTEM_PROMPT = """Tu es un Prompteur pour Stable Diffusion dans un studio de concept art.
Tu reçois une fiche JSON d'entité et tu dois produire un prompt POSITIF et un prompt NÉGATIF
pour générer UNIQUEMENT des croquis techniques précis et détourés.

Règles ABSOLUES à respecter impérativement :
1. Le prompt doit cibler un croquis technique isolé : pencil sketch, technical drawing, line art, orthographic turnaround, front view, side view, back view, isolated on white background, no background, no environment.
2. NE JAMAIS inclure de scène, d'arrière-plan, de paysage, de décor, d'éléments inutiles.
3. NE JAMAIS demander une illustration finale, une peinture, des couleurs ou un rendu réaliste.
4. Le sujet doit être décrit avec ses tags visuels exacts (physique, proportions, traits distinctifs).
5. Le prompt négatif doit interdire : background, scene, landscape, environment, colors, painting, blurry, low quality, extra limbs, deformed.
6. Longueur du prompt positif : 50-100 tokens. Reste concis et technique.

Sortie JSON avec les clés : "positive", "negative", "parametres" (optionnel).
"""

    USER_PROMPT = """Fiche d'entité au format JSON :
{json_fiche}

{format_instructions}
"""

    def __init__(self, model="gpt-4o-mini", temperature=0.4):
        super().__init__(model, temperature, PromptSD, agent_id="Prompteur")
        self.prompt = self._build_prompt(self.SYSTEM_PROMPT, self.USER_PROMPT)

    def traduire(self, fiche: dict) -> PromptSD:
        """Convertit une fiche dict en prompt SD."""
        import json
        chaine = self.prompt | self.llm | self.parser
        return chaine.invoke({
            "json_fiche": json.dumps(fiche, ensure_ascii=False, indent=2),
        })

    def discuter(self, message: str, role: str = "", contexte: str = "") -> str:
        return super().discuter(message, role or "Prompteur", contexte)
