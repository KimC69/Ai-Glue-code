"""
client_worker.py — Client du worker distant + exécuteur pour le pipeline.

Côté studio, ce module parle au serveur worker_distant.py lancé sur la
machine de rendu : envoi des scripts générés par les agents, suivi de
l'exécution, rapatriement des journaux et des fichiers produits dans
output/rendus/<outil>/.

Bibliothèque standard uniquement (urllib) : testable sans dépendances,
comme l'orchestrateur. Aucune fonction n'appelle sys.exit() — les erreurs
lèvent ErreurWorker et c'est l'appelant (orchestrateur / main.py) qui
décide de la suite.
"""

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class ErreurWorker(Exception):
    """Erreur de communication avec le worker, ou d'exécution distante."""


class ClientWorker:
    """Client HTTP minimal du worker distant (authentification par X-Jeton)."""

    def __init__(self, url: str, jeton: str, delai_requete: int = 30,
                 delai_telechargement: int = 120):
        self.url = url.rstrip("/")
        self.jeton = jeton
        self.delai_requete = delai_requete
        # Délai appliqué à chaque lecture de morceau pendant un téléchargement
        # (plus large : le réseau peut souffler entre deux morceaux d'un gros
        # fichier sans que ce soit une panne).
        self.delai_telechargement = delai_telechargement

    # ── Transport ────────────────────────────────────────────────────────────

    def _ouvrir(self, chemin: str, corps: dict = None, delai: float = None):
        """Ouvre la requête et traduit les erreurs de connexion en
        ErreurWorker. Retourne la réponse, à consommer dans un bloc with."""
        requete = urllib.request.Request(self.url + chemin)
        requete.add_header("X-Jeton", self.jeton)
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps).encode("utf-8")
            requete.add_header("Content-Type", "application/json")
        try:
            return urllib.request.urlopen(requete, data=donnees,
                                          timeout=delai or self.delai_requete)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8", "replace")).get("erreur", "")
            except Exception:
                pass
            if e.code == 401:
                raise ErreurWorker("Jeton refusé par le worker — vérifiez "
                                   "--worker-jeton ou la variable WORKER_JETON.") from e
            raise ErreurWorker(f"Le worker a répondu {e.code}"
                               + (f" : {detail}" if detail else "")) from e
        except urllib.error.URLError as e:
            raise ErreurWorker(
                f"Worker injoignable ({self.url}) : {e.reason}. Vérifiez qu'il est "
                "démarré sur la machine de rendu (python3 worker_distant.py) et que "
                "l'URL est correcte.") from e

    def _requete(self, chemin: str, corps: dict = None, brut: bool = False):
        """Requête courte (JSON ou petit texte) — la réponse tient en mémoire.
        Pour les fichiers volumineux, utilisez _telecharger_flux()."""
        try:
            with self._ouvrir(chemin, corps) as reponse:
                contenu = reponse.read()
        except (http.client.HTTPException, OSError) as e:
            raise ErreurWorker(f"Réponse du worker interrompue : {e}") from e
        if brut:
            return contenu
        try:
            return json.loads(contenu.decode("utf-8"))
        except ValueError as e:
            raise ErreurWorker(f"Réponse illisible du worker : {contenu[:120]!r}") from e

    def _telecharger_flux(self, chemin: str, destination: str) -> str:
        """Télécharge une ressource vers un fichier local, en flux (morceaux
        de 64 Kio) : une vidéo rendue peut peser plusieurs Go et ne doit
        jamais transiter entière en mémoire. Écrit d'abord un fichier
        `.partiel`, renommé une fois complet — aucun fichier tronqué ne peut
        passer pour un téléchargement réussi."""
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        temporaire = destination + ".partiel"
        try:
            with self._ouvrir(chemin, delai=self.delai_telechargement) as reponse, \
                 open(temporaire, "wb") as sortie:
                while True:
                    morceau = reponse.read(64 * 1024)
                    if not morceau:
                        break
                    sortie.write(morceau)
            os.replace(temporaire, destination)
            return destination
        except (http.client.HTTPException, OSError) as e:
            raise ErreurWorker(f"Téléchargement interrompu ({chemin}) : {e}") from e
        finally:
            if os.path.exists(temporaire):
                try:
                    os.remove(temporaire)
                except OSError:
                    pass

    # ── API ──────────────────────────────────────────────────────────────────

    def sante(self) -> dict:
        return self._requete("/sante")

    def soumettre(self, outil: str, nom_script: str, script: str,
                  poursuivre: str = "") -> str:
        corps = {"outil": outil, "nom_script": nom_script, "script": script}
        if poursuivre:
            corps["poursuivre"] = poursuivre
        return self._requete("/travaux", corps=corps)["id"]

    def statut(self, identifiant: str) -> dict:
        return self._requete(f"/travaux/{identifiant}")

    def journal(self, identifiant: str) -> str:
        """Journal complet, en mémoire — pour un aperçu court ou les tests.
        Pour rapatrier un journal potentiellement gros : telecharger_journal()."""
        contenu = self._requete(f"/travaux/{identifiant}/journal", brut=True)
        return contenu.decode("utf-8", "replace")

    def telecharger_journal(self, identifiant: str, destination: str) -> str:
        """Rapatrie le journal en flux, directement sur disque."""
        return self._telecharger_flux(f"/travaux/{identifiant}/journal", destination)

    def fichiers(self, identifiant: str) -> list:
        return self._requete(f"/travaux/{identifiant}/fichiers")["fichiers"]

    def telecharger(self, identifiant: str, nom: str, destination: str) -> str:
        chemin = f"/travaux/{identifiant}/fichiers/{urllib.parse.quote(nom, safe='')}"
        return self._telecharger_flux(chemin, destination)

    def attendre(self, identifiant: str, periode: float = 5.0,
                 rappel=None, periode_rappel: float = 30.0) -> dict:
        """Attend la fin du travail (sondage). `rappel(ecoule)` est appelé
        périodiquement pour informer l'utilisateur."""
        debut = time.time()
        dernier_rappel = 0.0
        while True:
            etat = self.statut(identifiant)
            if etat["etat"] in ("termine", "echec"):
                return etat
            ecoule = time.time() - debut
            if rappel is not None and ecoule - dernier_rappel >= periode_rappel:
                rappel(ecoule)
                dernier_rappel = ecoule
            time.sleep(periode)


class ExecuteurDistant:
    """
    « Agent » d'exécution distante branché dans le pipeline (champ fabrique
    d'une Etape) : envoie un script au worker, suit l'exécution, rapatrie
    le journal et les fichiers produits dans dossier_rendus/<outil>/.
    """

    def __init__(self, client: ClientWorker, dossier_rendus: str,
                 periode: float = 5.0):
        self.client = client
        self.dossier_rendus = dossier_rendus
        self.periode = periode

    # Méthodes appelées par les étapes du pipeline (via Etape.methode)

    def executer_blender(self, chemin_script: str) -> dict:
        return self._executer("blender", chemin_script)

    def executer_unreal(self, chemin_script: str) -> dict:
        return self._executer("unreal", chemin_script)

    def executer_ffmpeg(self, chemin_script: str, poursuivre_id: str = "") -> dict:
        # poursuivre_id : identifiant du travail Blender — l'export s'exécute
        # alors dans le même dossier, où la vidéo rendue est disponible.
        return self._executer("ffmpeg", chemin_script, poursuivre=poursuivre_id)

    def executer_csound(self, chemin_script: str) -> dict:
        # Rend la bande son (.csd) en audio : travail autonome, sans chaînage.
        return self._executer("csound", chemin_script)

    # ── Mécanique commune ────────────────────────────────────────────────────

    def _executer(self, outil: str, chemin_script: str, poursuivre: str = "") -> dict:
        if not chemin_script or not os.path.isfile(chemin_script):
            raise ErreurWorker(
                f"Script {outil} introuvable ({chemin_script or 'non généré'}) — "
                "lancez d'abord la production complète pour le générer.")
        with open(chemin_script, encoding="utf-8") as f:
            script = f.read()
        if not script.strip():
            raise ErreurWorker(f"Le script {outil} ({chemin_script}) est vide.")

        identifiant = self.client.soumettre(
            outil, os.path.basename(chemin_script), script, poursuivre)
        print(f"  ↗ Script envoyé au worker — travail {identifiant} ({outil})")
        final = self.client.attendre(
            identifiant, periode=self.periode,
            rappel=lambda s: print(f"  ⏳ {outil} en cours sur le worker... ({int(s)}s)"))

        # Rapatriement systématique — même en échec, le journal sert au diagnostic
        dossier = os.path.join(self.dossier_rendus, outil)
        os.makedirs(dossier, exist_ok=True)
        journal_path = os.path.join(dossier, f"journal_{identifiant}.log")
        self.client.telecharger_journal(identifiant, journal_path)

        fichiers = self.client.fichiers(identifiant)
        dossier_fichiers = os.path.join(dossier, "fichiers")
        for fichier in fichiers:
            nom = os.path.normpath(str(fichier["nom"]))
            if nom.startswith("..") or os.path.isabs(nom):
                continue  # nom anormal renvoyé par le worker — ignoré
            self.client.telecharger(identifiant, fichier["nom"],
                                    os.path.join(dossier_fichiers, nom))

        if final["etat"] != "termine":
            raise ErreurWorker(
                f"Exécution {outil} en échec sur le worker "
                f"(code {final['code_retour']}) — journal : {journal_path}")

        return {
            "travail_id": identifiant,
            "code_retour": final["code_retour"],
            "duree": final["duree"] or 0.0,
            "journal_path": journal_path,
            "nb_fichiers": len(fichiers),
            "dossier_fichiers": dossier_fichiers if fichiers else "",
        }
