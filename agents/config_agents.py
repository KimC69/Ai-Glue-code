"""
config_agents.py — Activation / désactivation des agents du pipeline.

Permet aux interfaces (API, PWA, bureau) de choisir quels agents participent à
une production, et de le faire persister d'un lancement à l'autre.

  output/agents_config.json   →  {"6": false, "7": true, ...}   (numéro → actif)

Règle centrale, honnête et non contournable : les agents 1 à 5 forment la
CHAÎNE CRÉATIVE INDISPENSABLE (vision → structure → scénario → Blender →
Unreal). Chacun consomme les sorties du précédent ; en désactiver un casserait
tout ce qui suit. Ces agents sont donc marqués « non optionnels » et NE PEUVENT
PAS être désactivés — on refuse clairement plutôt que de produire un pipeline
bancal. Seuls les agents 6, 7 et 8 (audit, exports, bande son), qui ne bloquent
jamais la production, sont désactivables.

Ce module ne crée PAS de nouvel agent : il ne fait qu'activer ou non ceux qui
existent déjà (créer un vrai agent supplémentaire est un travail de code, pas
un réglage).

Bibliothèque standard uniquement (json, os) : testable sans clé ni réseau.
"""

import json
import os

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
NOM_FICHIER = "agents_config.json"

# Catalogue des agents du pipeline. Source unique pour les interfaces (liste et
# libellés) et pour le chat interactif (fichier + classe à charger). Le champ
# `optionnel` distingue les agents désactivables (6, 7, 8) de la chaîne créative
# indispensable (1 à 5).
CATALOGUE_AGENTS = [
    {"numero": 1, "nom": "Directeur Créatif",
     "fichier": "01_directeur_creatif.py", "classe": "DirecteurCreatif",
     "optionnel": False,
     "role": "directeur créatif d'un studio de cinéma, qui définit la vision "
             "artistique globale d'un film (genre, ton, intention)"},
    {"numero": 2, "nom": "Architecte Narratif",
     "fichier": "02_architecte_narratif.py", "classe": "ArchitecteNarratif",
     "optionnel": False,
     "role": "architecte narratif, qui bâtit la structure d'un film "
             "(synopsis, actes, scènes clés)"},
    {"numero": 3, "nom": "Scénariste",
     "fichier": "03_scenariste.py", "classe": "Scenariste",
     "optionnel": False,
     "role": "scénariste, qui écrit personnages et dialogues"},
    {"numero": 4, "nom": "Directeur Artistique",
     "fichier": "04_directeur_artistique.py", "classe": "DirecteurArtistique",
     "optionnel": False,
     "role": "directeur artistique, qui conçoit l'univers visuel et génère des "
             "scènes Blender"},
    {"numero": 5, "nom": "Directeur Technique",
     "fichier": "05_directeur_technique.py", "classe": "DirecteurTechnique",
     "optionnel": False,
     "role": "directeur technique, qui prépare le rendu temps réel (Unreal Engine)"},
    {"numero": 6, "nom": "Superviseur Post-Production",
     "fichier": "06_superviseur_post_production.py",
     "classe": "SuperviseurPostProduction", "optionnel": True,
     "role": "superviseur de post-production, qui audite la cohérence de "
             "l'ensemble"},
    {"numero": 7, "nom": "Exporteur Multi-Format",
     "fichier": "07_exporteur_multi_format.py", "classe": "ExporteurMultiFormat",
     "optionnel": True,
     "role": "exporteur multi-format, qui prépare les livrables (FFmpeg)"},
    {"numero": 8, "nom": "Ingénieur du Son",
     "fichier": "08_ingenieur_son.py", "classe": "IngenieurSon",
     "optionnel": True,
     "role": "ingénieur du son, qui compose la bande originale (Csound)"},
]

# Recherche rapide par numéro.
_PAR_NUMERO = {a["numero"]: a for a in CATALOGUE_AGENTS}


def _chemin(dossier: str = "") -> str:
    return os.path.join(dossier or DOSSIER_DEFAUT, NOM_FICHIER)


def agent(numero: int) -> dict:
    """Retourne l'entrée de catalogue d'un agent, ou lève ValueError."""
    entree = _PAR_NUMERO.get(int(numero))
    if entree is None:
        raise ValueError(f"Agent inconnu : {numero}.")
    return entree


def charger_config(dossier: str = "") -> dict:
    """Charge la config d'activation : {numero(int): actif(bool)}.

    « Échoue sûr » : un fichier absent, illisible ou mal formé donne une config
    vide (donc tous les agents actifs par défaut). Les entrées inconnues ou de
    mauvais type sont ignorées."""
    try:
        with open(_chemin(dossier), "r", encoding="utf-8") as f:
            brut = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(brut, dict):
        return {}
    config = {}
    for cle, valeur in brut.items():
        try:
            numero = int(cle)
        except (TypeError, ValueError):
            continue
        if numero in _PAR_NUMERO and isinstance(valeur, bool):
            config[numero] = valeur
    return config


def enregistrer_config(config: dict, dossier: str = "") -> None:
    """Écrit la config d'activation de façon atomique. Laisse remonter une
    OSError (« échoue fermé » : l'interface doit signaler l'échec)."""
    chemin = _chemin(dossier)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    contenu = json.dumps({str(k): v for k, v in sorted(config.items())},
                         ensure_ascii=False, indent=2)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        f.write(contenu)
    os.replace(temporaire, chemin)


def est_actif(numero: int, config=None, dossier: str = "") -> bool:
    """Un agent est actif s'il est indispensable (toujours) OU si la config ne
    l'a pas explicitement désactivé (actif par défaut)."""
    entree = _PAR_NUMERO.get(int(numero))
    if entree is None:
        return False
    if not entree["optionnel"]:
        return True
    if config is None:
        config = charger_config(dossier)
    return config.get(int(numero), True)


def definir_agent(numero: int, actif: bool, dossier: str = "") -> dict:
    """Active ou désactive un agent optionnel, et persiste le choix.

    Lève ValueError si l'agent est inconnu, ou si l'on tente de désactiver un
    agent indispensable (chaîne créative 1 à 5). Retourne la config mise à jour."""
    entree = agent(numero)
    numero = int(numero)
    if not entree["optionnel"] and not actif:
        raise ValueError(
            f"L'agent {numero} ({entree['nom']}) est indispensable à la chaîne "
            "créative et ne peut pas être désactivé.")
    config = charger_config(dossier)
    config[numero] = bool(actif)
    enregistrer_config(config, dossier)
    return config


def liste_agents(dossier: str = "") -> list:
    """Catalogue enrichi de l'état d'activation, pour les interfaces."""
    config = charger_config(dossier)
    return [
        {"numero": a["numero"], "nom": a["nom"], "optionnel": a["optionnel"],
         "actif": est_actif(a["numero"], config)}
        for a in CATALOGUE_AGENTS
    ]
