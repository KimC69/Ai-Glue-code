"""
Agent 02 — Architecte Narratif
Rôle : Construire la structure dramaturgique complète.
Reçoit la vision du Directeur → produit synopsis, actes et scènes clés structurés.
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import ProjectState, NarrativeOutput


SYSTEM_PROMPT = """Tu es un Architecte Narratif expert en dramaturgie cinématographique.
Tu maîtrises le Voyage du Héros, la structure en 3 actes et Save the Cat.
Tu construis des histoires émotionnellement résonnantes et dramaturgiquement solides.

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Vision du Directeur :
{director_vision}

Genre : {genre}
Ton : {tone}

Construis la structure narrative. Fournis exactement :
- synopsis : résumé de 100 à 150 mots
- acts : structure en 3 actes avec les tournants clés (setup / confrontation / résolution)
- key_scenes : 3 scènes clés détaillées (ouverture, climax, résolution)

{format_instructions}"""


def _check_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante. Copiez .env.example en .env et ajoutez votre clé.")
        sys.exit(1)
    return api_key


def invoke(state: ProjectState, llm: ChatOpenAI) -> ProjectState:
    """
    Invoque l'Agent 02 avec la sortie structurée de l'Agent 01.

    Args:
        state: L'état contenant genre, ton et vision du directeur
        llm: Le modèle LLM partagé

    Returns:
        L'état enrichi avec synopsis, actes et scènes clés
    
    Raises:
        RuntimeError: Si le parsing échoue après tentative de correction
    """
    base_parser = PydanticOutputParser(pydantic_object=NarrativeOutput)
    parser = OutputFixingParser.from_llm(parser=base_parser, llm=llm)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]).partial(format_instructions=base_parser.get_format_instructions())

    chain = prompt | llm | parser

    print("\n[Agent 02 - Architecte Narratif] Structuration de l'histoire...")
    try:
        response: NarrativeOutput = chain.invoke({
            "director_vision": state.director_vision,
            "genre": state.genre,
            "tone": state.tone,
        })
    except (OutputParserException, Exception) as e:
        raise RuntimeError(f"[Agent 02] Échec du parsing : {e}") from e

    # Propagation directe depuis le schéma structuré
    state.synopsis = response.synopsis
    state.acts = response.acts
    state.key_scenes = response.key_scenes

    print(f"[Agent 02 ✓] Structure narrative construite.")
    return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=_check_api_key(),
    )
    test_state = ProjectState(
        idea="Un astronaute découvre une civilisation sous-marine sur une lune de Jupiter",
        director_vision="Film de science-fiction contemplatif, inspiré de Premier Contact et Annihilation.",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique, métaphysique",
    )
    result = invoke(test_state, llm)
    print(f"\nSynopsis:\n{result.synopsis}")
    print(f"\nActes:\n{result.acts}")
    print(f"\nScènes clés:\n{result.key_scenes}")
