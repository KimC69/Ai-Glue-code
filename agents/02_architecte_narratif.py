"""
02_architecte_narratif.py — Agent 02 : Architecte Narratif
Rôle : Construire la structure dramaturgique complète à partir de la vision du Directeur.
Expose la classe ArchitecteNarratif avec la méthode construire_structure().
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import NarrativeOutput


SYSTEM_PROMPT = """Tu es un Architecte Narratif expert en dramaturgie cinématographique.
Tu maîtrises le Voyage du Héros, la structure en 3 actes et Save the Cat.
Tu construis des histoires émotionnellement résonnantes et dramaturgiquement solides.

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Vision du Directeur Créatif :
{vision_globale}

Genre : {genre}
Ton : {tone}

Construis la structure narrative. Fournis exactement :
- synopsis : résumé de l'histoire en 100 à 150 mots
- acts : structure en 3 actes avec les tournants clés (setup / confrontation / résolution)
- key_scenes : 3 scènes clés détaillées (ouverture, climax, résolution)

{format_instructions}"""


class ArchitecteNarratif:
    """
    Agent 02 — Architecte Narratif.

    Lit la vision du Directeur dans WorldState, construit la structure
    dramaturgique, et renvoie les résultats pour les sauvegarder.

    Usage :
        architecte = ArchitecteNarratif()
        resultat = architecte.construire_structure(
            vision_globale="...",
            genre="Science-fiction contemplative",
            tone="Sombre, poétique"
        )
        # resultat["synopsis"], resultat["acts"], resultat["key_scenes"]
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("\n⚠️  OPENAI_API_KEY manquante.")
            print("   Copiez .env.example en .env et ajoutez votre clé OpenAI.")
            sys.exit(1)

        self.llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)

        base_parser = PydanticOutputParser(pydantic_object=NarrativeOutput)
        self.parser = OutputFixingParser.from_llm(parser=base_parser, llm=self.llm)
        self.base_parser = base_parser

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_PROMPT),
        ]).partial(format_instructions=base_parser.get_format_instructions())

    def construire_structure(self, vision_globale: str, genre: str, tone: str) -> dict:
        """
        Génère la structure narrative complète.

        Args:
            vision_globale : Texte complet de la vision du Directeur Créatif
            genre          : Genre cinématographique
            tone           : Ton du film

        Returns:
            {"synopsis": str, "acts": str, "key_scenes": str}

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        try:
            response: NarrativeOutput = chain.invoke({
                "vision_globale": vision_globale,
                "genre": genre,
                "tone": tone,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 02] Échec de la construction narrative : {e}") from e

        self._last_synopsis   = response.synopsis
        self._last_acts       = response.acts
        self._last_key_scenes = response.key_scenes

        return {
            "synopsis":   response.synopsis,
            "acts":       response.acts,
            "key_scenes": response.key_scenes,
        }

    def afficher_structure(self) -> str:
        """Retourne un résumé formaté du dernier appel à construire_structure()."""
        return (
            f"SYNOPSIS :\n{getattr(self, '_last_synopsis', '—')}\n\n"
            f"ACTES :\n{getattr(self, '_last_acts', '—')}\n\n"
            f"SCÈNES CLÉS :\n{getattr(self, '_last_key_scenes', '—')}"
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    architecte = ArchitecteNarratif()
    architecte.construire_structure(
        vision_globale="GENRE : Sci-fi contemplative\nTON : Sombre\nVISION : Film sur la solitude du contact.",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique",
    )
    print(architecte.afficher_structure())
