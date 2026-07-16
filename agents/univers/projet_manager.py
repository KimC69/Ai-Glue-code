"""
projet_manager.py — Gestion cloisonnée des projets pour le Générateur d'Univers.

Structure imposée par projet :
    /projects/[NOM_DU_PROJET]/
        /universe_bible/
            /characters/      # Fiches JSON d'identité (humains, animaux, insectes)
            /objects/         # Fiches JSON d'objets (reliques, outils)
            /flora/           # Fiches JSON de végétation
        /sketches/            # Croquis générés (.png)
            /characters/
            /objects/
            /flora/
        /models/              # Modèles Civitai (.safetensors)

Toutes les créations sont triées par catégorie. Rien ne se mélange entre projets.
"""

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional

from .config import DOSSIER_DEFAUT


# Catégories acceptées par le studio univers
CATEGORIES = ("characters", "objects", "flora")


def slugifier(nom: str) -> str:
    """Transforme un nom libre en identifiant de dossier sûr."""
    base = unicodedata.normalize("NFKD", str(nom))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not slug:
        raise ValueError("Nom de projet invalide : aucun caractère exploitable.")
    return slug


def _horodatage() -> str:
    """Horodatage UTC ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ecrire_atomique(chemin: str, contenu: str) -> None:
    """Écriture atomique « échoue fermé »."""
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = f"{chemin}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporaire, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.replace(temporaire, chemin)
    except OSError:
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise


def racine_projets(dossier: str = "") -> str:
    """Racine des dossiers de projets."""
    return dossier or DOSSIER_DEFAUT


def chemin_projet(nom: str, dossier: str = "") -> str:
    """Chemin absolu du dossier d'un projet."""
    return os.path.join(racine_projets(dossier), slugifier(nom))


def creer_ou_ouvrir(nom: str, dossier: str = "") -> dict:
    """Crée la structure complète d'un projet si elle n'existe pas,
    ou ouvre un projet existant sans l'écraser.

    Retourne {"slug", "nom", "chemin", "cree_le"}."""
    slug = slugifier(nom)
    chemin = chemin_projet(nom, dossier)
    meta = lire_meta(slug, dossier)
    cree_le = meta.get("cree_le") or _horodatage()

    # Création de toute l'arborescence
    for categorie in CATEGORIES:
        os.makedirs(os.path.join(chemin, "universe_bible", categorie), exist_ok=True)
        os.makedirs(os.path.join(chemin, "sketches", categorie), exist_ok=True)
    os.makedirs(os.path.join(chemin, "models"), exist_ok=True)

    nouvelle_meta = {
        "slug": slug,
        "nom": str(nom).strip() or slug,
        "cree_le": cree_le,
        "modifie_le": _horodatage(),
    }
    _ecrire_atomique(
        os.path.join(chemin, "meta.json"),
        json.dumps(nouvelle_meta, ensure_ascii=False, indent=2),
    )
    return {
        "slug": slug,
        "nom": nouvelle_meta["nom"],
        "chemin": chemin,
        "cree_le": cree_le,
    }


def lire_meta(slug: str, dossier: str = "") -> dict:
    """Lit les métadonnées d'un projet (« échoue sûr »)."""
    chemin = os.path.join(racine_projets(dossier), slug, "meta.json")
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            objet = json.load(f)
    except (OSError, ValueError):
        return {}
    return objet if isinstance(objet, dict) else {}


def lister_projets(dossier: str = "") -> list:
    """Liste les projets existants, du plus récent au plus ancien."""
    racine = racine_projets(dossier)
    try:
        slugs = [d for d in os.listdir(racine)
                 if os.path.isdir(os.path.join(racine, d))]
    except OSError:
        return []
    projets = []
    for slug in slugs:
        meta = lire_meta(slug, dossier)
        projets.append({
            "slug": slug,
            "nom": meta.get("nom", slug),
            "cree_le": meta.get("cree_le", ""),
            "modifie_le": meta.get("modifie_le", ""),
            "chemin": os.path.join(racine, slug),
        })
    projets.sort(key=lambda p: p["modifie_le"], reverse=True)
    return projets


def chemin_bible(projet: dict, categorie: str, nom_fiche: str) -> str:
    """Chemin d'une fiche JSON dans la bible du projet."""
    if categorie not in CATEGORIES:
        raise ValueError(f"Catégorie inconnue : {categorie}. Choix : {CATEGORIES}")
    nom_json = re.sub(r"\.json$", "", nom_fiche) + ".json"
    return os.path.join(projet["chemin"], "universe_bible", categorie, nom_json)


def chemin_croquis(projet: dict, categorie: str, nom_fiche: str) -> str:
    """Chemin d'un croquis PNG dans le projet."""
    if categorie not in CATEGORIES:
        raise ValueError(f"Catégorie inconnue : {categorie}. Choix : {CATEGORIES}")
    nom_png = re.sub(r"\.(png|jpg|jpeg)$", "", nom_fiche, flags=re.I) + ".png"
    return os.path.join(projet["chemin"], "sketches", categorie, nom_png)


def chemin_modeles(projet: dict) -> str:
    """Chemin du dossier de modèles Civitai du projet."""
    return os.path.join(projet["chemin"], "models")


def sauver_fiche(projet: dict, categorie: str, nom: str, contenu: dict) -> str:
    """Enregistre une fiche JSON dans la bible du projet."""
    chemin = chemin_bible(projet, categorie, nom)
    _ecrire_atomique(
        chemin,
        json.dumps(contenu, ensure_ascii=False, indent=2, default=str),
    )
    return chemin


def lire_fiche(projet: dict, categorie: str, nom: str) -> dict:
    """Lit une fiche JSON (« échoue sûr »)."""
    chemin = chemin_bible(projet, categorie, nom)
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def lister_fiches(projet: dict, categorie: str) -> list:
    """Liste les fiches JSON d'une catégorie."""
    if categorie not in CATEGORIES:
        return []
    dossier = os.path.join(projet["chemin"], "universe_bible", categorie)
    try:
        return [f for f in os.listdir(dossier) if f.endswith(".json")]
    except OSError:
        return []


def lister_croquis(projet: dict, categorie: str) -> list:
    """Liste les croquis PNG d'une catégorie."""
    if categorie not in CATEGORIES:
        return []
    dossier = os.path.join(projet["chemin"], "sketches", categorie)
    try:
        return [f for f in os.listdir(dossier)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    except OSError:
        return []


def lister_modeles(projet: dict) -> list:
    """Liste les modèles .safetensors du projet."""
    dossier = chemin_modeles(projet)
    try:
        return [f for f in os.listdir(dossier) if f.endswith(".safetensors")]
    except OSError:
        return []
