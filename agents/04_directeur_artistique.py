"""
04_directeur_artistique.py — Agent 04 : Directeur Artistique (Blender)
Rôle : Générer un script Python prêt à exécuter dans Blender 3.x/4.x.
Expose la classe DirecteurArtistique avec la méthode creer_scene_blender().
"""

import os
import re
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import ArtDirectorOutput, dossier_sortie


SYSTEM_PROMPT = """Tu es un Directeur Artistique et expert Blender Python (bpy).
Tu génères UNIQUEMENT du code Python valide pour Blender 3.x/4.x via l'API bpy.
Ton code est commenté, modulaire et directement exécutable dans le Script Editor de Blender.

Règles absolues :
- Le script commence toujours par : import bpy
- Nettoie la scène en début de script :
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
- Utilise des noms de variables explicites en anglais
- Commente chaque section importante du code
- Aucun import externe hormis bpy

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Extrait de scénario :
{screenplay_excerpt}

Fiches personnages :
{character_sheet}

Genre : {genre} | Ton : {tone}

Génère exactement :
- visual_style : description du style visuel, palette de couleurs et ambiance lumineuse (3-4 phrases)
- blender_script : script Python Blender complet pour recréer la scène d'ouverture
  (décors, lumières, caméra, matériaux — au moins 60 lignes de code)
- filename : nom du fichier à créer (ex: scene_01_opening.py)

{format_instructions}"""


def _securiser_nom_fichier(filename: str) -> str:
    """
    Nettoie un nom de fichier généré par le LLM.
    Bloque les traversals de répertoire (../) et les caractères dangereux.
    Force l'extension .py
    """
    # Prend uniquement le basename pour bloquer ../../../etc
    safe = os.path.basename(filename)
    # Supprime tout caractère non alphanumérique, tiret ou underscore
    safe = re.sub(r"[^\w\-.]", "_", safe)
    # Force l'extension .py
    name, ext = os.path.splitext(safe)
    if ext != ".py":
        safe = name + ".py"
    # Limite la longueur
    return safe[:80] if len(safe) > 80 else safe


class DirecteurArtistique(BaseAgent):
    """
    Agent 04 — Directeur Artistique (Blender).

    Lit le scénario dans WorldState, produit un script Python Blender
    complet et le sauvegarde dans output/.

    Usage :
        da = DirecteurArtistique()
        resultat = da.creer_scene_blender(
            screenplay_excerpt="INT. CAPSULE - NUIT\\nElara regarde par le hublot...",
            character_sheet="ELARA, 34 ans, astronaute...",
            genre="Science-fiction contemplative",
            tone="Sombre, poétique"
        )
        # resultat["visual_style"], resultat["blender_script"], resultat["saved_path"]
    """

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.4):
        # gpt-4o par défaut ici : la génération de code bénéficie d'un modèle plus puissant
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=ArtDirectorOutput,
            agent_id="Agent 04",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def creer_scene_blender(
        self,
        screenplay_excerpt: str,
        character_sheet: str,
        genre: str,
        tone: str,
    ) -> dict:
        """
        Génère et sauvegarde le script Python Blender de la scène d'ouverture.

        Args:
            screenplay_excerpt : Extrait de scénario (sortie Agent 03)
            character_sheet    : Fiches personnages (sortie Agent 03)
            genre              : Genre du film (sortie Agent 01)
            tone               : Ton du film (sortie Agent 01)

        Returns:
            {
              "visual_style"  : str,   # description du style visuel
              "blender_script": str,   # code Python Blender complet
              "saved_path"    : str,   # chemin du fichier .py sauvegardé
            }

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        try:
            response: ArtDirectorOutput = chain.invoke({
                "screenplay_excerpt": screenplay_excerpt,
                "character_sheet":   character_sheet,
                "genre":             genre,
                "tone":              tone,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 04] Échec de la génération Blender : {e}") from e

        # Sauvegarde sécurisée du script
        saved_path = self._sauvegarder(response.filename, response.blender_script)

        self._last_visual_style   = response.visual_style
        self._last_blender_script = response.blender_script
        self._last_saved_path     = saved_path

        return {
            "visual_style":   response.visual_style,
            "blender_script": response.blender_script,
            "saved_path":     saved_path,
        }

    def _sauvegarder(self, filename: str, code: str) -> str:
        """Sauvegarde le script Blender dans agents/output/ de façon sécurisée."""
        output_dir = dossier_sortie()
        os.makedirs(output_dir, exist_ok=True)

        safe_filename = _securiser_nom_fichier(filename)
        filepath = os.path.join(output_dir, safe_filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        return filepath

    def afficher_resultat(self) -> str:
        """Retourne un résumé formaté du dernier appel à creer_scene_blender()."""
        return (
            f"STYLE VISUEL :\n{getattr(self, '_last_visual_style', '—')}\n\n"
            f"SCRIPT BLENDER sauvegardé → {getattr(self, '_last_saved_path', '—')}\n"
            f"(Aperçu — 10 premières lignes) :\n"
            + "\n".join(getattr(self, "_last_blender_script", "").splitlines()[:10])
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    da = DirecteurArtistique()
    da.creer_scene_blender(
        screenplay_excerpt=(
            "INT. CAPSULE SUBMERSIBLE - NUIT\n"
            "ELARA (34 ans) regarde par le hublot. Des lumières bioluminescentes tourbillonnent."
        ),
        character_sheet="ELARA, 34 ans, astronaute solitaire. Motivation : comprendre. Faille : incapacité à lâcher prise.",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique, métaphysique",
    )
    print(da.afficher_resultat())
