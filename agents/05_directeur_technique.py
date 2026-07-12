"""
05_directeur_technique.py — Agent 05 : Directeur Technique (Unreal Engine)
Rôle : Générer un script Shell/Python pour automatiser Unreal Engine 5.
Expose la classe DirecteurTechnique avec la méthode creer_setup_unreal().
"""

import os
import re
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import TechDirectorOutput, dossier_sortie


SYSTEM_PROMPT = """Tu es un Directeur Technique expert Unreal Engine 5 (UE5).
Tu génères des scripts Shell (.sh) et des commandes Python via l'API Unreal (unreal.py)
pour automatiser la création de scènes cinématographiques dans UE5.

Règles absolues :
- Les scripts Shell commencent par #!/bin/bash
- Les commandes Python UE5 utilisent import unreal
- Commente chaque étape en détail
- Le script doit être autonome et documenté
- Utilise des chemins relatifs pour la portabilité

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Style visuel Blender : {visual_style}

Aperçu du script Blender de référence :
{blender_script_preview}

Genre : {genre} | Ton : {tone}

Génère exactement :
- technical_notes : étapes du workflow Blender → Unreal, assets nécessaires, contraintes (3-5 lignes)
- unreal_script : script Shell complet avec les commandes UE5
  (doit inclure : import FBX, configuration Sequencer, éclairage Lumen, export final en vidéo)
- filename : nom du fichier à créer (ex: setup_scene_01.sh)

{format_instructions}"""


def _securiser_nom_fichier(filename: str) -> str:
    """
    Nettoie un nom de fichier généré par le LLM.
    Bloque les traversals de répertoire (../) et les caractères dangereux.
    Force une extension .sh ou .py.
    """
    safe = os.path.basename(filename)
    safe = re.sub(r"[^\w\-.]", "_", safe)
    name, ext = os.path.splitext(safe)
    if ext not in (".sh", ".py"):
        safe = name + ".sh"
    return safe[:80] if len(safe) > 80 else safe


class DirecteurTechnique(BaseAgent):
    """
    Agent 05 — Directeur Technique (Unreal Engine).

    Dernier maillon de la chaîne : lit le style visuel et le script Blender
    de l'Agent 04, produit un script Shell UE5 et le sauvegarde dans output/.

    Usage :
        dt = DirecteurTechnique()
        resultat = dt.creer_setup_unreal(
            visual_style="Ambiance bioluminescente...",
            blender_script="import bpy\\n...",
            genre="Science-fiction contemplative",
            tone="Sombre, poétique"
        )
        # resultat["technical_notes"], resultat["unreal_script"], resultat["saved_path"]
    """

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.3):
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=TechDirectorOutput,
            agent_id="Agent 05",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def creer_setup_unreal(
        self,
        visual_style: str,
        blender_script: str,
        genre: str,
        tone: str,
    ) -> dict:
        """
        Génère et sauvegarde le script Shell Unreal Engine.

        Args:
            visual_style   : Style visuel décrit par l'Agent 04
            blender_script : Script Blender complet de l'Agent 04 (référence de cohérence)
            genre          : Genre du film (sortie Agent 01)
            tone           : Ton du film (sortie Agent 01)

        Returns:
            {
              "technical_notes": str,  # notes de production
              "unreal_script"  : str,  # script Shell complet
              "saved_path"     : str,  # chemin du fichier .sh sauvegardé
            }

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        # On tronque le script Blender pour ne pas saturer le contexte du prompt
        preview = blender_script[:800] + "..." if len(blender_script) > 800 else blender_script

        try:
            response: TechDirectorOutput = chain.invoke({
                "visual_style":           visual_style,
                "blender_script_preview": preview,
                "genre":                  genre,
                "tone":                   tone,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 05] Échec de la génération Unreal : {e}") from e

        saved_path = self._sauvegarder(response.filename, response.unreal_script)

        self._last_technical_notes = response.technical_notes
        self._last_unreal_script   = response.unreal_script
        self._last_saved_path      = saved_path

        return {
            "technical_notes": response.technical_notes,
            "unreal_script":   response.unreal_script,
            "saved_path":      saved_path,
        }

    def _sauvegarder(self, filename: str, code: str) -> str:
        """Sauvegarde le script Unreal dans agents/output/ de façon sécurisée."""
        output_dir = dossier_sortie()
        os.makedirs(output_dir, exist_ok=True)

        safe_filename = _securiser_nom_fichier(filename)
        filepath = os.path.join(output_dir, safe_filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        # Rend le script exécutable sur Linux/Mac
        try:
            os.chmod(filepath, 0o755)
        except Exception:
            pass

        return filepath

    def afficher_resultat(self) -> str:
        """Retourne un résumé formaté du dernier appel à creer_setup_unreal()."""
        return (
            f"NOTES TECHNIQUES :\n{getattr(self, '_last_technical_notes', '—')}\n\n"
            f"SCRIPT UNREAL sauvegardé → {getattr(self, '_last_saved_path', '—')}\n"
            f"(Aperçu — 10 premières lignes) :\n"
            + "\n".join(getattr(self, "_last_unreal_script", "").splitlines()[:10])
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    dt = DirecteurTechnique()
    dt.creer_setup_unreal(
        visual_style="Ambiance bioluminescente sous-marine, éclairage bleu profond, particules lumineuses.",
        blender_script="import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique",
    )
    print(dt.afficher_resultat())
