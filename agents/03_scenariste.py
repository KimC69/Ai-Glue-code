"""
03_scenariste.py — Agent 03 : Scénariste
Rôle : Écrire les fiches personnages et l'extrait de scénario format Hollywood.
Expose la classe Scenariste avec la méthode ecrire_scenario().
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import ScreenwriterOutput


SYSTEM_PROMPT = """Tu es un Scénariste professionnel formé au format Hollywood standard.
Tu écris des dialogues naturels et percutants, des directions de jeu précises.
Tu crées des personnages complexes avec des motivations profondes et des contradictions internes.

Format scénario obligatoire :
- INT./EXT. LIEU - MOMENT  pour les descriptions de scène
- NOM DU PERSONNAGE (centré, en majuscules) pour introduire un dialogue
- (entre parenthèses) pour les didascalies de jeu

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Synopsis : {synopsis}

Structure en actes : {acts}

Scènes clés : {key_scenes}

Écris exactement :
- character_sheet : fiche de chaque personnage principal
  (nom, âge, background en 1 phrase, motivation profonde, faille humaine)
- screenplay_excerpt : extrait de scénario complet de la scène d'ouverture
  en format Hollywood (au moins 20 lignes : actions + dialogues)

{format_instructions}"""


class Scenariste:
    """
    Agent 03 — Scénariste.

    Lit la structure narrative dans WorldState, produit les fiches
    personnages et l'extrait de scénario format Hollywood.

    Usage :
        scribe = Scenariste()
        resultat = scribe.ecrire_scenario(
            synopsis="...",
            acts="...",
            key_scenes="..."
        )
        # resultat["character_sheet"], resultat["screenplay_excerpt"]
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.8):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("\n⚠️  OPENAI_API_KEY manquante.")
            print("   Copiez .env.example en .env et ajoutez votre clé OpenAI.")
            sys.exit(1)

        self.llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)

        base_parser = PydanticOutputParser(pydantic_object=ScreenwriterOutput)
        self.parser = OutputFixingParser.from_llm(parser=base_parser, llm=self.llm)
        self.base_parser = base_parser

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_PROMPT),
        ]).partial(format_instructions=base_parser.get_format_instructions())

    def ecrire_scenario(self, synopsis: str, acts: str, key_scenes: str) -> dict:
        """
        Génère les fiches personnages et l'extrait de scénario.

        Args:
            synopsis   : Résumé de l'histoire (sortie de l'Agent 02)
            acts       : Structure en 3 actes (sortie de l'Agent 02)
            key_scenes : Les 3 scènes clés (sortie de l'Agent 02)

        Returns:
            {"character_sheet": str, "screenplay_excerpt": str}

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        try:
            response: ScreenwriterOutput = chain.invoke({
                "synopsis":   synopsis,
                "acts":       acts,
                "key_scenes": key_scenes,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 03] Échec de l'écriture du scénario : {e}") from e

        self._last_character_sheet    = response.character_sheet
        self._last_screenplay_excerpt = response.screenplay_excerpt

        return {
            "character_sheet":    response.character_sheet,
            "screenplay_excerpt": response.screenplay_excerpt,
        }

    def afficher_scenario(self) -> str:
        """Retourne un résumé formaté du dernier appel à ecrire_scenario()."""
        return (
            f"FICHES PERSONNAGES :\n{getattr(self, '_last_character_sheet', '—')}\n\n"
            f"EXTRAIT SCÉNARIO :\n{getattr(self, '_last_screenplay_excerpt', '—')}"
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    scribe = Scenariste()
    scribe.ecrire_scenario(
        synopsis="ELARA, astronaute solitaire, plonge sous les glaces d'Europe et découvre une conscience alien collective.",
        acts="Acte 1 : Arrivée et isolement. Acte 2 : Premier contact et incompréhension. Acte 3 : Fusion ou sacrifice.",
        key_scenes="Scène 1 : La plongée initiale dans l'obscurité. Scène 2 : La première lumière alien. Scène 3 : Le choix final.",
    )
    print(scribe.afficher_scenario())
