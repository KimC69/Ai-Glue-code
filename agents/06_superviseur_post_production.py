"""
06_superviseur_post_production.py — Agent 06 : Superviseur Post-Production
Rôle : Évaluer la cohérence du résultat (Agents 04/05) et déclencher, au cas
par cas UNIQUEMENT si nécessaire, des outils correctifs open source
(GIMP pour la retouche, Kdenlive/Shotcut pour le montage).

Aucun outil n'est lancé si le résultat est déjà conforme — c'est le rôle de
cet agent de trancher, pas une étape systématique du pipeline.
"""

import os
import sys
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from shared_state import PostProductionOutput


SYSTEM_PROMPT = """Tu es le Superviseur Post-Production d'un studio de cinéma virtuel.
Ton rôle est d'auditer la cohérence entre la vision artistique, le script Blender
et le setup Unreal Engine produits par les agents précédents.

Tu ne dois recommander un outil correctif QUE s'il y a un vrai problème de
cohérence (ex : palette de couleurs incohérente avec le ton du film, script
technique qui ne respecte pas le style visuel décrit, assemblage manquant).

Règles absolues :
- Si tout est cohérent : needs_gimp_retouching = false, needs_video_editing = false,
  gimp_script et video_editing_notes restent vides, issues = "Aucun".
- N'invente jamais un problème pour justifier un outil inutile.
- Le script GIMP (si nécessaire) est en Python-Fu (utilise le module gimpfu ou
  l'API GIMP 3 en Python), commenté et autonome.
- Les notes de montage (si nécessaires) sont des instructions concrètes et
  actionnables pour Kdenlive ou Shotcut (coupes, transitions, calage audio).

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Style visuel (Agent 04) : {visual_style}

Notes techniques Unreal (Agent 05) : {technical_notes}

Genre : {genre} | Ton : {tone}

Aperçu script Blender :
{blender_script_preview}

Aperçu script Unreal :
{unreal_script_preview}

Analyse la cohérence globale entre ces éléments et détermine :
- coherence_score : score de 0 à 100
- issues : problèmes identifiés (ou "Aucun")
- needs_gimp_retouching + gimp_script : uniquement si une retouche visuelle corrige un vrai écart
- needs_video_editing + video_editing_notes : uniquement si un montage est nécessaire pour rendre le résultat conforme

{format_instructions}"""


class SuperviseurPostProduction:
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

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.2):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Agent 06 est optionnel dans le pipeline (audit de conformité) :
            # on lève une exception récupérable plutôt que de tuer tout le
            # processus avec sys.exit(), pour que main.py puisse continuer
            # sans l'audit si nécessaire.
            raise RuntimeError(
                "[Agent 06] OPENAI_API_KEY manquante. "
                "Copiez .env.example en .env et ajoutez votre clé OpenAI."
            )

        self.llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)

        base_parser = PydanticOutputParser(pydantic_object=PostProductionOutput)
        self.parser = OutputFixingParser.from_llm(parser=base_parser, llm=self.llm)
        self.base_parser = base_parser

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_PROMPT),
        ]).partial(format_instructions=base_parser.get_format_instructions())

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
              "needs_gimp_retouching": bool,
              "gimp_script": str,
              "needs_video_editing": bool,
              "video_editing_notes": str,
            }

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

        # Validation croisée : si un outil est signalé nécessaire mais que le
        # contenu associé est vide, on désactive le déclenchement plutôt que
        # de proposer une commande qui n'exécuterait rien d'utile.
        needs_gimp = response.needs_gimp_retouching and bool(response.gimp_script.strip())
        needs_video = response.needs_video_editing and bool(response.video_editing_notes.strip())

        saved_gimp_path = ""
        if needs_gimp:
            saved_gimp_path = self._sauvegarder_gimp(response.gimp_script)

        self._last_result = response
        self._last_needs_gimp = needs_gimp
        self._last_needs_video = needs_video
        self._last_saved_gimp_path = saved_gimp_path

        return {
            "coherence_score":       response.coherence_score,
            "issues":                response.issues,
            "needs_gimp_retouching": needs_gimp,
            "gimp_script":           response.gimp_script if needs_gimp else "",
            "gimp_saved_path":       saved_gimp_path,
            "needs_video_editing":   needs_video,
            "video_editing_notes":   response.video_editing_notes if needs_video else "",
        }

    def _sauvegarder_gimp(self, code: str) -> str:
        """Sauvegarde le script GIMP Python-Fu dans agents/output/."""
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, "retouche_gimp.py")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return filepath

    def afficher_rapport(self) -> str:
        """Retourne un résumé formaté de la dernière analyse de conformité."""
        r = getattr(self, "_last_result", None)
        if r is None:
            return "Aucune analyse effectuée."

        lignes = [
            f"SCORE DE COHÉRENCE : {r.coherence_score}/100",
            f"PROBLÈMES IDENTIFIÉS : {r.issues}",
            "",
        ]

        if getattr(self, "_last_needs_gimp", False):
            lignes.append(f"🎨 Retouche GIMP nécessaire → {getattr(self, '_last_saved_gimp_path', '—')}")
        else:
            lignes.append("🎨 Retouche GIMP : non nécessaire")

        if getattr(self, "_last_needs_video", False):
            lignes.append(f"🎬 Montage vidéo nécessaire :\n   {r.video_editing_notes}")
        else:
            lignes.append("🎬 Montage vidéo (Kdenlive/Shotcut) : non nécessaire")

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
