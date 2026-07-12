"""
shared_state.py — La "Bible de production" partagée entre tous les agents.
WorldState est la mémoire commune : chaque agent peut y lire et écrire.
"""

import json
import os
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any


# ─── Mémoire commune (WorldState) ─────────────────────────────────────────────

class WorldState:
    """
    Mémoire partagée entre tous les agents du studio.
    
    Utilisation :
        state = WorldState()
        state.update("vision_globale", "Un film sous-marin...")
        state.save()  # → persiste dans output/world_state.json
    """

    SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "world_state.json")

    def __init__(self):
        # Données de l'état — chaque agent ajoute sa clé
        self._data: dict[str, Any] = {
            "idea": "",
            "vision_globale": "",
            "genre": "",
            "tone": "",
            "synopsis": "",
            "acts": "",
            "key_scenes": "",
            "character_sheet": "",
            "screenplay_excerpt": "",
            "visual_style": "",
            "blender_script": "",
            "technical_notes": "",
            "unreal_script": "",
            "coherence_score": "",
            "issues": "",
            "needs_gimp_retouching": "",
            "gimp_script": "",
            "needs_video_editing": "",
            "video_editing_notes": "",
            "needs_inkscape": "",
            "inkscape_notes": "",
            "needs_darktable": "",
            "darktable_notes": "",
            "needs_krita": "",
            "krita_script": "",
            "needs_obs": "",
            "obs_notes": "",
            "export_formats": "",
            "ffmpeg_script": "",
            "mood_musical": "",
            "csound_script": "",
            "last_updated": "",
        }

    def update(self, key: str, value: Any) -> None:
        """
        Met à jour une clé de l'état partagé.
        
        Args:
            key: La clé à mettre à jour (ex: "vision_globale")
            value: La valeur à enregistrer
        """
        self._data[key] = value
        self._data["last_updated"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    def get(self, key: str, default: Any = "") -> Any:
        """
        Lit une valeur de l'état partagé.
        
        Args:
            key: La clé à lire
            default: Valeur par défaut si la clé est absente
        """
        return self._data.get(key, default)

    def save(self) -> str:
        """
        Persiste l'état complet dans output/world_state.json.
        
        Returns:
            Chemin du fichier sauvegardé
        """
        os.makedirs(os.path.dirname(self.SAVE_PATH), exist_ok=True)
        with open(self.SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        return self.SAVE_PATH

    def load(self) -> bool:
        """
        Charge l'état depuis output/world_state.json (si existant).
        
        Returns:
            True si chargé avec succès, False sinon
        """
        if os.path.exists(self.SAVE_PATH):
            with open(self.SAVE_PATH, encoding="utf-8") as f:
                self._data.update(json.load(f))
            return True
        return False

    def to_dict(self) -> dict:
        """Retourne une copie de l'état complet."""
        return dict(self._data)

    def __repr__(self) -> str:
        filled = {k: v for k, v in self._data.items() if v}
        return f"WorldState({list(filled.keys())})"


# ─── Schémas de sortie structurée par agent (pour LangChain PydanticOutputParser) ─

class DirectorOutput(BaseModel):
    """Sortie structurée de l'Agent 01 — Directeur Créatif."""
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


class PostProductionOutput(BaseModel):
    """Sortie structurée de l'Agent 06 — Superviseur Post-Production.

    Cet agent évalue la cohérence du résultat produit par les Agents 04/05
    et décide, au cas par cas, si des outils correctifs sont nécessaires.
    Aucun outil n'est déclenché si le résultat est déjà conforme.
    """
    coherence_score: int = Field(description="Score de cohérence du résultat, de 0 à 100")
    issues: str = Field(description="Problèmes de cohérence identifiés, ou 'Aucun' si le résultat est conforme")

    needs_gimp_retouching: bool = Field(description="True si une retouche image (GIMP) est nécessaire pour corriger un problème visuel")
    gimp_script: str = Field(description="Script Script-Fu/Python-Fu GIMP pour la retouche, vide si non nécessaire")

    needs_video_editing: bool = Field(description="True si un montage (Kdenlive/Shotcut) est nécessaire pour assembler/corriger le rendu final")
    video_editing_notes: str = Field(description="Instructions de montage (coupes, transitions, assemblage), vide si non nécessaire")

    needs_inkscape: bool = Field(description="True si une illustration vectorielle (logo, affiche, titre stylisé) est nécessaire")
    inkscape_notes: str = Field(description="Instructions/SVG pour Inkscape (ce qu'il faut illustrer), vide si non nécessaire")

    needs_darktable: bool = Field(description="True si un développement RAW est nécessaire (photos de référence/textures haute qualité)")
    darktable_notes: str = Field(description="Instructions de développement RAW (exposition, balance des blancs, export), vide si non nécessaire")

    needs_krita: bool = Field(description="True si un dessin/peinture numérique est nécessaire (concept art, matte painting, texture peinte)")
    krita_script: str = Field(description="Script Python (API Krita) ou instructions de dessin, vide si non nécessaire")

    needs_obs: bool = Field(description="True si une capture/streaming est nécessaire (ex: capture du rendu Unreal en temps réel)")
    obs_notes: str = Field(description="Instructions de configuration OBS (scène, sources, sortie), vide si non nécessaire")


class ExportMultiFormatOutput(BaseModel):
    """Sortie structurée de l'Agent 07 — Exporteur Multi-Format.

    Cet agent détermine les formats de diffusion pertinents pour le projet
    (TV, téléphone, réseaux sociaux) et génère un script FFmpeg unique qui
    décline la vidéo master dans chaque format.
    """
    formats: list[str] = Field(description="Liste des formats choisis (ex: ['16:9', '9:16', '1:1']), au moins un format requis")
    ffmpeg_script: str = Field(description="Script shell FFmpeg complet et exécutable, commençant par #!/bin/bash")

    @field_validator("formats", mode="after")
    @classmethod
    def _formats_non_vides(cls, v: list[str]) -> list[str]:
        if not v or all(not f.strip() for f in v):
            raise ValueError("Au moins un format d'export doit être choisi.")
        return [f.strip() for f in v if f.strip()]

    @field_validator("ffmpeg_script", mode="after")
    @classmethod
    def _script_exécutable(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le script FFmpeg ne peut pas être vide.")
        if "#!/bin/bash" not in v:
            raise ValueError("Le script FFmpeg doit commencer par #!/bin/bash.")
        return v


class SoundEngineerOutput(BaseModel):
    """Sortie structurée de l'Agent 08 — Ingénieur du Son.

    Cet agent compose la bande originale du film sous forme d'un fichier
    Csound (.csd) autonome, rendu-able en audio sans interface graphique
    (csound bande_son.csd -o bande_son.wav).
    """
    mood_musical: str = Field(description="Ambiance sonore visée : tonalité, tempo, instrumentation, émotion")
    csound_script: str = Field(description="Fichier Csound (.csd) complet, encadré par <CsoundSynthesizer>...</CsoundSynthesizer>")
    filename: str = Field(description="Nom du fichier à créer (ex: bande_son.csd)")

    @field_validator("csound_script", mode="after")
    @classmethod
    def _csd_valide(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le fichier Csound ne peut pas être vide.")
        if "<CsoundSynthesizer>" not in v or "</CsoundSynthesizer>" not in v:
            raise ValueError("Le fichier Csound doit être encadré par <CsoundSynthesizer>...</CsoundSynthesizer>.")
        return v
