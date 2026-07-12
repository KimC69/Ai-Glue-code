"""
controle_production.py — Pilotage À DISTANCE d'une production en cours.

Une production tourne dans un sous-processus détaché (lancé par l'API ou en
ligne de commande) : une fois partie, on ne peut plus lui « parler » par le
clavier. Ce module fournit le canal de commande manquant, sans aucune
dépendance ni socket : un simple FICHIER DE COMMANDE par production.

  output/controle/<production_id>.json   →  {"commande": "pause", ...}

- Les interfaces (API, PWA, bureau) ÉCRIVENT une commande dans ce fichier
  (`ecrire_commande`) : « pause », « reprendre » ou « arreter ».
- L'orchestrateur, au début de chaque étape, LIT ce fichier (`Controleur.lire`)
  et agit en conséquence : se mettre en attente (pause) ou s'arrêter proprement.

Deux philosophies de robustesse, volontairement différentes selon le sens :

  - CÔTÉ ÉCRITURE (interfaces) : « échoue fermé ». Si la commande ne peut pas
    être écrite (disque plein, dossier en lecture seule), on LÈVE l'erreur —
    l'interface doit dire honnêtement « commande non transmise », jamais
    prétendre avoir mis en pause une production qui continue.

  - CÔTÉ LECTURE (orchestrateur) : « échoue SÛR ». Un fichier illisible ou
    corrompu ne doit JAMAIS tuer une production en cours : au moindre doute on
    renvoie « aucune commande » et la production continue son travail.

Bibliothèque standard uniquement (json, os) : testable sans clé ni réseau.
"""

import json
import os
import uuid

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SOUS_DOSSIER = "controle"

# Commandes qu'une interface peut transmettre à une production.
COMMANDES_VALIDES = ("pause", "reprendre", "arreter")


def chemin_controle(production_id: str, dossier: str = "") -> str:
    """Chemin du fichier de commande d'une production."""
    base = dossier or DOSSIER_DEFAUT
    return os.path.join(base, SOUS_DOSSIER, f"{production_id}.json")


def ecrire_commande(production_id: str, commande: str, par: str = "",
                    dossier: str = "") -> None:
    """Transmet une commande à une production (« échoue fermé »).

    Lève ValueError si la commande n'est pas reconnue, et laisse remonter une
    OSError si l'écriture échoue : l'appelant (API) doit alors signaler l'échec
    plutôt que de laisser croire que la commande a été prise en compte.

    L'écriture est ATOMIQUE (fichier temporaire puis os.replace) : l'orchestrateur
    ne lira jamais un fichier à moitié écrit. Le fichier temporaire porte un
    suffixe UNIQUE (uuid) pour que deux écritures simultanées sur la même
    production (deux interfaces, deux onglets…) ne se marchent jamais dessus."""
    if commande not in COMMANDES_VALIDES:
        raise ValueError(
            f"Commande inconnue : {commande!r}. "
            f"Attendu : {', '.join(COMMANDES_VALIDES)}.")
    chemin = chemin_controle(production_id, dossier)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    contenu = json.dumps(
        {"commande": commande, "par": par}, ensure_ascii=False)
    temporaire = f"{chemin}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporaire, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.replace(temporaire, chemin)
    except OSError:
        # Nettoyage « échoue sûr » du temporaire, puis on relaie l'échec
        # à l'appelant (« échoue fermé » côté écriture).
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise


def lire_commande(production_id: str, dossier: str = "") -> str:
    """Lit la commande courante d'une production (« échoue sûr »).

    Renvoie "" (aucune commande) si le fichier est absent, illisible, mal formé
    ou contient une commande inconnue : jamais d'exception, pour qu'une lecture
    ratée n'interrompe jamais une production en cours."""
    chemin = chemin_controle(production_id, dossier)
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            objet = json.load(f)
    except (OSError, ValueError):
        return ""
    if not isinstance(objet, dict):
        return ""
    commande = objet.get("commande", "")
    return commande if commande in COMMANDES_VALIDES else ""


def effacer_commande(production_id: str, dossier: str = "") -> None:
    """Efface le fichier de commande (« échoue sûr » : ignore son absence)."""
    chemin = chemin_controle(production_id, dossier)
    try:
        os.remove(chemin)
    except OSError:
        pass


class Controleur:
    """Vue « côté production » du canal de commande, injectée dans
    l'orchestrateur. Encapsule l'identifiant et le dossier pour que
    l'orchestrateur reste agnostique du mécanisme (fichier ici, mais on
    pourrait le remplacer sans le toucher)."""

    def __init__(self, production_id: str, dossier: str = ""):
        self.production_id = production_id
        self.dossier = dossier

    def lire(self) -> str:
        return lire_commande(self.production_id, self.dossier)

    def effacer(self) -> None:
        effacer_commande(self.production_id, self.dossier)


class ControleNul:
    """Contrôleur inactif (patron « objet nul ») : utilisé quand aucun pilotage
    n'est branché (ligne de commande simple, tests). Aucune commande, jamais."""

    def lire(self) -> str:
        return ""

    def effacer(self) -> None:
        pass
