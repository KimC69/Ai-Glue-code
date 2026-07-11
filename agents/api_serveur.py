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

VERSION = "1.0"
DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
MAIN_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

# Un corps de requête JSON (connexion, lancement) est minuscule : on plafonne
# pour ne pas lire un flux arbitraire en mémoire.
TAILLE_MAX_CORPS = 64 * 1024

# Format d'un identifiant de production (voir main.py / journal_production.py).
_ID_PRODUCTION = re.compile(r"^[0-9a-f]{12}$")
ROUTE_PRODUCTION = re.compile(r"^/productions/([0-9a-f]{12})$")


@dataclass
class ConfigAPI:
    """Paramètres d'exécution de l'API. Regroupés pour être injectés facilement
    dans le handler (comme ConfigWorker côté worker) et testés isolément."""
    hote: str = "127.0.0.1"
    port: int = 8000
    dossier: str = DOSSIER_DEFAUT          # dossier output/ (bases + logs)
    python: str = ""                       # interpréteur pour le sous-processus
    main_script: str = MAIN_DEFAUT         # chemin de main.py
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

        return self._erreur(404, "route inconnue")

    # ── POST ────────────────────────────────────────────────────────────────────

    def _traiter_post(self):
        if self.path == "/connexion":
            return self._connexion()
        if self.path == "/deconnexion":
            return self._deconnexion()
        if self.path == "/productions":
            return self._lancer_production()
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

        production_id = _nouvel_id()
        try:
            demarrer_production_en_fond(self.config, production_id, idee, modele)
        except OSError as e:
            # Échec du lancement du sous-processus (interpréteur/main.py
            # introuvable) : on le signale clairement plutôt que par une 500.
            return self._erreur(500, f"Lancement impossible : {e}")
        return self._json(202, {
            "id": production_id, "statut": "en_cours",
            "suivi": f"/productions/{production_id}"})


# ── Lancement du pipeline en arrière-plan ─────────────────────────────────────

def _nouvel_id() -> str:
    """Identifiant de production : 12 caractères hexadécimaux, comme main.py."""
    import uuid
    return uuid.uuid4().hex[:12]


def commande_lancement(config: ConfigAPI, production_id: str, idee: str,
                       modele: str = "") -> list:
    """Construit la ligne de commande du sous-processus de production. Isolée
    (et sans effet de bord) pour être testable sans rien exécuter."""
    commande = [config.python, config.main_script,
                "--idea", idee, "--production-id", production_id]
    if modele:
        commande += ["--model", modele]
    return commande


def demarrer_production_en_fond(config: ConfigAPI, production_id: str,
                                idee: str, modele: str = "") -> "subprocess.Popen":
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
    commande = commande_lancement(config, production_id, idee, modele)
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
    print(f"  Comptes     : {nb_comptes}")
    print(f"  Jeton valide: {config.duree_jeton_s}s")
    print("  Routes      : GET /sante · POST /connexion · POST /deconnexion")
    print("                GET /productions · GET /productions/<id>")
    print("                POST /productions")
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
