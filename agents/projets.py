"""
projets.py — Gestion des « projets » (univers de film ou de série).

Un projet regroupe tout ce qui est PROPRE à un film dans son propre dossier
`output/projets/<slug>/` :
  - world_state.json : archive durable de la « bible » créative du film
    (état en mémoire de la production, écrit en fin de production) ;
  - meta.json        : nom affiché, dates, dernière production associée ;
  - scripts et notes générés par le pipeline (rendus, notes_*.txt, …).

Le reste demeure PARTAGÉ dans `output/` (historique studio.db, comptes,
objectifs globaux, canal de pilotage) : un projet n'isole que son contenu
créatif. Cela permet, entre autres, d'écrire une SUITE (saison 2 à partir de la
saison 1) en réutilisant l'état archivé du projet précédent comme référence.

Conventions du studio respectées ici :
  - bibliothèque standard uniquement, docstrings en français ;
  - ÉCRITURE « échoue fermé » : atomique (fichier temporaire UNIQUE +
    os.replace) ; si l'écriture échoue, la fonction LÈVE — on ne fait jamais
    croire à un succès ;
  - LECTURE « échoue sûr » : un projet ou un état absent renvoie une valeur
    vide, jamais d'exception — c'est l'appelant qui décide de refuser ou de
    continuer.
"""

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "output")
SOUS_DOSSIER_PROJETS = "projets"
NOM_META = "meta.json"
NOM_WORLD_STATE = "world_state.json"

# Clés créatives réellement utiles pour écrire une suite cohérente, dans
# l'ordre où on les présente à l'agent (les scripts techniques bruts sont
# volontairement exclus : ils n'aident pas à concevoir un scénario).
_CLES_REFERENCE = (
    ("idea", "Idée d'origine"),
    ("vision_globale", "Vision"),
    ("genre", "Genre"),
    ("tone", "Ton"),
    ("synopsis", "Synopsis"),
    ("acts", "Structure en actes"),
    ("key_scenes", "Scènes clés"),
    ("character_sheet", "Personnages"),
    ("screenplay_excerpt", "Extrait de scénario"),
    ("visual_style", "Style visuel"),
)


def _horodatage() -> str:
    """Horodatage UTC ISO 8601 (à la seconde), comme le reste du studio."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugifier(nom: str) -> str:
    """Transforme un nom de projet libre en identifiant de dossier sûr :
    minuscules, sans accents, seuls les caractères [a-z0-9-] conservés.
    Ex. « Alien 2 : le Retour » → « alien-2-le-retour ».

    Lève ValueError si le résultat est vide (nom composé uniquement de
    caractères non exploitables) — « échoue fermé » : on refuse de créer un
    dossier au nom vide plutôt que d'en inventer un."""
    base = unicodedata.normalize("NFKD", str(nom))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not slug:
        raise ValueError(
            "nom de projet invalide : aucun caractère exploitable pour en "
            "faire un dossier.")
    return slug


def dossier_projets(dossier: str = "") -> str:
    """Chemin de la racine des projets (`output/projets/`)."""
    return os.path.join(dossier or DOSSIER_DEFAUT, SOUS_DOSSIER_PROJETS)


def chemin_projet(slug: str, dossier: str = "") -> str:
    """Chemin du dossier d'un projet à partir de son slug."""
    return os.path.join(dossier_projets(dossier), slug)


def projet_existe(slug: str, dossier: str = "") -> bool:
    """True si le dossier du projet existe (« échoue sûr »)."""
    return os.path.isdir(chemin_projet(slug, dossier))


def _ecrire_atomique(chemin: str, contenu: str) -> None:
    """Écriture atomique « échoue fermé ». Le fichier temporaire porte un
    suffixe UNIQUE (uuid) pour éviter toute collision entre écritures
    concurrentes ; en cas d'échec, le temporaire est nettoyé et l'erreur
    remonte à l'appelant."""
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


def lire_meta(slug: str, dossier: str = "") -> dict:
    """Métadonnées d'un projet (« échoue sûr » : projet absent → dict vide)."""
    chemin = os.path.join(chemin_projet(slug, dossier), NOM_META)
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            objet = json.load(f)
    except (OSError, ValueError):
        return {}
    return objet if isinstance(objet, dict) else {}


def creer_ou_ouvrir(nom: str, dossier: str = "") -> dict:
    """Crée le dossier d'un projet (et son meta.json) s'il n'existe pas, ou
    ouvre un projet existant en préservant sa date de création.

    « Échoue fermé » : toute écriture ratée LÈVE (OSError). Retourne un dict
    {"slug", "nom", "chemin", "cree_le"}."""
    slug = slugifier(nom)
    chemin = chemin_projet(slug, dossier)
    meta_existante = lire_meta(slug, dossier)
    cree_le = meta_existante.get("cree_le") or _horodatage()
    meta = {
        "slug": slug,
        "nom": str(nom).strip() or slug,
        "cree_le": cree_le,
        "modifie_le": _horodatage(),
        "derniere_production": meta_existante.get("derniere_production", ""),
        "dernier_statut": meta_existante.get("dernier_statut", ""),
    }
    _ecrire_atomique(os.path.join(chemin, NOM_META),
                     json.dumps(meta, ensure_ascii=False, indent=2))
    return {"slug": slug, "nom": meta["nom"], "chemin": chemin,
            "cree_le": cree_le}


def enregistrer_production(slug: str, production_id: str, statut: str = "",
                           dossier: str = "") -> None:
    """Note dans meta.json la dernière production liée au projet
    (« échoue fermé »). Sans effet si le projet n'a pas de meta (rien à mettre
    à jour)."""
    meta = lire_meta(slug, dossier)
    if not meta:
        return
    meta["derniere_production"] = str(production_id)
    if statut:
        meta["dernier_statut"] = str(statut)
    meta["modifie_le"] = _horodatage()
    _ecrire_atomique(os.path.join(chemin_projet(slug, dossier), NOM_META),
                     json.dumps(meta, ensure_ascii=False, indent=2))


def lister_projets(dossier: str = "") -> list:
    """Liste des projets (« échoue sûr » : [] si aucun / dossier absent).
    Chaque entrée : {"slug", "nom", "cree_le", "modifie_le", "a_un_etat"},
    triée par date de modification décroissante (le plus récent en premier)."""
    racine = dossier_projets(dossier)
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
            "derniere_production": meta.get("derniere_production", ""),
            "a_un_etat": os.path.exists(
                os.path.join(chemin_projet(slug, dossier), NOM_WORLD_STATE)),
        })
    projets.sort(key=lambda p: p.get("modifie_le", ""), reverse=True)
    return projets


def archiver_etat(slug: str, etat: dict, dossier: str = "") -> str:
    """Archive l'état créatif d'une production dans le dossier du projet, pour le
    réutiliser plus tard comme référence d'une suite.

    On reçoit l'état EN MÉMOIRE de la production courante (un dict, via
    `WorldState.to_dict()`) plutôt que de recopier le fichier global
    `output/world_state.json` : ainsi deux productions simultanées ne risquent
    pas d'archiver l'état l'une de l'autre.

    « Échoue fermé » côté écriture (lève si l'archive échoue). Renvoie le chemin
    de l'archive écrite."""
    cible = os.path.join(chemin_projet(slug, dossier), NOM_WORLD_STATE)
    _ecrire_atomique(cible, json.dumps(etat, ensure_ascii=False, indent=2,
                                       default=str))
    return cible


def resume_reference(slug: str, dossier: str = "", apercu_max: int = 1500) -> str:
    """Construit un bloc texte RÉFÉRENCE à partir de l'état archivé d'un projet
    source, destiné à être injecté dans le pipeline pour écrire une SUITE
    cohérente (mêmes univers, personnages et ton).

    « Échoue sûr » : renvoie "" si le projet ou son état est absent/illisible.
    Ne sert que les clés créatives utiles ; les longues valeurs sont tronquées
    pour ne pas noyer le prompt."""
    chemin = os.path.join(chemin_projet(slug, dossier), NOM_WORLD_STATE)
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            etat = json.load(f)
    except (OSError, ValueError):
        return ""
    if not isinstance(etat, dict):
        return ""
    lignes = []
    for cle, etiquette in _CLES_REFERENCE:
        valeur = etat.get(cle)
        if not valeur:
            continue
        texte = valeur if isinstance(valeur, str) else json.dumps(
            valeur, ensure_ascii=False, default=str)
        texte = texte.strip()
        if not texte:
            continue
        if len(texte) > apercu_max:
            texte = texte[:apercu_max] + "…"
        lignes.append(f"- {etiquette} : {texte}")
    return "\n".join(lignes)
