"""
schemas.py — Schémas de sortie structurée pour les agents du Générateur d'Univers.

Tous les agents rédacteurs utilisent PydanticOutputParser (via BaseAgent) pour
obtenir des JSON fiables et directement enregistrables dans la bible du projet.
"""

from pydantic import BaseModel, Field
from typing import Optional


class FicheEntite(BaseModel):
    """Fiche d'identité d'une entité de l'univers (humain, animal, insecte,
    objet, plante)."""

    nom: str = Field(description="Nom unique de l'entité dans l'univers")
    categorie: str = Field(description="Catégorie : characters, objects, flora")
    type: str = Field(
        description="Type précis : Humain, Animal, Insecte, Objet, Plante, Arbre, etc.")

    # Physique
    taille_cm: Optional[int] = Field(
        default=None, description="Taille approximative en centimètres")
    poids_kg: Optional[float] = Field(
        default=None, description="Poids approximatif en kilogrammes")
    apparence: str = Field(
        description="Description physique détaillée (formes, proportions, couleurs, textures)")

    # Caractère / comportement (optionnel selon le type)
    caractere: str = Field(
        default="", description="Tempérament, comportement, psychologie ou instincts")

    # Lore
    lore: str = Field(
        description="Histoire, origine, rôle ou importance dans l'univers")

    # Mots-clés pour le prompt SD
    tags_visuels: list[str] = Field(
        description="Liste de mots-clés visuels pertinents pour un croquis")

    # Direction artistique implicite
    style_souhaite: str = Field(
        default="pencil sketch, technical drawing, white background, isolated subject",
        description="Style artistique recommandé pour le croquis")

    class Config:
        json_schema_extra = {
            "example": {
                "nom": "Kael Vorn",
                "categorie": "characters",
                "type": "Humain",
                "taille_cm": 178,
                "poids_kg": 72,
                "apparence": "Cheveux blancs courts, cicatrice sous l'œil gauche, manteau en cuir usé.",
                "caractere": "Méfiant, calculateur, loyal envers les siens.",
                "lore": "Ancien chasseur de primes devenu protecteur d'un village isolé.",
                "tags_visuels": ["human male", "white hair", "scar", "leather coat"],
                "style_souhaite": "pencil sketch, technical drawing, white background, isolated subject"
            }
        }


class PromptSD(BaseModel):
    """Prompt optimisé pour Stable Diffusion — croquis technique uniquement."""

    positive: str = Field(
        description="Prompt positif, uniquement pour un croquis technique isolé")
    negative: str = Field(
        default="background, landscape, scene, complex environment, colors, painting, blurry, low quality",
        description="Prompt négatif pour éviter scènes, arrière-plans et illustrations finales")
    parametres: dict = Field(
        default_factory=dict,
        description="Paramètres suggérés : width, height, steps, cfg_scale, sampler")


class ResultatCroquis(BaseModel):
    """Résultat d'une génération d'image."""

    chemin_image: str = Field(description="Chemin du fichier PNG généré")
    seed_utilisee: int = Field(default=-1, description="Seed utilisée par Stable Diffusion")
    modele_utilise: str = Field(default="", description="Nom du modèle/checkpoint utilisé")
    duree_s: float = Field(default=0.0, description="Durée de la génération en secondes")


class ResultatDecoupe(BaseModel):
    """Résultat de la découpe d'un croquis en vues orthographiques."""

    vues: dict = Field(description="Dict {'face': chemin, 'profile': chemin, 'back': chemin, ...}")
    dimensions: dict = Field(default_factory=dict, description="Dimensions de l'image source")
