"""
memoire.py — Mémoire et objectifs persistants du studio.

Deux notions distinctes, regroupées ici car ce sont les deux formes de
« mémoire » que les interfaces (API, PWA, bureau) donnent à consulter et à gérer :

1. LES OBJECTIFS DU PRODUCTEUR (output/objectifs.json) : une note libre et
   persistante — ligne éditoriale, contraintes, préférences. Elle est INJECTÉE
   au lancement de chaque nouvelle production (transmise au Directeur Créatif),
   pour orienter durablement le studio sans la retaper à chaque idée.

2. L'ÉTAT DE TRAVAIL (output/world_state.json) : la mémoire vive de la dernière
   production (vision, scénario, scripts générés…). On peut la RÉSUMER (pour
   voir ce que le studio « a en tête ») et la RÉINITIALISER (repartir propre).

Lecture « échoue sûr » (jamais d'exception : au pire, contenu vide) ; écriture
« échoue fermé » (OSError laissée remonter pour que l'interface signale l'échec).

Ce module lit/écrit le fichier world_state.json en JSON brut (bibliothèque
standard), SANS importer shared_state : les interfaces restent ainsi légères et
testables sans les dépendances du pipeline (pydantic, langchain).
"""

import json
import os
from datetime import datetime, timezone

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
NOM_OBJECTIFS = "objectifs.json"
NOM_WORLD_STATE = "world_state.json"

# Longueur au-delà de laquelle une valeur de l'état est tronquée dans le résumé
# (les scripts générés font des milliers de caractères : inutile de tout servir).
_APERCU_MAX = 200


def _chemin(nom: str, dossier: str = "") -> str:
    return os.path.join(dossier or DOSSIER_DEFAUT, nom)


def _ecrire_atomique(chemin: str, contenu: str) -> None:
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        f.write(contenu)
    os.replace(temporaire, chemin)


# ── Objectifs persistants ─────────────────────────────────────────────────────

def lire_objectifs(dossier: str = "") -> dict:
    """Retourne {"texte", "modifie_le", "par"} ; champs vides si aucun objectif."""
    vide = {"texte": "", "modifie_le": "", "par": ""}
    try:
        with open(_chemin(NOM_OBJECTIFS, dossier), "r", encoding="utf-8") as f:
            objet = json.load(f)
    except (OSError, ValueError):
        return vide
    if not isinstance(objet, dict):
        return vide
    return {
        "texte": str(objet.get("texte", "")),
        "modifie_le": str(objet.get("modifie_le", "")),
        "par": str(objet.get("par", "")),
    }


def ecrire_objectifs(texte: str, par: str = "", modifie_le: str = "",
                     dossier: str = "") -> dict:
    """Enregistre la note d'objectifs (« échoue fermé »). Retourne l'objet écrit.
    `modifie_le` est horodaté automatiquement (UTC ISO 8601) s'il est vide."""
    if not modifie_le:
        modifie_le = datetime.now(timezone.utc).isoformat(timespec="seconds")
    objet = {"texte": str(texte), "modifie_le": str(modifie_le), "par": str(par)}
    _ecrire_atomique(_chemin(NOM_OBJECTIFS, dossier),
                     json.dumps(objet, ensure_ascii=False, indent=2))
    return objet


# ── État de travail (world_state) ─────────────────────────────────────────────

def resume_world_state(dossier: str = "") -> dict:
    """Résumé lisible de l'état : uniquement les clés renseignées, valeurs
    longues tronquées. Renvoie {"present": bool, "production_id", "cles": {...}}."""
    try:
        with open(_chemin(NOM_WORLD_STATE, dossier), "r", encoding="utf-8") as f:
            etat = json.load(f)
    except (OSError, ValueError):
        return {"present": False, "production_id": "", "cles": {}}
    if not isinstance(etat, dict):
        return {"present": False, "production_id": "", "cles": {}}

    cles = {}
    for cle, valeur in etat.items():
        if valeur in ("", None, [], {}):
            continue
        texte = valeur if isinstance(valeur, str) else json.dumps(
            valeur, ensure_ascii=False, default=str)
        if len(texte) > _APERCU_MAX:
            texte = texte[:_APERCU_MAX] + "…"
        cles[cle] = texte
    return {
        "present": True,
        "production_id": str(etat.get("production_id", "")),
        "cles": cles,
    }


def reinitialiser_world_state(dossier: str = "") -> bool:
    """Efface l'état de travail (« échoue sûr » : ignore son absence). Retourne
    True si un fichier a été supprimé, False s'il n'y en avait pas."""
    try:
        os.remove(_chemin(NOM_WORLD_STATE, dossier))
        return True
    except OSError:
        return False
