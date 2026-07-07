"""
Agent 05 — Directeur Technique (Unreal Engine)
Rôle : Générer un script Shell/Python pour automatiser Unreal Engine.
Reçoit le style visuel Blender → produit les commandes Unreal Engine prêtes à l'emploi.
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
from shared_state import ProjectState, TechDirectorOutput


SYSTEM_PROMPT = """Tu es un Directeur Technique expert Unreal Engine 5 (UE5).
Tu génères des scripts Shell (.sh) et des commandes Python via l'API Unreal (unreal.py)
pour automatiser la création de scènes cinématographiques dans UE5.

Règles absolues :
- Les scripts Shell commencent par #!/bin/bash
- Les commandes Python UE5 utilisent import unreal
- Inclure des commentaires détaillés à chaque étape
- Les scripts doivent être autonomes et documentés
- Prévoir des chemins relatifs pour la portabilité

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Style visuel Blender : {visual_style}

Aperçu du script Blender de référence :
{blender_script_preview}

Genre : {genre} | Ton : {tone}

Génère exactement :
- technical_notes : étapes techniques du workflow Blender→Unreal, assets, contraintes (3-5 lignes)
- unreal_script : script Shell (.sh) complet avec les commandes UE5 pour importer et configurer la scène
  (doit inclure : import FBX, Sequencer, éclairage Lumen, export final)
- filename : nom du fichier à créer (ex: setup_scene_01.sh)

{format_instructions}"""


def _sanitize_filename(filename: str, allowed_ext: tuple = (".sh", ".py")) -> str:
    """
    Nettoie un nom de fichier généré par le LLM pour éviter les traversals de répertoire.

    - Prend uniquement le basename (supprime les chemins relatifs ../../../)
    - Supprime les caractères dangereux
    - Garantit une extension autorisée

    Args:
        filename: Nom de fichier brut venant du LLM
        allowed_ext: Extensions autorisées

    Returns:
        Nom de fichier sûr et valide
    """
    safe = os.path.basename(filename)
    safe = re.sub(r"[^\w\-.]", "_", safe)
    _, ext = os.path.splitext(safe)
    if ext not in allowed_ext:
        safe = safe + allowed_ext[0]
    if len(safe) > 80:
        safe = safe[:76] + allowed_ext[0]
    return safe


@tool
def save_unreal_script(filename: str, code: str) -> str:
    """
    Outil LangChain : Sauvegarde un script Unreal dans le dossier output/.

    Args:
        filename: Nom du fichier .sh ou .py à créer
        code: Contenu du script Shell/Python Unreal

    Returns:
        Chemin complet du fichier créé
    """
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    safe_filename = _sanitize_filename(filename, allowed_ext=(".sh", ".py"))
    filepath = os.path.join(output_dir, safe_filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)

    # Rendre exécutable sur Linux/Mac
    try:
        os.chmod(filepath, 0o755)
    except Exception:
        pass

    return f"Script Unreal sauvegardé : {filepath}"


def _check_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante. Copiez .env.example en .env et ajoutez votre clé.")
        sys.exit(1)
    return api_key


def invoke(state: ProjectState, llm: ChatOpenAI) -> ProjectState:
    """
    Invoque l'Agent 05 et sauvegarde le script Unreal généré.

    Args:
        state: L'état contenant le style visuel et le script Blender
        llm: Le modèle LLM partagé

    Returns:
        L'état final enrichi avec le script Unreal et les notes techniques

    Raises:
        RuntimeError: Si le parsing échoue après tentative de correction
    """
    base_parser = PydanticOutputParser(pydantic_object=TechDirectorOutput)
    parser = OutputFixingParser.from_llm(parser=base_parser, llm=llm)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]).partial(format_instructions=base_parser.get_format_instructions())

    chain = prompt | llm | parser

    print("\n[Agent 05 - Directeur Technique] Génération du script Unreal Engine...")
    try:
        response: TechDirectorOutput = chain.invoke({
            "visual_style": state.visual_style,
            "blender_script_preview": (
                state.blender_script[:800] + "..."
                if len(state.blender_script) > 800
                else state.blender_script
            ),
            "genre": state.genre,
            "tone": state.tone,
        })
    except (OutputParserException, Exception) as e:
        raise RuntimeError(f"[Agent 05] Échec du parsing : {e}") from e

    # Propagation directe depuis le schéma structuré
    state.technical_notes = response.technical_notes
    state.unreal_script = response.unreal_script

    # Sauvegarde sécurisée via l'outil LangChain
    result = save_unreal_script.invoke({
        "filename": response.filename,
        "code": response.unreal_script,
    })
    print(f"[Agent 05 ✓] {result}")

    return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        api_key=_check_api_key(),
    )
    test_state = ProjectState(
        visual_style="Ambiance bioluminescente sous-marine, éclairage bleu profond avec particules lumineuses.",
        blender_script="import bpy\n# Script de test\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique",
    )
    result = invoke(test_state, llm)
    print(f"\nNotes Techniques:\n{result.technical_notes}")
    print(f"\nScript Unreal (début):\n{result.unreal_script[:200]}")
