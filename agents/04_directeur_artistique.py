"""
Agent 04 — Directeur Artistique (Blender)
Rôle : Générer un script Python prêt à exécuter dans Blender.
Reçoit le scénario → produit du code Blender 100% fonctionnel.
"""

import os
import re
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from langchain_core.tools import tool
from shared_state import ProjectState, ArtDirectorOutput


SYSTEM_PROMPT = """Tu es un Directeur Artistique et expert Blender Python (bpy).
Tu génères UNIQUEMENT du code Python valide pour Blender 3.x/4.x via l'API bpy.
Ton code est commenté, modulaire et directement exécutable dans le Script Editor de Blender.

Règles absolues :
- Tout code commence par : import bpy
- Nettoie la scène en début de script : bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
- Utilise des noms de variables explicites en anglais
- Ajoute des commentaires pour chaque section importante
- Le code doit être autonome (pas d'imports externes hors bpy)

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Extrait de scénario : {screenplay_excerpt}

Style visuel (genre : {genre}, ton : {tone}) :
- Éclairage dramatique adapté au genre
- Géométries et décors représentatifs de l'univers
- Matériaux et shaders appropriés

Fournis exactement :
- visual_style : description du style visuel, palette, ambiance lumineuse (2-3 phrases)
- blender_script : script Python Blender complet (commence obligatoirement par "import bpy")
- filename : nom du fichier Python à créer (ex: scene_01_opening.py)

{format_instructions}"""


def _sanitize_filename(filename: str, allowed_ext: tuple = (".py",)) -> str:
    """
    Nettoie un nom de fichier généré par le LLM pour éviter les traversals de répertoire.
    
    - Prend uniquement le basename (supprime les chemins relatifs ../../../)
    - Supprime les caractères dangereux
    - Garantit l'extension autorisée
    
    Args:
        filename: Nom de fichier brut venant du LLM
        allowed_ext: Extensions autorisées

    Returns:
        Nom de fichier sûr et valide
    """
    # Prendre uniquement le basename pour bloquer ../../../etc
    safe = os.path.basename(filename)
    # Supprimer tout caractère non alphanumérique, tiret ou underscore (hors extension)
    safe = re.sub(r"[^\w\-.]", "_", safe)
    # Vérifier et forcer l'extension
    _, ext = os.path.splitext(safe)
    if ext not in allowed_ext:
        safe = safe + allowed_ext[0]
    # Limiter la longueur
    if len(safe) > 80:
        safe = safe[:76] + allowed_ext[0]
    return safe


@tool
def save_blender_script(filename: str, code: str) -> str:
    """
    Outil LangChain : Sauvegarde un script Blender dans le dossier output/.

    Args:
        filename: Nom du fichier .py à créer
        code: Contenu du script Python Blender

    Returns:
        Chemin complet du fichier créé
    """
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    safe_filename = _sanitize_filename(filename, allowed_ext=(".py",))
    filepath = os.path.join(output_dir, safe_filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)

    return f"Script Blender sauvegardé : {filepath}"


def _check_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante. Copiez .env.example en .env et ajoutez votre clé.")
        sys.exit(1)
    return api_key


def invoke(state: ProjectState, llm: ChatOpenAI) -> ProjectState:
    """
    Invoque l'Agent 04 et sauvegarde le script Blender généré.

    Args:
        state: L'état contenant le scénario et le style
        llm: Le modèle LLM partagé

    Returns:
        L'état enrichi avec le script Blender et le style visuel

    Raises:
        RuntimeError: Si le parsing échoue après tentative de correction
    """
    base_parser = PydanticOutputParser(pydantic_object=ArtDirectorOutput)
    parser = OutputFixingParser.from_llm(parser=base_parser, llm=llm)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]).partial(format_instructions=base_parser.get_format_instructions())

    chain = prompt | llm | parser

    print("\n[Agent 04 - Directeur Artistique] Génération du script Blender...")
    try:
        response: ArtDirectorOutput = chain.invoke({
            "screenplay_excerpt": state.screenplay_excerpt,
            "genre": state.genre,
            "tone": state.tone,
        })
    except (OutputParserException, Exception) as e:
        raise RuntimeError(f"[Agent 04] Échec du parsing : {e}") from e

    # Propagation directe depuis le schéma structuré
    state.visual_style = response.visual_style
    state.blender_script = response.blender_script

    # Sauvegarde sécurisée du script via l'outil LangChain
    result = save_blender_script.invoke({
        "filename": response.filename,
        "code": response.blender_script,
    })
    print(f"[Agent 04 ✓] {result}")

    return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.4,
        api_key=_check_api_key(),
    )
    test_state = ProjectState(
        screenplay_excerpt="INT. CAPSULE SUBMERSIBLE - NUIT\nELARA regarde par le hublot. Des lumières bioluminescentes tourbillonnent dans les profondeurs.",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique, métaphysique",
    )
    result = invoke(test_state, llm)
    print(f"\nStyle Visuel:\n{result.visual_style}")
    print(f"\nScript Blender (200 premiers caractères):\n{result.blender_script[:200]}")
