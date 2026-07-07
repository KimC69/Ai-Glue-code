"""
Agent 01 — Directeur de Création
Rôle : Définir la vision artistique globale du projet cinématographique.
Reçoit une idée brute → produit genre, ton et vision structurés.
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import ProjectState, DirectorOutput


SYSTEM_PROMPT = """Tu es un Directeur de Création cinématographique visionnaire, 
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


def _check_api_key() -> str:
    """Vérifie la présence de la clé API et l'enregistre."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante. Copiez .env.example en .env et ajoutez votre clé.")
        sys.exit(1)
    return api_key


def invoke(state: ProjectState, llm: ChatOpenAI) -> ProjectState:
    """
    Invoque l'Agent 01 et met à jour l'état partagé.

    Args:
        state: L'état courant du projet
        llm: Le modèle LLM partagé

    Returns:
        L'état mis à jour avec la vision du directeur
    
    Raises:
        RuntimeError: Si le parseur échoue même après correction automatique
    """
    base_parser = PydanticOutputParser(pydantic_object=DirectorOutput)
    # OutputFixingParser demande au LLM de se corriger si le JSON est malformé
    parser = OutputFixingParser.from_llm(parser=base_parser, llm=llm)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]).partial(format_instructions=base_parser.get_format_instructions())

    chain = prompt | llm | parser

    print("\n[Agent 01 - Directeur] Analyse de l'idée...")
    try:
        response: DirectorOutput = chain.invoke({"idea": state.idea})
    except (OutputParserException, Exception) as e:
        raise RuntimeError(f"[Agent 01] Échec du parsing : {e}") from e

    # Propagation directe depuis le schéma structuré (pas de heuristique)
    state.genre = response.genre
    state.tone = response.tone
    state.director_vision = response.director_vision

    print(f"[Agent 01 ✓] Genre : {state.genre} | Ton : {state.tone}")
    return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=_check_api_key(),
    )
    test_state = ProjectState(idea="Un astronaute découvre une civilisation sous-marine sur une lune de Jupiter")
    result = invoke(test_state, llm)
    print("\n--- Vision du Directeur ---")
    print(f"Genre : {result.genre}")
    print(f"Ton   : {result.tone}")
    print(f"Vision:\n{result.director_vision}")
