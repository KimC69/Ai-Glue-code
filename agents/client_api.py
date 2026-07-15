"""
client_api.py — Client Python de l'API du Studio IA (api_serveur.py).

BRIQUE COMMUNE aux interfaces des étapes 9 et 10 : une petite classe qui parle
à `api_serveur.py` en HTTP et masque les détails répétitifs (en-tête
« Authorization: Bearer <jeton> », encodage JSON, lecture des codes d'erreur).

- L'application de BUREAU (étape 10, bureau.py) l'utilise directement.
- L'application mobile (étape 9, PWA) fait l'équivalent en JavaScript (pwa/app.js) ;
  ce fichier-ci est la version Python, utile au bureau et à tout script.

Bibliothèque standard uniquement (urllib), dans la même philosophie que
client_worker.py : testable sans aucune dépendance, et AUCUNE fonction n'appelle
sys.exit() — les erreurs lèvent `ErreurAPI` et c'est l'appelant qui décide de la
suite (afficher un message, réessayer, se reconnecter…).
"""

import json
import urllib.error
import urllib.request


class ErreurAPI(Exception):
    """Erreur renvoyée par l'API, ou survenue en tentant de la contacter.

    Attributs :
      - `code`    : le code HTTP (401, 403, 404, 500…) quand l'API a répondu ;
                    0 quand la connexion elle-même a échoué (serveur injoignable,
                    hôte inconnu, délai dépassé).
      - `message` : message lisible — le champ « erreur » renvoyé par l'API
                    lorsqu'il existe, sinon la cause réseau.
    """

    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message


class ClientAPI:
    """Client HTTP de l'API du Studio. Conserve le jeton de session obtenu à la
    connexion et l'ajoute automatiquement aux appels protégés."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000",
                 jeton: str = "", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.jeton = jeton
        self.role = ""
        self.timeout = timeout

    @property
    def connecte(self) -> bool:
        """Vrai si un jeton est en mémoire (pas de garantie qu'il soit encore
        valide côté serveur — seul un appel le confirmera)."""
        return bool(self.jeton)

    # ── Appel HTTP bas niveau ────────────────────────────────────────────────

    def _appel(self, methode: str, chemin: str, corps=None,
               authentifie: bool = True):
        """Envoie une requête et renvoie (code, objet_json). Toute erreur (HTTP
        4xx/5xx ou réseau) est convertie en `ErreurAPI` : l'appelant n'a qu'un
        seul type d'exception à gérer."""
        url = self.base_url + chemin
        entetes = {"Accept": "application/json"}
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            entetes["Content-Type"] = "application/json; charset=utf-8"
        if authentifie and self.jeton:
            entetes["Authorization"] = f"Bearer {self.jeton}"

        requete = urllib.request.Request(url, data=donnees, headers=entetes,
                                         method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=self.timeout) as rep:
                brut = rep.read().decode("utf-8")
                return rep.status, self._decoder(brut)
        except urllib.error.HTTPError as e:
            # L'API renvoie toujours un JSON {"erreur": "..."} même en 4xx/5xx.
            brut = e.read().decode("utf-8", "replace")
            objet = self._decoder(brut)
            message = objet.get("erreur") if isinstance(objet, dict) else ""
            raise ErreurAPI(message or f"Erreur HTTP {e.code}", code=e.code)
        except urllib.error.URLError as e:
            # Connexion impossible (serveur éteint, hôte/port faux, timeout…).
            raise ErreurAPI(f"Serveur injoignable : {e.reason}", code=0)

    @staticmethod
    def _decoder(brut: str):
        try:
            return json.loads(brut) if brut else {}
        except ValueError:
            return {}

    # ── Routes de l'API ──────────────────────────────────────────────────────

    def sante(self) -> dict:
        """GET /sante — sonde publique ({ok, version, service})."""
        _, corps = self._appel("GET", "/sante", authentifie=False)
        return corps

    def connexion(self, nom: str, mot_de_passe: str) -> dict:
        """POST /connexion — mémorise le jeton et le rôle en cas de succès.
        Lève ErreurAPI(code=401) si les identifiants sont faux."""
        _, corps = self._appel("POST", "/connexion",
                               {"nom": nom, "mot_de_passe": mot_de_passe},
                               authentifie=False)
        self.jeton = corps.get("jeton", "")
        self.role = corps.get("role", "")
        return corps

    def deconnexion(self) -> dict:
        """POST /deconnexion — révoque le jeton côté serveur. Le jeton local est
        effacé DANS TOUS LES CAS (même si le serveur répond une erreur) : se
        déconnecter ne doit jamais laisser l'interface dans un état ambigu."""
        try:
            _, corps = self._appel("POST", "/deconnexion")
            return corps
        except ErreurAPI:
            return {"ok": True}
        finally:
            self.jeton = ""
            self.role = ""

    def lister_productions(self) -> list:
        """GET /productions — liste des productions récentes (permission consulter)."""
        _, corps = self._appel("GET", "/productions")
        return corps.get("productions", [])

    def details_production(self, production_id: str) -> dict:
        """GET /productions/<id> — entête + étapes + événements (consulter)."""
        _, corps = self._appel("GET", f"/productions/{production_id}")
        return corps

    def lancer_production(self, idee: str, modele: str = "") -> dict:
        """POST /productions — démarre une production (permission lancer_production).
        Renvoie {id, statut, suivi} ; le suivi se fait via details_production()."""
        corps_requete = {"idee": idee}
        if modele:
            corps_requete["modele"] = modele
        _, corps = self._appel("POST", "/productions", corps_requete)
        return corps

    # ── Pilotage à distance d'une production (permission piloter_production) ───

    def piloter_production(self, production_id: str, commande: str) -> dict:
        """POST /productions/<id>/(pause|reprendre|arreter). `commande` doit être
        « pause », « reprendre » ou « arreter ». L'effet est appliqué par le
        pipeline à la fin de l'étape en cours, pas instantanément."""
        _, corps = self._appel(
            "POST", f"/productions/{production_id}/{commande}")
        return corps

    def mettre_en_pause(self, production_id: str) -> dict:
        return self.piloter_production(production_id, "pause")

    def reprendre_production(self, production_id: str) -> dict:
        return self.piloter_production(production_id, "reprendre")

    def arreter_production(self, production_id: str) -> dict:
        return self.piloter_production(production_id, "arreter")

    # ── Agents (activation/désactivation) ────────────────────────────────────

    def lister_agents(self) -> list:
        """GET /agents — catalogue des agents et leur état d'activation
        (permission consulter)."""
        _, corps = self._appel("GET", "/agents")
        return corps.get("agents", [])

    def definir_agent(self, numero: int, actif: bool) -> list:
        """POST /agents/<numero> {actif} — active/désactive un agent optionnel
        (permission gerer_utilisateurs). Renvoie la liste des agents à jour."""
        _, corps = self._appel("POST", f"/agents/{numero}", {"actif": bool(actif)})
        return corps.get("agents", [])

    # ── Mémoire et objectifs ─────────────────────────────────────────────────

    def lire_objectifs(self) -> dict:
        """GET /objectifs — note d'objectifs persistants (permission consulter)."""
        _, corps = self._appel("GET", "/objectifs")
        return corps

    def definir_objectifs(self, texte: str) -> dict:
        """POST /objectifs {texte} — enregistre les objectifs persistants
        (permission gerer_utilisateurs : réservé à l'administrateur)."""
        _, corps = self._appel("POST", "/objectifs", {"texte": texte})
        return corps

    def lire_memoire(self) -> dict:
        """GET /memoire — objectifs + résumé de l'état de travail (consulter)."""
        _, corps = self._appel("GET", "/memoire")
        return corps

    def reinitialiser_memoire(self) -> dict:
        """POST /memoire/reset — efface l'état de travail (gerer_utilisateurs).
        Refusé (409) si une production est en cours ou en pause."""
        _, corps = self._appel("POST", "/memoire/reset")
        return corps

    # ── Chat interactif avec un agent (hors production) ──────────────────────

    def chat(self, numero_agent: int, message: str, modele: str = "") -> str:
        """POST /chat {agent, message} — pose une question libre à un agent et
        renvoie sa réponse en texte (permission piloter_production)."""
        corps_requete = {"agent": numero_agent, "message": message}
        if modele:
            corps_requete["modele"] = modele
        _, corps = self._appel("POST", "/chat", corps_requete)
        return corps.get("reponse", "")
