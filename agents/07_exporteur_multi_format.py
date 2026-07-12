"""
07_exporteur_multi_format.py — Agent 07 : Exporteur Multi-Format
Rôle : À partir de la vidéo/réseau master produit par les agents précédents,
générer les exports déclinés pour chaque plateforme (téléphone, TV, projecteur,
réseaux sociaux) sous forme d'un script FFmpeg exécutable.

L'Agent 07 ne suppose jamais qu'il faut un format unique : il détermine
explicitement lesquels sont pertinents en fonction du projet (genre, ton,
scènes clés, destination prévisible) et produit un script de conversion
prêt à l'emploi.
"""

import os
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import ExportMultiFormatOutput, dossier_sortie


SYSTEM_PROMPT = """Tu es l'Exporteur Multi-Format d'un studio de cinéma virtuel.
Ton rôle est de produire un script FFmpeg qui convertit la vidéo/réseau master
du film en plusieurs formats adaptés aux plateformes de diffusion.

Formats possibles (tu choisis ceux qui ont du sens pour le projet) :
- 16:9 paysage — TV, YouTube, projecteur, ordinateur (1920x1080 ou 3840x2160)
- 9:16 vertical — TikTok, Instagram Reels, YouTube Shorts (1080x1920)
- 1:1 carré — Instagram feed, Twitter/X (1080x1080)
- 4:5 portrait — Instagram feed vertical (1080x1350)
- 21:9 cinémascope — TV ultra-wide, projecteur cinéma (2560x1080)

Règles absolues :
- Choisis UNIQUEMENT les formats pertinents pour le projet (ex : un film
  contemplatif → 16:9 + 21:9 ; un clip réseaux sociaux → 9:16 + 1:1).
- Ne génère pas de format "juste au cas où" : chaque déclinaison doit être
  justifiée par le genre, le ton ou la destination attendue.
- Le script FFmpeg doit être un shell (.sh) autonome, commenté, avec une
  entrée `MASTER_VIDEO` paramétrable en haut du fichier.
- Utilise `ffmpeg` avec des filtres de recadrage (`crop`, `scale`, `pad`) et
  des paramètres d'encodage cohérents (H.264, CRF 18-23, audio copy).
- Si le format d'origine n'est pas précis, suppose un master 16:9 1920x1080.
- Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Vision artistique : {vision_globale}

Style visuel (Agent 04) : {visual_style}

Notes techniques (Agent 05) : {technical_notes}

Genre : {genre} | Ton : {tone}

Aperçu du script Blender :
{blender_script_preview}

Aperçu du script Unreal :
{unreal_script_preview}

Détermine les formats d'export pertinents et génère un script FFmpeg unique
qui déclinera le master dans chaque format choisi.

{format_instructions}"""


class ExporteurMultiFormat(BaseAgent):
    """
    Agent 07 — Exporteur Multi-Format.

    Lit les livrables des agents précédents et produit un script FFmpeg qui
    génère les exports déclinés (TV, téléphone, réseaux sociaux, etc.).

    Usage :
        exporteur = ExporteurMultiFormat()
        resultat = exporteur.generer_exports(
            vision_globale="...",
            visual_style="...",
            technical_notes="...",
            blender_script="...",
            unreal_script="...",
            genre="...",
            tone="...",
        )
        # resultat["formats"], resultat["ffmpeg_script"], resultat["saved_path"]
    """

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.2):
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=ExportMultiFormatOutput,
            agent_id="Agent 07",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def generer_exports(
        self,
        vision_globale: str,
        visual_style: str,
        technical_notes: str,
        blender_script: str,
        unreal_script: str,
        genre: str,
        tone: str,
    ) -> dict:
        """
        Génère le script FFmpeg multi-format et le sauvegarde.

        Returns:
            {
              "formats": list[str],       # formats choisis (ex: ["16:9", "9:16"])
              "ffmpeg_script": str,       # script shell complet
              "saved_path": str,          # chemin du fichier sauvegardé
            }

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        blender_preview = blender_script[:600] + "..." if len(blender_script) > 600 else blender_script
        unreal_preview = unreal_script[:600] + "..." if len(unreal_script) > 600 else unreal_script

        try:
            response: ExportMultiFormatOutput = chain.invoke({
                "vision_globale":         vision_globale,
                "visual_style":           visual_style,
                "technical_notes":        technical_notes,
                "genre":                  genre,
                "tone":                   tone,
                "blender_script_preview": blender_preview,
                "unreal_script_preview":  unreal_preview,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 07] Échec de la génération des exports : {e}") from e

        saved_path = self._sauvegarder("export_multi_format.sh", response.ffmpeg_script)

        self._last_formats = response.formats
        self._last_ffmpeg_script = response.ffmpeg_script
        self._last_saved_path = saved_path

        return {
            "formats":       response.formats,
            "ffmpeg_script": response.ffmpeg_script,
            "saved_path":    saved_path,
        }

    def _sauvegarder(self, filename: str, code: str) -> str:
        """Sauvegarde le script FFmpeg dans agents/output/.
        Le nom de fichier est fixe (défini en interne, jamais fourni par le LLM)."""
        output_dir = dossier_sortie()
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        # Rend le script exécutable sur Linux/Mac
        try:
            os.chmod(filepath, 0o755)
        except Exception:
            pass

        return filepath

    def afficher_rapport(self) -> str:
        """Retourne un résumé formaté du dernier export généré."""
        formats = getattr(self, "_last_formats", [])
        saved_path = getattr(self, "_last_saved_path", "—")
        script = getattr(self, "_last_ffmpeg_script", "")

        lignes = [
            f"FORMATS D'EXPORT CHOISIS : {', '.join(formats) if formats else 'Aucun'}",
            f"SCRIPT FFMPEG sauvegardé → {saved_path}",
            "(Aperçu — 10 premières lignes) :",
        ]
        lignes.extend(script.splitlines()[:10])
        return "\n".join(lignes)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    exporteur = ExporteurMultiFormat()
    exporteur.generer_exports(
        vision_globale="Un film sous-marin bioluminescent, poétique et contemplatif.",
        visual_style="Ambiance bleu profond, particules lumineuses, éclairage doux.",
        technical_notes="Render 4K depuis Blender, import Unreal, Lumen activé.",
        blender_script="import bpy\nbpy.ops.object.select_all(action='SELECT')",
        unreal_script="#!/bin/bash\necho 'setup UE5'",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique",
    )
    print(exporteur.afficher_rapport())
