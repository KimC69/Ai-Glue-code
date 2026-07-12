"""
worker_distant.py — Serveur d'exécution distant du Studio IA.

À lancer sur la machine de rendu (celle où Blender, Unreal Engine et/ou
FFmpeg sont installés). Le studio (main.py --worker URL) lui envoie les
scripts générés par les agents ; le worker les exécute localement puis
laisse le studio rapatrier journaux et fichiers produits.

Aucune dépendance externe : bibliothèque standard uniquement. Ce fichier
est autonome — copiez-le seul sur la machine de rendu si besoin.

Usage sur la machine de rendu :
    python3 worker_distant.py                            # 127.0.0.1:8765, jeton généré
    python3 worker_distant.py --hote 0.0.0.0 --port 8765 # exposé au réseau local
    python3 worker_distant.py --blender /opt/blender/blender
    WORKER_JETON=mon-jeton python3 worker_distant.py

Sécurité :
    - toutes les requêtes exigent l'en-tête X-Jeton (affiché au démarrage) ;
    - seuls les lanceurs du studio sont invocables : blender / unreal / ffmpeg ;
    - chaque travail s'exécute dans un dossier isolé (sauf chaînage explicite) ;
    - par défaut le serveur n'écoute qu'en local (127.0.0.1) — utilisez
      --hote 0.0.0.0 pour l'exposer, idéalement derrière un pare-feu ou un
      tunnel SSH ;
    - IMPORTANT : la fonction même du worker est d'exécuter les scripts
      qu'on lui envoie. Posséder le jeton équivaut donc à pouvoir exécuter
      du code sur cette machine — traitez-le comme un mot de passe SSH :
      secret, jamais commité, régénéré au moindre doute.

API (JSON, en-tête X-Jeton obligatoire) :
    GET  /sante                        → état + outils disponibles
    POST /travaux                      → {outil, nom_script, script[, poursuivre]}
    GET  /travaux/<id>                 → statut du travail
    GET  /travaux/<id>/journal         → journal d'exécution (texte)
    GET  /travaux/<id>/fichiers        → liste des fichiers produits
    GET  /travaux/<id>/fichiers/<nom>  → téléchargement d'un fichier produit
"""

import argparse
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

VERSION = "1.0"
OUTILS_STUDIO = ("blender", "unreal", "ffmpeg", "csound")
TAILLE_MAX_CORPS = 5 * 1024 * 1024  # 5 Mo — largement au-delà d'un script généré


@dataclass
class ConfigWorker:
    """Configuration du worker (voir principal() pour les options CLI)."""
    hote: str = "127.0.0.1"
    port: int = 8765
    jeton: str = ""
    dossier: str = "travaux_worker"
    blender: str = "blender"
    ffmpeg: str = "ffmpeg"
    csound: str = "csound"
    bash: str = "bash"
    delai_max: int = 7200          # durée maximale d'un travail (secondes)


class Travail:
    """Un script reçu du studio, exécuté dans son dossier de travail."""

    def __init__(self, identifiant: str, outil: str, nom_script: str, dossier: str):
        self.id = identifiant
        self.outil = outil
        self.nom_script = nom_script          # nom du fichier script dans le dossier
        self.dossier = dossier
        self.etat = "en_attente"              # en_attente | en_cours | termine | echec
        self.code_retour = None
        self.duree = None

    @property
    def journal_path(self) -> str:
        return os.path.join(self.dossier, f"journal_{self.id}.log")

    def statut(self) -> dict:
        return {
            "id": self.id, "outil": self.outil, "etat": self.etat,
            "code_retour": self.code_retour, "duree": self.duree,
        }


def outils_disponibles(config: ConfigWorker) -> dict:
    """Détecte les outils réellement utilisables sur cette machine."""
    bash_ok = shutil.which(config.bash) is not None
    return {
        "blender": shutil.which(config.blender) is not None,
        # Le script Unreal généré par l'Agent 05 est un .sh autonome : il
        # embarque lui-même ses appels à Unreal Engine.
        "unreal": bash_ok,
        "ffmpeg": bash_ok and shutil.which(config.ffmpeg) is not None,
        # Csound rend le fichier .csd directement en audio, sans interface.
        "csound": shutil.which(config.csound) is not None,
    }


def nom_script_securise(outil: str, nom_brut: str, identifiant: str) -> str:
    """Nom de fichier sûr pour un script reçu (anti-traversée de répertoire).

    Ne garde que le basename, remplace tout caractère non
    alphanumérique/._- , force une extension selon l'outil, puis préfixe par
    l'identifiant du travail. Source unique partagée par le worker distant et
    l'exécuteur local pour garantir le même comportement de sécurité.
    """
    nom = re.sub(r"[^A-Za-z0-9._-]", "_",
                 os.path.basename(str(nom_brut))).strip("._")
    if not nom:
        nom = "script"
    if "." not in nom:
        nom += {"blender": ".py", "csound": ".csd"}.get(outil, ".sh")
    return f"script_{identifiant}_{nom}"


def construire_commande(config: ConfigWorker, travail: Travail) -> list:
    """Commande d'exécution du script selon l'outil (liste blanche stricte)."""
    script = os.path.join(travail.dossier, travail.nom_script)
    if travail.outil == "blender":
        return [config.blender, "--background", "--python", script]
    if travail.outil == "csound":
        # Rend la partition Csound en fichier audio, dans le dossier du travail.
        return [config.csound, script, "-o", "bande_son.wav"]
    # unreal / ffmpeg : scripts shell autonomes générés par les agents
    return [config.bash, script]


class Executeur(threading.Thread):
    """
    Consomme la file des travaux : UN SEUL travail à la fois (Blender et
    Unreal saturent facilement une machine de rendu).
    """

    def __init__(self, config: ConfigWorker, file_travaux: "queue.Queue"):
        super().__init__(daemon=True)
        self.config = config
        self.file_travaux = file_travaux

    def run(self):
        while True:
            travail = self.file_travaux.get()
            self._executer(travail)

    def _executer(self, travail: Travail) -> None:
        travail.etat = "en_cours"
        debut = time.time()
        commande = construire_commande(self.config, travail)
        print(f"[worker] ▶ Travail {travail.id} ({travail.outil}) démarré")
        try:
            with open(travail.journal_path, "a", encoding="utf-8") as journal:
                journal.write("$ " + " ".join(commande) + "\n")
                journal.flush()
                try:
                    resultat = subprocess.run(
                        commande, cwd=travail.dossier, env=os.environ.copy(),
                        stdout=journal, stderr=subprocess.STDOUT,
                        timeout=self.config.delai_max)
                    travail.code_retour = resultat.returncode
                    travail.etat = "termine" if resultat.returncode == 0 else "echec"
                except subprocess.TimeoutExpired:
                    journal.write(f"\n[worker] DÉLAI MAXIMAL DÉPASSÉ "
                                  f"({self.config.delai_max}s) — processus interrompu.\n")
                    travail.code_retour = -1
                    travail.etat = "echec"
        except Exception as e:  # binaire absent, droits insuffisants...
            travail.code_retour = -1
            travail.etat = "echec"
            try:
                with open(travail.journal_path, "a", encoding="utf-8") as journal:
                    journal.write(f"\n[worker] Erreur d'exécution : {e}\n")
            except OSError:
                pass
        travail.duree = round(time.time() - debut, 1)
        symbole = "✅" if travail.etat == "termine" else "⚠️ "
        print(f"[worker] {symbole} Travail {travail.id} ({travail.outil}) : "
              f"{travail.etat} (code {travail.code_retour}, {travail.duree}s)")


class RequeteWorker(BaseHTTPRequestHandler):
    """Routeur HTTP. Attributs injectés par creer_worker() : config,
    registre, verrou, file_travaux."""

    config: ConfigWorker = None
    registre: dict = None
    verrou: "threading.Lock" = None
    file_travaux: "queue.Queue" = None

    ROUTE_TRAVAIL = re.compile(r"^/travaux/([0-9a-f]{12})$")
    ROUTE_JOURNAL = re.compile(r"^/travaux/([0-9a-f]{12})/journal$")
    ROUTE_FICHIERS = re.compile(r"^/travaux/([0-9a-f]{12})/fichiers$")
    ROUTE_FICHIER = re.compile(r"^/travaux/([0-9a-f]{12})/fichiers/(.+)$")

    # ── Réponses ─────────────────────────────────────────────────────────────

    def _json(self, code: int, objet: dict) -> None:
        corps = json.dumps(objet, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _erreur(self, code: int, message: str) -> None:
        self._json(code, {"erreur": message})

    def _octets(self, corps: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _fichier(self, chemin: str, content_type: str) -> None:
        """Envoie un fichier en flux, par morceaux de 64 Kio — jamais chargé
        entièrement en mémoire : une vidéo rendue peut peser plusieurs Go.
        La taille annoncée est figée à l'ouverture ; si le fichier grossit
        pendant l'envoi (journal d'un travail en cours), l'envoi s'arrête
        proprement à la taille annoncée."""
        try:
            f = open(chemin, "rb")
        except OSError:
            return self._erreur(404, "fichier introuvable")
        with f:
            taille = os.fstat(f.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(taille))
            self.end_headers()
            restant = taille
            while restant > 0:
                morceau = f.read(min(64 * 1024, restant))
                if not morceau:
                    break  # fichier raccourci entre-temps — connexion coupée
                self.wfile.write(morceau)
                restant -= len(morceau)

    def _autorise(self) -> bool:
        jeton = self.headers.get("X-Jeton", "")
        return hmac.compare_digest(jeton.encode(), self.config.jeton.encode())

    def _travail(self, identifiant: str):
        with self.verrou:
            return self.registre.get(identifiant)

    def log_message(self, *args):
        """Silence le journal HTTP standard — l'Executeur journalise l'essentiel."""

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        if not self._autorise():
            return self._erreur(401, "jeton absent ou invalide (en-tête X-Jeton)")

        if self.path == "/sante":
            return self._json(200, {
                "ok": True, "version": VERSION,
                "outils": outils_disponibles(self.config),
                "en_attente": self.file_travaux.qsize(),
            })

        m = self.ROUTE_TRAVAIL.match(self.path)
        if m:
            travail = self._travail(m.group(1))
            if travail is None:
                return self._erreur(404, "travail inconnu")
            return self._json(200, travail.statut())

        m = self.ROUTE_JOURNAL.match(self.path)
        if m:
            travail = self._travail(m.group(1))
            if travail is None:
                return self._erreur(404, "travail inconnu")
            if not os.path.isfile(travail.journal_path):
                # Travail encore en file d'attente : journal pas encore créé
                return self._octets(b"", "text/plain; charset=utf-8")
            return self._fichier(travail.journal_path, "text/plain; charset=utf-8")

        m = self.ROUTE_FICHIERS.match(self.path)
        if m:
            travail = self._travail(m.group(1))
            if travail is None:
                return self._erreur(404, "travail inconnu")
            fichiers = []
            for racine, _, noms in os.walk(travail.dossier):
                for nom in noms:
                    # Les scripts reçus et les journaux ne sont pas des « produits »
                    if nom.startswith(("script_", "journal_")):
                        continue
                    complet = os.path.join(racine, nom)
                    fichiers.append({
                        "nom": os.path.relpath(complet, travail.dossier),
                        "taille": os.path.getsize(complet),
                    })
            fichiers.sort(key=lambda f: f["nom"])
            return self._json(200, {"fichiers": fichiers})

        m = self.ROUTE_FICHIER.match(self.path)
        if m:
            travail = self._travail(m.group(1))
            if travail is None:
                return self._erreur(404, "travail inconnu")
            relatif = unquote(m.group(2))
            racine = os.path.realpath(travail.dossier)
            complet = os.path.realpath(os.path.join(racine, relatif))
            # Anti-traversée de chemin : le fichier doit rester dans le dossier
            if not complet.startswith(racine + os.sep) or not os.path.isfile(complet):
                return self._erreur(404, "fichier introuvable")
            return self._fichier(complet, "application/octet-stream")

        return self._erreur(404, "route inconnue")

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._autorise():
            return self._erreur(401, "jeton absent ou invalide (en-tête X-Jeton)")
        if self.path != "/travaux":
            return self._erreur(404, "route inconnue")

        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur <= 0:
            return self._erreur(411, "corps de requête manquant")
        if longueur > TAILLE_MAX_CORPS:
            return self._erreur(413, "script trop volumineux")
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._erreur(400, "JSON invalide")

        outil = str(corps.get("outil", "")).strip().lower()
        script = corps.get("script", "")
        if outil not in OUTILS_STUDIO:
            return self._erreur(400, f"outil inconnu « {outil} » — outils acceptés : "
                                     + ", ".join(OUTILS_STUDIO))
        if not isinstance(script, str) or not script.strip():
            return self._erreur(400, "script vide")
        if not outils_disponibles(self.config).get(outil):
            return self._erreur(409, f"outil « {outil} » indisponible sur ce worker")

        identifiant = uuid.uuid4().hex[:12]

        # Dossier d'exécution : isolé, ou celui d'un travail précédent
        # (chaînage : l'export FFmpeg retrouve la vidéo rendue par Blender).
        poursuivre = str(corps.get("poursuivre", "")).strip()
        if poursuivre:
            precedent = self._travail(poursuivre)
            if precedent is None:
                return self._erreur(404, f"travail à poursuivre inconnu : {poursuivre}")
            if precedent.etat not in ("termine", "echec"):
                return self._erreur(409, "le travail à poursuivre n'est pas terminé")
            dossier = precedent.dossier
        else:
            dossier = os.path.join(self.config.dossier, identifiant)
            os.makedirs(dossier, exist_ok=True)

        nom_script = nom_script_securise(outil, corps.get("nom_script", ""), identifiant)
        with open(os.path.join(dossier, nom_script), "w", encoding="utf-8") as f:
            f.write(script)

        travail = Travail(identifiant, outil, nom_script, dossier)
        with self.verrou:
            self.registre[identifiant] = travail
        self.file_travaux.put(travail)
        return self._json(201, {"id": identifiant})


def creer_worker(config: ConfigWorker):
    """
    Construit (serveur HTTP, thread exécuteur) sans les démarrer.
    Séparé de principal() pour être testable en local.
    """
    if not config.jeton:
        raise ValueError("Un jeton est obligatoire (config.jeton).")
    os.makedirs(config.dossier, exist_ok=True)
    registre, verrou, file_travaux = {}, threading.Lock(), queue.Queue()
    handler = type("RequeteWorkerConfigure", (RequeteWorker,), {
        "config": config, "registre": registre,
        "verrou": verrou, "file_travaux": file_travaux,
    })
    serveur = ThreadingHTTPServer((config.hote, config.port), handler)
    executeur = Executeur(config, file_travaux)
    return serveur, executeur


def principal(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Worker d'exécution distant du Studio IA — exécute les scripts "
                    "Blender / Unreal / FFmpeg / Csound envoyés par main.py --worker.")
    parser.add_argument("--hote", default="127.0.0.1",
                        help="Adresse d'écoute (0.0.0.0 pour exposer au réseau)")
    parser.add_argument("--port", type=int, default=8765, help="Port d'écoute")
    parser.add_argument("--jeton", default="",
                        help="Jeton d'accès (sinon : variable WORKER_JETON, sinon généré)")
    parser.add_argument("--dossier", default="travaux_worker",
                        help="Dossier où s'exécutent les travaux")
    parser.add_argument("--blender", default="blender", help="Chemin du binaire Blender")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Chemin du binaire FFmpeg")
    parser.add_argument("--csound", default="csound", help="Chemin du binaire Csound")
    parser.add_argument("--delai-max", type=int, default=7200,
                        help="Durée maximale d'un travail en secondes (défaut : 7200)")
    args = parser.parse_args(argv)

    jeton = (args.jeton.strip() or os.environ.get("WORKER_JETON", "").strip()
             or secrets.token_hex(16))
    config = ConfigWorker(hote=args.hote, port=args.port, jeton=jeton,
                          dossier=args.dossier, blender=args.blender,
                          ffmpeg=args.ffmpeg, csound=args.csound,
                          delai_max=args.delai_max)
    serveur, executeur = creer_worker(config)
    outils = outils_disponibles(config)
    port_effectif = serveur.server_address[1]

    print("─" * 62)
    print("  🛠  WORKER DISTANT DU STUDIO IA")
    print("─" * 62)
    print(f"  Écoute     : http://{args.hote}:{port_effectif}")
    print(f"  Jeton      : {jeton}")
    print(f"  Dossier    : {os.path.abspath(config.dossier)}")
    print(f"  Délai max  : {config.delai_max}s par travail")
    for outil in OUTILS_STUDIO:
        print(f"  {outil:<9}: {'✅ disponible' if outils[outil] else '❌ indisponible'}")
    if not outils["blender"]:
        print("  ⚠️  Blender introuvable — précisez --blender /chemin/vers/blender")
    print("\n  Côté studio, lancez :")
    print(f"    python main.py --reprendre --worker http://<ip-de-cette-machine>:{port_effectif}"
          f" --worker-jeton {jeton}")
    print("  (Ctrl+C pour arrêter le worker)")
    print("─" * 62)

    executeur.start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\n[worker] Arrêt demandé — au revoir.")
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
