"""
06_superviseur_post_production.py — Agent 06 : Superviseur Post-Production
Rôle : Évaluer la cohérence du résultat (Agents 04/05) et déclencher, au cas
par cas UNIQUEMENT si nécessaire, des outils correctifs open source
(GIMP pour la retouche, Kdenlive/Shotcut pour le montage).

Aucun outil n'est lancé si le résultat est déjà conforme — c'est le rôle de
cet agent de trancher, pas une étape systématique du pipeline.
"""

import os
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import PostProductionOutput


SYSTEM_PROMPT = """Tu es le Superviseur Post-Production d'un studio de cinéma virtuel.
Ton rôle est d'auditer la cohérence entre la vision artistique, le script Blender
et le setup Unreal Engine produits par les agents précédents, et de décider,
outil par outil, si l'un des logiciels open source suivants doit intervenir :

- GIMP        : retouche photo/image
- Kdenlive / Shotcut : montage vidéo
- Inkscape    : illustration vectorielle (logo, affiche, titre stylisé)
- Darktable   : développement de photos RAW (textures/références haute qualité)
- Krita       : dessin et peinture numérique (concept art, matte painting)
- OBS Studio  : capture vidéo / streaming (ex: capture du rendu Unreal)

Tu ne dois recommander un outil QUE s'il y a un vrai besoin justifié par le
projet (ex : palette de couleurs incohérente avec le ton → GIMP ; le film a
besoin d'une affiche → Inkscape ; une texture manque de réalisme → Darktable ;
un plan nécessite un concept art peint → Krita ; le rendu final doit être
capturé en direct → OBS ; assemblage de plusieurs scènes → Kdenlive/Shotcut).

Règles absolues :
- Par défaut, TOUS les needs_* sont false et les champs texte associés vides.
- N'active un outil que s'il répond à un besoin réel et concret du projet
  (genre, ton, scènes clés). N'invente jamais un problème pour justifier un
  outil inutile — la majorité des projets n'auront besoin que d'un sous-ensemble
  de ces outils, voire d'aucun.
- Le script GIMP (si nécessaire) est en Python-Fu, commenté et autonome.
- Les notes de montage (si nécessaires) sont des instructions concrètes pour
  Kdenlive ou Shotcut (coupes, transitions, calage audio).
- Le script Krita (si nécessaire) utilise l'API Python Krita (module krita),
  commenté et autonome.
- Les notes Inkscape/Darktable/OBS (si nécessaires) sont des instructions
  concrètes et actionnables, pas des généralités.

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Style visuel (Agent 04) : {visual_style}

Notes techniques Unreal (Agent 05) : {technical_notes}

Genre : {genre} | Ton : {tone}

Aperçu script Blender :
{blender_script_preview}

Aperçu script Unreal :
{unreal_script_preview}

Analyse la cohérence globale entre ces éléments et détermine, outil par outil,
si une intervention est réellement nécessaire :
- coherence_score : score de 0 à 100
- issues : problèmes identifiés (ou "Aucun")
- needs_gimp_retouching + gimp_script
- needs_video_editing + video_editing_notes
- needs_inkscape + inkscape_notes (affiche, logo, titre stylisé)
- needs_darktable + darktable_notes (développement RAW de textures/références)
- needs_krita + krita_script (concept art, matte painting)
- needs_obs + obs_notes (capture/streaming du rendu)

{format_instructions}"""


class SuperviseurPostProduction(BaseAgent):
    """
    Agent 06 — Superviseur Post-Production.

    Audite la cohérence du travail des Agents 04/05 et décide, au cas par
    cas, si des outils open source (GIMP, Kdenlive/Shotcut) doivent
    intervenir pour rendre le résultat conforme à la vision d'origine.

    Usage :
        superviseur = SuperviseurPostProduction()
        rapport = superviseur.analyser_conformite(
            visual_style="...", technical_notes="...",
            blender_script="...", unreal_script="...",
            genre="...", tone="..."
        )
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.2):
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=PostProductionOutput,
            agent_id="Agent 06",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def analyser_conformite(
        self,
        visual_style: str,
        technical_notes: str,
        blender_script: str,
        unreal_script: str,
        genre: str,
        tone: str,
    ) -> dict:
        """
        Audite la cohérence du résultat produit par les Agents 04/05.

        Returns:
            {
              "coherence_score": int,
              "issues": str,
              "needs_gimp_retouching": bool, "gimp_script": str, "gimp_saved_path": str,
              "needs_video_editing": bool,   "video_editing_notes": str,
              "needs_inkscape": bool,        "inkscape_notes": str,
              "needs_darktable": bool,       "darktable_notes": str,
              "needs_krita": bool,           "krita_script": str, "krita_saved_path": str,
              "needs_obs": bool,             "obs_notes": str,
            }
            Seuls les outils réellement jugés nécessaires ont un contenu non vide.

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        blender_preview = blender_script[:600] + "..." if len(blender_script) > 600 else blender_script
        unreal_preview = unreal_script[:600] + "..." if len(unreal_script) > 600 else unreal_script

        try:
            response: PostProductionOutput = chain.invoke({
                "visual_style":            visual_style,
                "technical_notes":         technical_notes,
                "genre":                   genre,
                "tone":                    tone,
                "blender_script_preview":  blender_preview,
                "unreal_script_preview":   unreal_preview,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 06] Échec de l'analyse de conformité : {e}") from e

        # Table de correspondance outil → (drapeau, champ contenu, fichier de sortie).
        # Centralise la validation croisée : si un outil est signalé nécessaire
        # mais que son contenu est vide, on désactive le déclenchement plutôt
        # que de proposer une commande qui n'exécuterait rien d'utile.
        outils = {
            "gimp":      ("needs_gimp_retouching", "gimp_script",       "retouche_gimp.py"),
            "video":     ("needs_video_editing",    "video_editing_notes", None),
            "inkscape":  ("needs_inkscape",         "inkscape_notes",    None),
            "darktable": ("needs_darktable",        "darktable_notes",   None),
            "krita":     ("needs_krita",            "krita_script",      "concept_krita.py"),
            "obs":       ("needs_obs",              "obs_notes",         None),
        }

        resultat: dict = {
            "coherence_score": response.coherence_score,
            "issues": response.issues,
        }
        etat_final: dict = {}

        for _cle, (flag_field, content_field, output_filename) in outils.items():
            contenu = getattr(response, content_field)
            actif = getattr(response, flag_field) and bool(contenu.strip())

            saved_path = ""
            if actif and output_filename:
                saved_path = self._sauvegarder_script(output_filename, contenu)

            resultat[flag_field] = actif
            resultat[content_field] = contenu if actif else ""
            if output_filename:
                resultat[f"{_cle}_saved_path"] = saved_path

            etat_final[_cle] = actif

        self._last_result = response
        self._last_etat_outils = etat_final
        self._last_saved_paths = {
            k: resultat.get(f"{k}_saved_path", "") for k in outils if outils[k][2]
        }

        return resultat

    def _sauvegarder_script(self, filename: str, code: str) -> str:
        """Sauvegarde un script généré (GIMP, Krita, ...) dans agents/output/.
        Le nom de fichier est fixe (défini en interne, jamais fourni par le LLM),
        donc aucun risque de traversal de répertoire."""
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return filepath

    def afficher_rapport(self) -> str:
        """Retourne un résumé formaté de la dernière analyse de conformité."""
        r = getattr(self, "_last_result", None)
        if r is None:
            return "Aucune analyse effectuée."

        etat = getattr(self, "_last_etat_outils", {})
        paths = getattr(self, "_last_saved_paths", {})

        lignes = [
            f"SCORE DE COHÉRENCE : {r.coherence_score}/100",
            f"PROBLÈMES IDENTIFIÉS : {r.issues}",
            "",
        ]

        libelles = {
            "gimp":      ("🎨 Retouche GIMP", r.gimp_script and paths.get("gimp", "")),
            "video":     ("🎬 Montage vidéo (Kdenlive/Shotcut)", r.video_editing_notes),
            "inkscape":  ("✏️  Illustration Inkscape", r.inkscape_notes),
            "darktable": ("📷 Développement RAW Darktable", r.darktable_notes),
            "krita":     ("🖌️  Dessin numérique Krita", paths.get("krita", "")),
            "obs":       ("🎥 Capture/streaming OBS", r.obs_notes),
        }

        for cle, (label, detail) in libelles.items():
            if etat.get(cle):
                lignes.append(f"{label} nécessaire → {detail}" if detail else f"{label} nécessaire")
            else:
                lignes.append(f"{label} : non nécessaire")

        return "\n".join(lignes)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    superviseur = SuperviseurPostProduction()
    superviseur.analyser_conformite(
        visual_style="Ambiance bioluminescente sous-marine, éclairage bleu profond.",
        technical_notes="Import FBX depuis Blender, Sequencer configuré, Lumen activé.",
        blender_script="import bpy\nbpy.ops.object.select_all(action='SELECT')",
        unreal_script="#!/bin/bash\necho 'setup UE5'",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique",
    )
    print(superviseur.afficher_rapport())
