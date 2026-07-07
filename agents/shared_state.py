"""
shared_state.py — Schéma de données partagé entre tous les agents.
LangChain lit et met à jour cet état à chaque étape de la chaîne.
"""

from pydantic import BaseModel, Field
from typing import Optional


class ProjectState(BaseModel):
    """État global du projet cinématographique."""

    # Entrée initiale
    idea: str = Field(default="", description="L'idée de film brute fournie par l'utilisateur")

    # Sorties de l'Agent 01 — Directeur
    director_vision: str = Field(default="", description="La vision artistique globale du directeur")
    genre: str = Field(default="", description="Genre cinématographique (sci-fi, drame, horreur...)")
    tone: str = Field(default="", description="Ton du film (sombre, épique, poétique...)")

    # Sorties de l'Agent 02 — Architecte Narratif
    synopsis: str = Field(default="", description="Résumé complet de l'histoire")
    acts: str = Field(default="", description="Structure en actes (setup / confrontation / résolution)")
    key_scenes: str = Field(default="", description="Scènes clés décrites en détail")

    # Sorties de l'Agent 03 — Scénariste
    screenplay_excerpt: str = Field(default="", description="Extrait de scénario formaté (dialogues, actions)")
    character_sheet: str = Field(default="", description="Fiches personnages avec motivations")

    # Sorties de l'Agent 04 — Directeur Artistique (Blender)
    blender_script: str = Field(default="", description="Script Python prêt pour Blender")
    visual_style: str = Field(default="", description="Description du style visuel et de l'ambiance 3D")

    # Sorties de l'Agent 05 — Directeur Technique (Unreal)
    unreal_script: str = Field(default="", description="Script shell/Blueprint pour Unreal Engine")
    technical_notes: str = Field(default="", description="Notes techniques de production")


# ─── Schémas de sortie structurée par agent ──────────────────────────────────
# Chaque agent dispose de son propre schéma Pydantic avec des champs explicites.
# Cela rend la propagation d'état déterministe et élimine le parsing heuristique.

class DirectorOutput(BaseModel):
    """Sortie structurée de l'Agent 01 — Directeur."""
    genre: str = Field(description="Genre cinématographique précis (ex: science-fiction contemplative)")
    tone: str = Field(description="Ton du film (ex: sombre, épique, poétique, onirique)")
    director_vision: str = Field(description="Vision artistique globale en 3 à 5 phrases")


class NarrativeOutput(BaseModel):
    """Sortie structurée de l'Agent 02 — Architecte Narratif."""
    synopsis: str = Field(description="Résumé de l'histoire en 100 à 150 mots")
    acts: str = Field(description="Structure en 3 actes avec tournants dramatiques")
    key_scenes: str = Field(description="3 scènes clés décrites (ouverture, climax, résolution)")


class ScreenwriterOutput(BaseModel):
    """Sortie structurée de l'Agent 03 — Scénariste."""
    character_sheet: str = Field(description="Fiche de chaque personnage principal : nom, âge, motivation, faille")
    screenplay_excerpt: str = Field(description="Extrait de scénario en format Hollywood (INT./EXT., dialogues)")


class ArtDirectorOutput(BaseModel):
    """Sortie structurée de l'Agent 04 — Directeur Artistique."""
    visual_style: str = Field(description="Description du style visuel, palette, ambiance lumineuse")
    blender_script: str = Field(description="Script Python complet et fonctionnel pour Blender (commence par import bpy)")
    filename: str = Field(description="Nom du fichier Python à créer (ex: scene_01_opening.py)")


class TechDirectorOutput(BaseModel):
    """Sortie structurée de l'Agent 05 — Directeur Technique."""
    technical_notes: str = Field(description="Notes de production : workflow Blender→Unreal, assets, contraintes")
    unreal_script: str = Field(description="Script Shell ou Python Unreal Engine complet et fonctionnel")
    filename: str = Field(description="Nom du fichier à créer (ex: setup_scene_01.sh)")


# ─── Réponses génériques (conservées pour compatibilité) ─────────────────────

class AgentTextResponse(BaseModel):
    """Format de réponse narrative (texte pur) — usage générique."""
    content: str = Field(description="Contenu narratif ou conceptuel de l'agent")


class AgentCodeResponse(BaseModel):
    """Format de réponse avec code technique — usage générique."""
    narrative: str = Field(description="Explication textuelle de ce que fait le code")
    code: str = Field(description="Code Python (Blender) ou Shell (Unreal), prêt à l'emploi")
    filename: str = Field(description="Nom du fichier à créer (ex: scene_01_blender.py)")
