"""
chat_agents.py — Chat interactif avec un agent, HORS production.

Permet au producteur, depuis les interfaces (API/PWA/bureau), de POSER une
question libre à l'agent de son choix (« Directeur Créatif, propose-moi trois
ambiances pour un thriller ») et d'obtenir une réponse en langage naturel —
indépendamment d'une production complète.

C'est un pont fin entre l'API (bibliothèque standard) et les agents (qui, eux,
ont besoin de LangChain). Pour NE PAS alourdir l'API — qui doit rester
importable et testable sans les dépendances du pipeline — l'import de LangChain
n'a lieu QUE lorsqu'on instancie réellement un agent (au premier message), via
le chargement dynamique déjà utilisé par l'orchestrateur.

Le catalogue des agents (numéro → fichier/classe/rôle) vient de config_agents :
une source unique, partagée avec la gestion d'activation.
"""

import os

from config_agents import agent as _agent_catalogue
from orchestrateur import charger_module

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))


def repondre(numero: int, message: str, dossier_agents: str = "",
             modele: str = "") -> str:
    """Charge l'agent `numero`, lui transmet `message` et renvoie sa réponse.

    Lève :
      - ValueError    si le numéro d'agent est inconnu ;
      - RuntimeError  si aucun accès OpenAI n'est configuré (remonté par
                      l'agent) — l'API la traduit en 503 ;
      - toute autre   exception si l'appel au modèle échoue (traduite en 502).
    """
    entree = _agent_catalogue(numero)          # ValueError si inconnu
    message = (message or "").strip()
    if not message:
        raise ValueError("Le message ne peut pas être vide.")

    dossier = dossier_agents or AGENTS_DIR
    module = charger_module(os.path.join(dossier, entree["fichier"]))
    classe = getattr(module, entree["classe"])

    kwargs = {}
    if modele:
        kwargs["model"] = modele
    instance = classe(**kwargs)                # RuntimeError si pas d'accès OpenAI
    return instance.discuter(message, role=entree["role"])
