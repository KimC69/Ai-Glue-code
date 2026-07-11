"""
01_directeur_creatif.py — Agent 01 : Directeur Créatif
Rôle : Transformer une idée brute en vision artistique structurée.
Expose la classe DirecteurCreatif avec la méthode generer_vision().
"""

import os
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import DirectorOutput


SYSTEM_PROMPT = """Tu es un Directeur Créatif cinématographique visionnaire,
inspiré des plus grands réalisateurs (Kubrick, Villeneuve, Lynch).
Tu transformes une idée brute en vision artistique forte et cohérente.

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Idée de film : {idea}

Développe la vision artistique avec précision. Fournis :
- Le genre précis (avec ses sous-genres si nécessaire)
- Le ton émotionnel et atmosphérique (1 phrase)
- La vision artistique globale (3 à 5 phrases percutantes)

{format_instructions}"""


class DirecteurCreatif(BaseAgent):
    """
    Agent 01 — Directeur Créatif.

    Usage :
        boss = DirecteurCreatif()
        vision = boss.generer_vision("Un film sous-marin sur Europa")
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=DirectorOutput,
            agent_id="Agent 01",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def generer_vision(self, idea: str) -> str:
        """
        Génère la vision artistique complète à partir d'une idée de film.

        Args:
            idea: L'idée brute saisie par l'utilisateur

        Returns:
            Une chaîne de texte formatée avec genre, ton et vision globale

        Raises:
            RuntimeError: Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        try:
            response: DirectorOutput = chain.invoke({"idea": idea})
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 01] Échec de la génération de vision : {e}") from e

        # Formatage lisible de la vision pour affichage et sauvegarde dans WorldState
        vision_formatee = (
            f"GENRE   : {response.genre}\n"
            f"TON     : {response.tone}\n"
            f"VISION  :\n{response.director_vision}"
        )

        # On expose aussi les champs bruts pour que main.py puisse les stocker séparément
        self._last_genre = response.genre
        self._last_tone = response.tone
        self._last_vision = response.director_vision

        return vision_formatee

    @property
    def dernier_genre(self) -> str:
        """Genre extrait lors du dernier appel à generer_vision()."""
        return getattr(self, "_last_genre", "")

    @property
    def dernier_ton(self) -> str:
        """Ton extrait lors du dernier appel à generer_vision()."""
        return getattr(self, "_last_tone", "")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    boss = DirecteurCreatif()
    vision = boss.generer_vision("Un astronaute découvre une civilisation sous-marine sur une lune de Jupiter")
    print("\n--- Vision du Directeur Créatif ---")
    print(vision)
