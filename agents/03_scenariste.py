"""
Agent 03 — Scénariste
Rôle : Écrire l'extrait de scénario et les fiches personnages.
Reçoit la structure narrative → produit dialogues et biographies structurés.
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import ProjectState, ScreenwriterOutput


SYSTEM_PROMPT = """Tu es un Scénariste professionnel formé au format Hollywood standard.
Tu écris des dialogues naturels et percutants, des directions de jeu précises.
Tu crées des personnages complexes avec des motivations profondes et des contradictions.

Format scénario : INT./EXT. LIEU - MOMENT pour les actions, NOM PERSONNAGE centré pour les dialogues.
Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Synopsis : {synopsis}

Structure en actes : {acts}

Scènes clés : {key_scenes}

Écris exactement :
- character_sheet : fiche de chaque personnage principal (nom, âge, background, motivation, faille)
- screenplay_excerpt : extrait de scénario de la scène d'ouverture en format Hollywood complet

{format_instructions}"""


def _check_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante. Copiez .env.example en .env et ajoutez votre clé.")
        sys.exit(1)
    return api_key


def invoke(state: ProjectState, llm: ChatOpenAI) -> ProjectState:
    """
    Invoque l'Agent 03 avec la structure narrative de l'Agent 02.

    Args:
        state: L'état contenant synopsis, actes et scènes clés
        llm: Le modèle LLM partagé

    Returns:
        L'état enrichi avec l'extrait de scénario et les fiches personnages

    Raises:
        RuntimeError: Si le parsing échoue après tentative de correction
    """
    base_parser = PydanticOutputParser(pydantic_object=ScreenwriterOutput)
    parser = OutputFixingParser.from_llm(parser=base_parser, llm=llm)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]).partial(format_instructions=base_parser.get_format_instructions())

    chain = prompt | llm | parser

    print("\n[Agent 03 - Scénariste] Écriture du scénario...")
    try:
        response: ScreenwriterOutput = chain.invoke({
            "synopsis": state.synopsis,
            "acts": state.acts,
            "key_scenes": state.key_scenes,
        })
    except (OutputParserException, Exception) as e:
        raise RuntimeError(f"[Agent 03] Échec du parsing : {e}") from e

    # Propagation directe depuis le schéma structuré
    state.character_sheet = response.character_sheet
    state.screenplay_excerpt = response.screenplay_excerpt

    print(f"[Agent 03 ✓] Scénario et personnages écrits.")
    return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.8,
        api_key=_check_api_key(),
    )
    test_state = ProjectState(
        synopsis="ELARA, astronaute solitaire, plonge dans les océans d'Europe et découvre une conscience collective alien.",
        acts="Acte 1 : Arrivée. Acte 2 : Contact et incompréhension. Acte 3 : Fusion ou destruction.",
        key_scenes="Scène 1 : Plongée initiale. Scène 2 : Premier contact. Scène 3 : Climax de fusion.",
    )
    result = invoke(test_state, llm)
    print(f"\n--- Fiche Personnages ---\n{result.character_sheet[:400]}")
    print(f"\n--- Extrait Scénario ---\n{result.screenplay_excerpt[:400]}")
