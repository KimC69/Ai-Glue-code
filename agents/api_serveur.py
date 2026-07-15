"""
api_serveur.py — API HTTP du Studio IA (étape 7 de la feuille de route).

Met enfin EN SERVICE l'authentification de l'étape 6 : ce serveur expose le
studio par-dessus HTTP pour que les futures interfaces (web à l'étape 8, Android
à l'étape 9, application de bureau à l'étape 10) puissent, à distance et de
façon contrôlée :

  - SE CONNECTER (nom + mot de passe → jeton de session signé) ;
  - CONSULTER l'historique des productions et le détail de chacune ;
  - LANCER une nouvelle production ;
  - SE DÉCONNECTER (révoquer son jeton).

Chaque route (hormis /sante et /connexion) exige un jeton valide présenté dans
l'en-tête « Authorization: Bearer <jeton> » ET la permission correspondant au
rôle de l'utilisateur (voir securite.PERMISSIONS). Le serveur RÉUTILISE les
briques déjà écrites : securite.py pour l'authentification, journal_production.py
pour la lecture de l'historique, et main.py (lancé en sous-processus) pour la
production elle-même.

Principe « échoue fermé », hérité de securite.py : au moindre doute sur un jeton,
on REFUSE. Surtout, aucune erreur de sécurité ne doit jamais provoquer une 500 —
un jeton absent ou invalide donne 401, une permission manquante donne 403. C'est
la règle centrale de cette étape : toute ErreurSecurite est convertie en réponse
HTTP propre, jamais en plantage du serveur.

Le LANCEMENT est asynchrone : produire un film prend plusieurs minutes, alors
l'API ne bloque pas. Elle génère l'identifiant de la production, démarre le
pipeline EN ARRIÈRE-PLAN (sous-processus `python main.py --idea ... --production-id
...`) et renvoie l'identifiant immédiatement (202 Accepted). Le client suit
ensuite l'avancement en interrogeant GET /productions/<id>, qui lit la base du
journal alimentée par le sous-processus.

Bibliothèque standard uniquement (http.server, subprocess, json, hmac…) : aucune
dépendance, dans la même philosophie que le worker distant et le journal. Note :
le sous-processus de production, lui, a besoin des dépendances du pipeline
(langchain…) installées sur la machine ; l'API et l'authentification, elles, sont
testables sans aucune clé.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from securite import Securite, ErreurSecurite, DUREE_JETON_DEFAUT
from journal_production import JournalProduction
from controle_production import ecrire_commande
import config_agents
import chat_agents
import memoire
import projets

VERSION = "1.0"
DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
MAIN_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
DOSSIER_PWA_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pwa")

# Interface mobile (PWA, étape 9) servie EN STATIQUE par l'API. Liste BLANCHE
# explicite « route → (fichier relatif, type MIME) » : on ne construit jamais un
# chemin de fichier à partir de l'URL, donc aucune traversée de répertoire
# (« /../secret ») n'est possible. Ces ressources sont PUBLIQUES (la page elle-
# même) ; les appels API qu'elle déclenche restent protégés par le jeton.
FICHIERS_PWA = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest",
                              "application/manifest+json; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/icons/icon-192.png": ("icons/icon-192.png", "image/png"),
    "/icons/icon-512.png": ("icons/icon-512.png", "image/png"),
}

# Un corps de requête JSON (connexion, lancement) est minuscule : on plafonne
# pour ne pas lire un flux arbitraire en mémoire.
TAILLE_MAX_CORPS = 64 * 1024

# Format d'un identifiant de production (voir main.py / journal_production.py).
_ID_PRODUCTION = re.compile(r"^[0-9a-f]{12}$")
ROUTE_PRODUCTION = re.compile(r"^/productions/([0-9a-f]{12})$")
# Pilotage à distance d'une production : pause / reprise / arrêt.
ROUTE_CONTROLE = re.compile(
    r"^/productions/([0-9a-f]{12})/(pause|reprendre|arreter)$")
# Activation/désactivation d'un agent par son numéro.
ROUTE_AGENT = re.compile(r"^/agents/([0-9]+)$")


@dataclass
class ConfigAPI:
    """Paramètres d'exécution de l'API. Regroupés pour être injectés facilement
    dans le handler (comme ConfigWorker côté worker) et testés isolément."""
    hote: str = "127.0.0.1"
    port: int = 8000
    dossier: str = DOSSIER_DEFAUT          # dossier output/ (bases + logs)
    python: str = ""                       # interpréteur pour le sous-processus
    main_script: str = MAIN_DEFAUT         # chemin de main.py
    dossier_pwa: str = DOSSIER_PWA_DEFAUT  # dossier de l'app mobile (statique)
    duree_jeton_s: int = DUREE_JETON_DEFAUT

    def __post_init__(self):
        # sys.executable garantit le MÊME interpréteur (et donc le même
        # environnement/paquets) que celui qui fait tourner l'API.
        self.python = self.python or sys.executable


class RequeteAPI(BaseHTTPRequestHandler):
    """Routeur HTTP de l'API. Attributs injectés par creer_serveur() :
    config, securite, journal."""

    config: ConfigAPI = None
    securite: Securite = None
    journal: JournalProduction = None

    # ── Réponses ─────────────────────────────────────────────────────────────

    def _json(self, code: int, objet: dict) -> None:
        corps = json.dumps(objet, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        # HEAD n'a pas de corps ; ici on ne sert que GET/POST → écriture directe.
        self.wfile.write(corps)

    def _erreur(self, code: int, message: str) -> None:
        self._json(code, {"erreur": message})

    def log_message(self, *args):
        """Silence le journal HTTP standard (une ligne par requête sur stderr)."""

    # ── Authentification et autorisation ──────────────────────────────────────

    def _jeton_presente(self) -> str:
        """Extrait le jeton de l'en-tête « Authorization: Bearer <jeton> ».
        Retourne une chaîne vide si l'en-tête est absent ou mal formé."""
        entete = self.headers.get("Authorization", "")
        prefixe = "Bearer "
        if entete.startswith(prefixe):
            return entete[len(prefixe):].strip()
        return ""

    def _authentifier(self):
        """Vérifie qu'un jeton valide est présenté. Retourne sa charge utile, ou
        None APRÈS avoir envoyé une réponse 401 (jeton absent, invalide, expiré
        ou révoqué). Toute ErreurSecurite est absorbée ici : jamais de 500."""
        jeton = self._jeton_presente()
        if not jeton:
            self._erreur(401, "Authentification requise : en-tête "
                              "« Authorization: Bearer <jeton> » attendu.")
            return None
        try:
            return self.securite.verifier_jeton(jeton)
        except ErreurSecurite as e:
            self._erreur(401, str(e))
            return None

    def _exiger(self, permission: str):
        """Authentifie PUIS vérifie la permission. Retourne la charge du jeton,
        ou None après avoir envoyé 401 (pas connecté) ou 403 (rôle insuffisant).
        C'est le point unique qui garantit « échoue fermé, jamais 500 »."""
        charge = self._authentifier()
        if charge is None:
            return None
        role = charge.get("role", "")
        if not Securite.a_permission(role, permission):
            self._erreur(403, f"Permission refusée : le rôle {role!r} ne peut "
                              f"pas « {permission} ».")
            return None
        return charge

    # ── Lecture du corps JSON ─────────────────────────────────────────────────

    def _corps_json(self):
        """Lit et décode un corps JSON. Retourne le dict, ou None APRÈS avoir
        envoyé l'erreur adéquate (411 corps manquant, 413 trop gros, 400 JSON
        invalide ou racine non-objet)."""
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            self._erreur(400, "en-tête Content-Length invalide")
            return None
        if longueur <= 0:
            self._erreur(411, "corps de requête manquant")
            return None
        if longueur > TAILLE_MAX_CORPS:
            self._erreur(413, "corps de requête trop volumineux")
            return None
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._erreur(400, "JSON invalide")
            return None
        if not isinstance(corps, dict):
            self._erreur(400, "le corps JSON doit être un objet")
            return None
        return corps

    # ── Fichiers statiques de l'app mobile (PWA) ─────────────────────────────────

    def _fichier(self, chemin_relatif: str, content_type: str) -> None:
        """Sert un fichier de la PWA. `chemin_relatif` provient de la liste
        blanche FICHIERS_PWA (jamais de l'URL brute) : pas de traversée possible."""
        chemin = os.path.join(self.config.dossier_pwa, chemin_relatif)
        try:
            with open(chemin, "rb") as f:
                corps = f.read()
        except OSError:
            # PWA non installée à côté de l'API (ou icône manquante) : 404 propre.
            return self._erreur(404, "ressource introuvable")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(corps)))
        # Le service worker ne doit PAS être mis en cache par le navigateur,
        # sinon une mise à jour de l'app ne serait jamais récupérée.
        if chemin_relatif == "sw.js":
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(corps)

    def _servir_statique(self) -> bool:
        """Sert une ressource de la PWA si l'URL en désigne une. Retourne True si
        la requête a été traitée (fichier servi ou 404), False sinon — auquel cas
        le routeur continue vers ses autres routes."""
        chemin = self.path.split("?", 1)[0]
        entree = FICHIERS_PWA.get(chemin)
        if entree is None:
            return False
        self._fichier(*entree)
        return True

    # ── Routage (avec filet de sécurité anti-500) ───────────────────────────────

    def _router(self, handler) -> None:
        """Exécute un handler de route en garantissant qu'AUCUNE exception
        inattendue ne remonte en 500 non contrôlée. Le principe « échoue fermé »
        de l'auth n'a de valeur que si le serveur ne plante pas sur un cas de
        bord (en-tête malformé, client déconnecté…) : on répond proprement."""
        try:
            handler()
        except Exception:
            # La réponse a pu être partiellement envoyée (ex. coupure client) —
            # une seconde tentative d'écriture est alors vaine : on l'absorbe.
            try:
                self._erreur(500, "erreur interne du serveur")
            except Exception:
                pass

    def do_GET(self):
        self._router(self._traiter_get)

    def do_POST(self):
        self._router(self._traiter_post)

    # ── GET ────────────────────────────────────────────────────────────────────

    def _traiter_get(self):
        # /sante : sonde publique (aucun jeton), pour vérifier que l'API répond.
        if self.path == "/sante":
            return self._json(200, {"ok": True, "version": VERSION,
                                    "service": "studio-ia-api"})

        # /productions : historique (permission consulter).
        if self.path == "/productions":
            if self._exiger("consulter") is None:
                return
            return self._json(200, {
                "productions": self.journal.lister_productions()})

        # /productions/<id> : fiche détaillée (permission consulter).
        m = ROUTE_PRODUCTION.match(self.path)
        if m:
            if self._exiger("consulter") is None:
                return
            details = self.journal.details_production(m.group(1))
            if not details:
                return self._erreur(404, "production inconnue")
            return self._json(200, details)

        # /agents : liste des agents et de leur état d'activation (consulter).
        if self.path == "/agents":
            if self._exiger("consulter") is None:
                return
            return self._json(200, {
                "agents": config_agents.liste_agents(self.config.dossier)})

        # /objectifs : note d'objectifs persistants du producteur (consulter).
        if self.path == "/objectifs":
            if self._exiger("consulter") is None:
                return
            return self._json(200, memoire.lire_objectifs(self.config.dossier))

        # /memoire : objectifs + résumé de l'état de travail (consulter).
        if self.path == "/memoire":
            if self._exiger("consulter") is None:
                return
            return self._json(200, {
                "objectifs": memoire.lire_objectifs(self.config.dossier),
                "etat": memoire.resume_world_state(self.config.dossier)})

        # /projets : liste des projets (films/séries) avec leur état (consulter).
        if self.path == "/projets":
            if self._exiger("consulter") is None:
                return
            return self._json(200, {
                "projets": projets.lister_projets(self.config.dossier)})

        # Interface mobile (PWA) : fichiers statiques publics (/, /app.js, …).
        if self._servir_statique():
            return

        return self._erreur(404, "route inconnue")

    # ── POST ────────────────────────────────────────────────────────────────────

    def _traiter_post(self):
        if self.path == "/connexion":
            return self._connexion()
        if self.path == "/deconnexion":
            return self._deconnexion()
        if self.path == "/productions":
            return self._lancer_production()

        # Pilotage à distance : /productions/<id>/(pause|reprendre|arreter).
        m = ROUTE_CONTROLE.match(self.path)
        if m:
            return self._piloter_production(m.group(1), m.group(2))

        # Activation/désactivation d'un agent : /agents/<numero>.
        m = ROUTE_AGENT.match(self.path)
        if m:
            return self._basculer_agent(int(m.group(1)))

        if self.path == "/objectifs":
            return self._definir_objectifs()
        if self.path == "/memoire/reset":
            return self._reinitialiser_memoire()
        if self.path == "/chat":
            return self._chat()
        return self._erreur(404, "route inconnue")

    # ── Handlers POST ─────────────────────────────────────────────────────────

    def _connexion(self):
        """POST /connexion {nom, mot_de_passe} → {jeton, role, expire_dans_s}.
        Route PUBLIQUE (pas encore de jeton). Identifiants faux → 401 avec un
        message unique (on ne révèle pas si le nom ou le mot de passe est faux)."""
        corps = self._corps_json()
        if corps is None:
            return
        nom = str(corps.get("nom", ""))
        mot_de_passe = str(corps.get("mot_de_passe", ""))
        try:
            compte = self.securite.verifier_identifiants(nom, mot_de_passe)
            if compte is None:
                return self._erreur(401, "Nom d'utilisateur ou mot de passe "
                                         "incorrect.")
            jeton = self.securite.emettre_jeton(
                compte["nom"], compte["role"], self.config.duree_jeton_s)
        except ErreurSecurite as e:
            # p. ex. clé de signature absente : refus propre, pas de 500.
            return self._erreur(401, str(e))
        return self._json(200, {"jeton": jeton, "role": compte["role"],
                                "expire_dans_s": self.config.duree_jeton_s})

    def _deconnexion(self):
        """POST /deconnexion → révoque le jeton présenté. Idempotent : révoquer
        deux fois le même jeton reste un succès (INSERT OR IGNORE côté base)."""
        charge = self._authentifier()
        if charge is None:
            return
        try:
            self.securite.revoquer_jeton(self._jeton_presente())
        except ErreurSecurite as e:
            return self._erreur(401, str(e))
        return self._json(200, {"ok": True, "message": "Jeton révoqué."})

    def _lancer_production(self):
        """POST /productions {idee, modele?} → 202 {id, statut}. Génère
        l'identifiant, démarre main.py EN ARRIÈRE-PLAN et renvoie tout de suite ;
        le client suit ensuite via GET /productions/<id> (permission
        lancer_production)."""
        if self._exiger("lancer_production") is None:
            return
        corps = self._corps_json()
        if corps is None:
            return
        idee = str(corps.get("idee", "")).strip()
        if not idee:
            return self._erreur(400, "le champ « idee » est obligatoire")
        modele = str(corps.get("modele", "")).strip()
        projet = str(corps.get("projet", "")).strip()
        inspiration = str(corps.get("inspiration", "")).strip()

        # Écrire une suite : le projet source doit exister, sinon on refuse tout
        # de suite (404) plutôt que de lancer une production qui échouera seule
        # dans son sous-processus.
        if inspiration:
            try:
                slug_source = projets.slugifier(inspiration)
            except ValueError:
                return self._erreur(400, "le champ « inspiration » est invalide")
            if not projets.projet_existe(slug_source, self.config.dossier):
                return self._erreur(
                    404, f"projet source « {inspiration} » introuvable : "
                         "impossible d'en écrire une suite.")

        production_id = _nouvel_id()
        try:
            demarrer_production_en_fond(self.config, production_id, idee, modele,
                                        projet, inspiration)
        except OSError as e:
            # Échec du lancement du sous-processus (interpréteur/main.py
            # introuvable) : on le signale clairement plutôt que par une 500.
            return self._erreur(500, f"Lancement impossible : {e}")
        return self._json(202, {
            "id": production_id, "statut": "en_cours",
            "suivi": f"/productions/{production_id}"})

    # ── Pilotage à distance d'une production ─────────────────────────────────

    def _piloter_production(self, production_id: str, commande: str):
        """POST /productions/<id>/(pause|reprendre|arreter) → transmet une
        commande de pilotage (permission piloter_production). L'effet est pris en
        compte par le sous-processus au début de l'étape suivante — la réponse le
        dit clairement plutôt que de laisser croire à un arrêt instantané."""
        if self._exiger("piloter_production") is None:
            return
        details = self.journal.details_production(production_id)
        if not details:
            return self._erreur(404, "production inconnue")
        statut = details.get("production", {}).get("statut", "")
        if statut not in ("en_cours", "en_pause"):
            return self._erreur(409, f"production « {statut} » : le pilotage "
                                     "n'est possible que sur une production en "
                                     "cours ou en pause.")
        try:
            ecrire_commande(production_id, commande, dossier=self.config.dossier)
        except (OSError, ValueError) as e:
            return self._erreur(500, f"commande non transmise : {e}")
        return self._json(200, {
            "ok": True, "id": production_id, "commande": commande,
            "message": f"Commande « {commande} » transmise — effet à la fin de "
                       "l'étape en cours."})

    # ── Activation / désactivation des agents ────────────────────────────────

    def _basculer_agent(self, numero: int):
        """POST /agents/<numero> {actif: bool} → active ou désactive un agent
        optionnel (permission gerer_utilisateurs). Refuse (409) de désactiver un
        agent de la chaîne créative indispensable."""
        if self._exiger("gerer_utilisateurs") is None:
            return
        try:
            config_agents.agent(numero)
        except ValueError:
            return self._erreur(404, "agent inconnu")
        corps = self._corps_json()
        if corps is None:
            return
        actif = corps.get("actif")
        if not isinstance(actif, bool):
            return self._erreur(400, "le champ « actif » (booléen) est obligatoire")
        try:
            config_agents.definir_agent(numero, actif, dossier=self.config.dossier)
        except ValueError as e:
            return self._erreur(409, str(e))
        except OSError as e:
            return self._erreur(500, f"configuration non enregistrée : {e}")
        return self._json(200, {
            "agents": config_agents.liste_agents(self.config.dossier)})

    # ── Mémoire et objectifs ─────────────────────────────────────────────────

    def _definir_objectifs(self):
        """POST /objectifs {texte} → enregistre la note d'objectifs persistants,
        injectée au lancement des futures productions (permission
        gerer_utilisateurs : seul l'administrateur fixe la ligne éditoriale)."""
        charge = self._exiger("gerer_utilisateurs")
        if charge is None:
            return
        corps = self._corps_json()
        if corps is None:
            return
        texte = str(corps.get("texte", ""))
        try:
            objet = memoire.ecrire_objectifs(
                texte, par=charge.get("sub", ""), dossier=self.config.dossier)
        except OSError as e:
            return self._erreur(500, f"objectifs non enregistrés : {e}")
        return self._json(200, objet)

    def _reinitialiser_memoire(self):
        """POST /memoire/reset → efface l'état de travail (world_state)
        (permission gerer_utilisateurs). Refusé si une production est active,
        pour ne pas effacer la mémoire vive sous les pieds d'un sous-processus."""
        if self._exiger("gerer_utilisateurs") is None:
            return
        try:
            actives = self.journal.compter_productions_actives()
        except RuntimeError:
            # Impossible de vérifier → on « échoue fermé » : on refuse plutôt
            # que de risquer d'effacer la mémoire pendant une production active.
            return self._erreur(503, "état des productions indisponible : "
                                     "réinitialisation de la mémoire refusée par "
                                     "précaution.")
        if actives > 0:
            return self._erreur(409, "une production est en cours ou en pause : "
                                     "réinitialisation de la mémoire impossible.")
        efface = memoire.reinitialiser_world_state(self.config.dossier)
        return self._json(200, {
            "ok": True, "efface": efface,
            "message": "Mémoire de travail réinitialisée." if efface
                       else "Aucune mémoire de travail à réinitialiser."})

    # ── Chat interactif avec un agent (hors production) ──────────────────────

    def _chat(self):
        """POST /chat {agent, message, modele?} → {agent, reponse}. Discussion
        libre avec un agent (permission piloter_production). L'appel au modèle
        peut échouer : on le traduit en erreur propre (503 sans accès OpenAI,
        502 si l'agent ne répond pas), jamais en 500."""
        if self._exiger("piloter_production") is None:
            return
        corps = self._corps_json()
        if corps is None:
            return
        try:
            numero = int(corps.get("agent"))
        except (TypeError, ValueError):
            return self._erreur(400, "le champ « agent » (numéro) est obligatoire")
        message = str(corps.get("message", "")).strip()
        if not message:
            return self._erreur(400, "le champ « message » est obligatoire")
        modele = str(corps.get("modele", "")).strip()
        dossier_agents = os.path.dirname(self.config.main_script)
        try:
            reponse = chat_agents.repondre(
                numero, message, dossier_agents=dossier_agents, modele=modele)
        except ValueError as e:
            return self._erreur(404, str(e))
        except RuntimeError as e:
            return self._erreur(503, str(e))
        except Exception as e:            # échec de l'appel LLM : 502, pas 500
            return self._erreur(502, f"l'agent n'a pas pu répondre : {e}")
        return self._json(200, {"agent": numero, "reponse": reponse})


# ── Lancement du pipeline en arrière-plan ─────────────────────────────────────

def _nouvel_id() -> str:
    """Identifiant de production : 12 caractères hexadécimaux, comme main.py."""
    import uuid
    return uuid.uuid4().hex[:12]


def commande_lancement(config: ConfigAPI, production_id: str, idee: str,
                       modele: str = "", projet: str = "",
                       inspiration: str = "") -> list:
    """Construit la ligne de commande du sous-processus de production. Isolée
    (et sans effet de bord) pour être testable sans rien exécuter.

    `projet` range le film dans son propre dossier ; `inspiration` désigne un
    projet existant dont l'univers sert de référence pour écrire une suite."""
    commande = [config.python, config.main_script,
                "--idea", idee, "--production-id", production_id]
    if modele:
        commande += ["--model", modele]
    if projet:
        commande += ["--projet", projet]
    if inspiration:
        commande += ["--inspiration", inspiration]
    return commande


def demarrer_production_en_fond(config: ConfigAPI, production_id: str,
                                idee: str, modele: str = "", projet: str = "",
                                inspiration: str = "") -> "subprocess.Popen":
    """Démarre le pipeline dans un sous-processus détaché et rend la main
    immédiatement (on N'ATTEND PAS la fin — une production dure plusieurs
    minutes). La sortie du sous-processus est redirigée vers un fichier de log
    par production (utile pour diagnostiquer un lancement qui échoue, p. ex.
    dépendances du pipeline absentes), et son entrée standard est coupée pour
    qu'il ne réclame jamais de saisie au clavier."""
    dossier_logs = os.path.join(config.dossier, "lancements_api")
    os.makedirs(dossier_logs, exist_ok=True)
    chemin_log = os.path.join(dossier_logs, f"{production_id}.log")
    sortie = open(chemin_log, "w", encoding="utf-8")
    commande = commande_lancement(config, production_id, idee, modele,
                                  projet, inspiration)
    try:
        return subprocess.Popen(
            commande, stdin=subprocess.DEVNULL, stdout=sortie,
            stderr=subprocess.STDOUT, cwd=os.path.dirname(config.main_script),
            start_new_session=True)
    finally:
        # Le sous-processus a hérité du descripteur ; l'API n'en a plus besoin.
        sortie.close()


# ── Construction et démarrage du serveur ──────────────────────────────────────

def creer_serveur(config: ConfigAPI, securite: Securite,
                  journal: JournalProduction) -> ThreadingHTTPServer:
    """Construit le serveur HTTP (sans le démarrer). Séparé de principal() pour
    être testable en local avec un port éphémère (port=0)."""
    handler = type("RequeteAPIConfigure", (RequeteAPI,), {
        "config": config, "securite": securite, "journal": journal,
    })
    return ThreadingHTTPServer((config.hote, config.port), handler)


def principal(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="API HTTP du Studio IA — connexion, historique et lancement "
                    "de productions, protégés par les comptes de l'étape 6.")
    parser.add_argument("--hote", default="127.0.0.1",
                        help="Adresse d'écoute (0.0.0.0 pour exposer au réseau)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute")
    parser.add_argument("--duree-jeton", type=int, default=DUREE_JETON_DEFAUT,
                        help=f"Durée de validité d'un jeton en secondes "
                             f"(défaut : {DUREE_JETON_DEFAUT})")
    args = parser.parse_args(argv)

    config = ConfigAPI(hote=args.hote, port=args.port,
                       duree_jeton_s=args.duree_jeton)

    # Sous-système de sécurité. Sans clé de signature (SESSION_SECRET), aucune
    # connexion n'est possible : on refuse de démarrer plutôt que d'exposer une
    # API d'authentification qui ne peut authentifier personne (échoue fermé).
    try:
        securite = Securite()
    except ErreurSecurite as e:
        print(f"[Erreur] : {e}")
        return 1
    if not os.environ.get("SESSION_SECRET", "").strip():
        print("[Erreur] : le secret SESSION_SECRET n'est pas défini — les jetons "
              "ne peuvent être ni émis ni vérifiés. Définissez-le puis relancez.")
        securite.fermer()
        return 1

    journal = JournalProduction()          # instance de lecture (historique)

    try:
        serveur = creer_serveur(config, securite, journal)
    except OSError as e:
        print(f"[Erreur] : impossible d'écouter sur {args.hote}:{args.port} ({e}).")
        securite.fermer()
        journal.fermer()
        return 1

    port_effectif = serveur.server_address[1]
    nb_comptes = securite.compte_utilisateurs()

    print("─" * 62)
    print("  🎬  API DU STUDIO IA")
    print("─" * 62)
    print(f"  Écoute      : http://{args.hote}:{port_effectif}")
    print(f"  App mobile  : http://{args.hote}:{port_effectif}/  (PWA — étape 9)")
    print(f"  Comptes     : {nb_comptes}")
    print(f"  Jeton valide: {config.duree_jeton_s}s")
    print("  Routes      : GET /sante · POST /connexion · POST /deconnexion")
    print("                GET /productions · GET /productions/<id>")
    print("                POST /productions")
    print("                POST /productions/<id>/(pause|reprendre|arreter)")
    print("                GET /agents · POST /agents/<numero>")
    print("                GET /objectifs · POST /objectifs")
    print("                GET /memoire · POST /memoire/reset")
    print("                POST /chat")
    if nb_comptes == 0:
        print("\n  ⚠️  Aucun compte : créez un administrateur avant de vous connecter :")
        print("      python main.py --creer-utilisateur admin --role admin")
    print("\n  Exemple de connexion :")
    print(f"    curl -X POST http://{args.hote}:{port_effectif}/connexion \\")
    print("         -d '{\"nom\":\"admin\",\"mot_de_passe\":\"...\"}'")
    print("  (Ctrl+C pour arrêter l'API)")
    print("─" * 62)

    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\n[api] Arrêt demandé — au revoir.")
    finally:
        serveur.server_close()
        securite.fermer()
        journal.fermer()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
