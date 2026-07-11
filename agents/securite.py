"""
securite.py — Fondation d'authentification du Studio IA.

Fournit la brique de sécurité que l'API (étape 7) puis les interfaces
web/Android (étapes 8–9) utiliseront pour savoir QUI a le droit de commander
le studio :

  - COMPTES UTILISATEURS stockés dans une base SQLite dédiée
    (`output/securite.db`, séparée de `studio.db` qui contient l'historique
    créatif : on ne mélange pas les données sensibles avec les productions) ;
  - MOTS DE PASSE jamais stockés en clair : hachage pbkdf2-hmac-sha256 avec un
    sel aléatoire par utilisateur et un grand nombre d'itérations (méthode la
    plus portable de la bibliothèque standard) ;
  - RÔLES : admin / operateur / observateur, chacun associé à un jeu de
    permissions ;
  - JETONS DE SESSION SIGNÉS (hmac) et AUTONOMES : ils contiennent l'utilisateur,
    son rôle et une date d'expiration, si bien qu'une API peut les VÉRIFIER SANS
    interroger la base — juste en recalculant la signature. Révocables.

Bibliothèque standard uniquement (sqlite3, hashlib, hmac, secrets, base64,
json, time) : aucune dépendance, testable sans clé API — comme l'orchestrateur,
le worker et le journal.

Principe de sécurité : ce module ÉCHOUE FERMÉ (« fail closed »). Contrairement
au journal — dont le mode dégradé rend les écritures inoffensives pour ne jamais
casser une production —, une vérification qui ne peut pas aboutir (base
indisponible, signature invalide, jeton expiré, révocation invérifiable) REFUSE
l'accès. On ne laisse jamais un doute autoriser quelqu'un.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Nombre d'itérations pbkdf2 : compromis coût/sécurité. Stocké PAR utilisateur
# dans la base pour pouvoir l'augmenter plus tard sans invalider les comptes
# existants (les anciens hachages restent vérifiables avec leur propre valeur).
ITERATIONS_DEFAUT = 200_000
DUREE_JETON_DEFAUT = 12 * 3600          # 12 h
ROLE_DEFAUT = "operateur"

# Rôles → permissions. Un seul endroit à modifier pour faire évoluer les droits.
PERMISSIONS = {
    "admin":       {"gerer_utilisateurs", "lancer_production",
                    "piloter_production", "consulter"},
    "operateur":   {"lancer_production", "piloter_production", "consulter"},
    "observateur": {"consulter"},
}
ROLES_VALIDES = set(PERMISSIONS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hash_mdp    TEXT NOT NULL,          -- pbkdf2-hmac-sha256, encodé hexadécimal
    sel         TEXT NOT NULL,          -- sel aléatoire, encodé hexadécimal
    iterations  INTEGER NOT NULL,
    role        TEXT NOT NULL,
    actif       INTEGER NOT NULL DEFAULT 1,
    cree_le     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jetons_revoques (
    jti        TEXT PRIMARY KEY,        -- identifiant unique du jeton
    revoque_le TEXT NOT NULL,
    expire_le  REAL                     -- epoch : purge possible après expiration
);
"""


class ErreurSecurite(Exception):
    """Erreur d'authentification ou d'administration des comptes.

    Sert aussi bien aux refus (identifiants faux, jeton invalide/expiré/révoqué)
    qu'aux problèmes d'exploitation (base indisponible, clé de signature absente).
    Dans tous les cas, l'appelant doit traiter l'opération comme REFUSÉE."""


def _horodatage() -> str:
    """Horodatage ISO 8601 en UTC (lisible dans la base, sans fuseau ambigu)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _b64url_encode(donnees: bytes) -> str:
    """Base64 URL-safe sans remplissage (compatible en-têtes HTTP / URL)."""
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode("ascii")


def _b64url_decode(texte: str) -> bytes:
    rembourrage = "=" * (-len(texte) % 4)
    return base64.urlsafe_b64decode(texte + rembourrage)


class Securite:
    """Gestion des comptes, des mots de passe hachés et des jetons de session.

    La base SQLite (`output/securite.db`) porte les comptes et la liste de
    révocation ; les jetons, eux, sont autonomes et signés — un service tiers
    peut les valider avec la seule clé de signature, sans accès à la base.
    """

    def __init__(self, dossier: str = "", nom_bdd: str = "securite.db",
                 cle_signature: str = "", iterations: int = ITERATIONS_DEFAUT):
        self.dossier = dossier or DOSSIER_DEFAUT
        self.bdd_path = os.path.join(self.dossier, nom_bdd)
        self.iterations = iterations
        # Clé de signature des jetons : SESSION_SECRET par défaut. Elle n'est
        # PAS conservée en base et ne doit jamais être affichée. Sans elle,
        # la gestion des comptes reste possible, mais toute opération sur les
        # jetons échoue clairement (fail closed).
        self._cle = (cle_signature or os.environ.get("SESSION_SECRET", "")).strip()
        self._verrou = threading.RLock()
        self._connexion = None
        self._init_bdd()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_bdd(self) -> None:
        try:
            os.makedirs(self.dossier, exist_ok=True)
            self._connexion = sqlite3.connect(
                self.bdd_path, check_same_thread=False, timeout=5.0)
            self._connexion.row_factory = sqlite3.Row
            # Accès concurrent (API multi-requêtes + gestion des comptes en CLI) :
            # WAL + busy_timeout évitent qu'une contention ponctuelle ne fasse
            # échouer une vérification de jeton (qui, en échouant fermé, se
            # traduirait par un 401 injustifié).
            self._connexion.execute("PRAGMA journal_mode=WAL")
            self._connexion.execute("PRAGMA busy_timeout=5000")
            self._connexion.executescript(SCHEMA)
            self._connexion.commit()
        except (sqlite3.Error, OSError) as e:
            # Contrairement au journal, on NE dégrade PAS silencieusement : sans
            # base, aucune authentification n'est fiable. On lève pour que
            # l'appelant sache que le sous-système de sécurité est indisponible.
            raise ErreurSecurite(
                f"Base de sécurité indisponible ({e}) — authentification impossible."
            ) from e

    def _executer(self, sql: str, params: tuple = ()):
        try:
            with self._verrou:
                curseur = self._connexion.execute(sql, params)
                self._connexion.commit()
                return curseur
        except sqlite3.Error as e:
            raise ErreurSecurite(f"Erreur base de sécurité : {e}") from e

    # ── Hachage des mots de passe ─────────────────────────────────────────────

    @staticmethod
    def _hacher(mot_de_passe: str, sel: bytes, iterations: int) -> str:
        empreinte = hashlib.pbkdf2_hmac(
            "sha256", mot_de_passe.encode("utf-8"), sel, iterations)
        return empreinte.hex()

    # ── Gestion des comptes ───────────────────────────────────────────────────

    def creer_utilisateur(self, nom: str, mot_de_passe: str,
                          role: str = ROLE_DEFAUT) -> dict:
        """Crée un compte. Lève ErreurSecurite si le nom existe déjà, si le rôle
        est inconnu, ou si le nom / mot de passe est vide."""
        nom = (nom or "").strip()
        if not nom:
            raise ErreurSecurite("Le nom d'utilisateur ne peut pas être vide.")
        if not mot_de_passe:
            raise ErreurSecurite("Le mot de passe ne peut pas être vide.")
        if role not in ROLES_VALIDES:
            raise ErreurSecurite(
                f"Rôle inconnu : {role!r}. Rôles valides : "
                f"{', '.join(sorted(ROLES_VALIDES))}.")
        sel = secrets.token_bytes(16)
        hash_mdp = self._hacher(mot_de_passe, sel, self.iterations)
        try:
            self._executer(
                "INSERT INTO utilisateurs (nom, hash_mdp, sel, iterations, role, "
                "actif, cree_le) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (nom, hash_mdp, sel.hex(), self.iterations, role, _horodatage()))
        except ErreurSecurite as e:
            # UNIQUE COLLATE NOCASE : doublon insensible à la casse.
            if "UNIQUE" in str(e):
                raise ErreurSecurite(
                    f"L'utilisateur {nom!r} existe déjà.") from None
            raise
        return {"nom": nom, "role": role}

    def _lire_utilisateur(self, nom: str):
        curseur = self._executer(
            "SELECT * FROM utilisateurs WHERE nom=? COLLATE NOCASE",
            ((nom or "").strip(),))
        return curseur.fetchone() if curseur else None

    def verifier_identifiants(self, nom: str, mot_de_passe: str):
        """Retourne le compte (dict) si le mot de passe est correct et le compte
        actif, sinon None. Comparaison à temps constant (anti-timing)."""
        ligne = self._lire_utilisateur(nom)
        if ligne is None or not ligne["actif"]:
            # On hache quand même dans le vide : le temps de réponse ne révèle
            # pas si le nom existe (défense contre l'énumération de comptes).
            self._hacher(mot_de_passe, b"factice", self.iterations)
            return None
        attendu = ligne["hash_mdp"]
        calcule = self._hacher(mot_de_passe, bytes.fromhex(ligne["sel"]),
                               ligne["iterations"])
        if not hmac.compare_digest(attendu, calcule):
            return None
        return {"nom": ligne["nom"], "role": ligne["role"]}

    def changer_mot_de_passe(self, nom: str, nouveau: str) -> None:
        if not nouveau:
            raise ErreurSecurite("Le nouveau mot de passe ne peut pas être vide.")
        if self._lire_utilisateur(nom) is None:
            raise ErreurSecurite(f"Utilisateur inconnu : {nom!r}.")
        sel = secrets.token_bytes(16)
        hash_mdp = self._hacher(nouveau, sel, self.iterations)
        self._executer(
            "UPDATE utilisateurs SET hash_mdp=?, sel=?, iterations=? "
            "WHERE nom=? COLLATE NOCASE",
            (hash_mdp, sel.hex(), self.iterations, nom.strip()))

    def definir_role(self, nom: str, role: str) -> None:
        if role not in ROLES_VALIDES:
            raise ErreurSecurite(
                f"Rôle inconnu : {role!r}. Rôles valides : "
                f"{', '.join(sorted(ROLES_VALIDES))}.")
        if self._lire_utilisateur(nom) is None:
            raise ErreurSecurite(f"Utilisateur inconnu : {nom!r}.")
        self._executer("UPDATE utilisateurs SET role=? WHERE nom=? COLLATE NOCASE",
                       (role, nom.strip()))

    def supprimer_utilisateur(self, nom: str) -> None:
        curseur = self._executer(
            "DELETE FROM utilisateurs WHERE nom=? COLLATE NOCASE",
            ((nom or "").strip(),))
        if curseur is not None and curseur.rowcount == 0:
            raise ErreurSecurite(f"Utilisateur inconnu : {nom!r}.")

    def lister_utilisateurs(self) -> list:
        curseur = self._executer(
            "SELECT nom, role, actif, cree_le FROM utilisateurs "
            "ORDER BY nom COLLATE NOCASE")
        return [dict(r) for r in curseur.fetchall()] if curseur else []

    def compte_utilisateurs(self) -> int:
        curseur = self._executer("SELECT COUNT(*) AS n FROM utilisateurs")
        ligne = curseur.fetchone() if curseur else None
        return int(ligne["n"]) if ligne else 0

    # ── Jetons de session signés (autonomes) ──────────────────────────────────

    def _exiger_cle(self) -> bytes:
        if not self._cle:
            raise ErreurSecurite(
                "Clé de signature absente : définissez le secret SESSION_SECRET "
                "pour émettre ou vérifier des jetons.")
        return self._cle.encode("utf-8")

    def _signer(self, message: str) -> str:
        signature = hmac.new(self._exiger_cle(), message.encode("utf-8"),
                             hashlib.sha256).digest()
        return _b64url_encode(signature)

    def emettre_jeton(self, nom: str, role: str,
                      duree_s: int = DUREE_JETON_DEFAUT) -> str:
        """Émet un jeton signé et autonome pour (nom, role). Le contenu est
        lisible (base64) mais infalsifiable sans la clé de signature."""
        if role not in ROLES_VALIDES:
            raise ErreurSecurite(f"Rôle inconnu : {role!r}.")
        maintenant = int(time.time())
        charge = {
            "sub": nom, "role": role, "iat": maintenant,
            "exp": maintenant + int(duree_s), "jti": secrets.token_hex(8),
        }
        charge_b64 = _b64url_encode(
            json.dumps(charge, separators=(",", ":")).encode("utf-8"))
        return f"{charge_b64}.{self._signer(charge_b64)}"

    def authentifier(self, nom: str, mot_de_passe: str,
                     duree_s: int = DUREE_JETON_DEFAUT) -> str:
        """Vérifie les identifiants et retourne un jeton, ou lève ErreurSecurite.
        Un seul message d'erreur pour nom ou mot de passe faux (on ne révèle
        pas lequel des deux est en cause)."""
        compte = self.verifier_identifiants(nom, mot_de_passe)
        if compte is None:
            raise ErreurSecurite("Nom d'utilisateur ou mot de passe incorrect.")
        return self.emettre_jeton(compte["nom"], compte["role"], duree_s)

    def _charge_signee(self, jeton: str) -> dict:
        """Découpe le jeton, vérifie sa signature (temps constant), décode et
        VALIDE sa charge. Toute erreur de format, de base64, de JSON ou de type
        est convertie en ErreurSecurite : un jeton forgé ne peut jamais faire
        remonter une exception native (pas de 500/DoS applicatif à l'étape API).
        Cette méthode ne juge PAS l'expiration ni la révocation (l'appelant le
        fait), pour rester réutilisable par verifier_jeton et revoquer_jeton."""
        try:
            charge_b64, signature = (jeton or "").split(".")
        except ValueError:
            raise ErreurSecurite("Jeton mal formé.") from None
        if not hmac.compare_digest(signature, self._signer(charge_b64)):
            raise ErreurSecurite("Signature du jeton invalide.")
        try:
            charge = json.loads(_b64url_decode(charge_b64))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise ErreurSecurite("Contenu du jeton illisible.") from None
        if not isinstance(charge, dict):
            raise ErreurSecurite("Contenu du jeton invalide.")
        return charge

    @staticmethod
    def _entier(valeur, defaut: int = 0) -> int:
        """Convertit une valeur de claim en entier sans jamais lever (un `exp`
        non numérique dans un jeton forgé ne doit pas casser la vérification —
        on renvoie le défaut, ce qui mène à un refus par expiration)."""
        try:
            return int(valeur)
        except (TypeError, ValueError):
            return defaut

    def verifier_jeton(self, jeton: str) -> dict:
        """Valide un jeton et retourne sa charge utile, ou lève ErreurSecurite.

        Contrôles (échec fermé à chaque étape) : format → signature (temps
        constant) → charge JSON valide → expiration → non-révocation. La
        révocation est vérifiée en base ; si la base est injoignable, on REFUSE
        (on ne peut pas garantir que le jeton n'a pas été révoqué)."""
        charge = self._charge_signee(jeton)
        if self._entier(charge.get("exp", 0)) < int(time.time()):
            raise ErreurSecurite("Jeton expiré.")
        jti = charge.get("jti", "")
        if not isinstance(jti, str) or self._est_revoque(jti):
            raise ErreurSecurite("Jeton révoqué.")
        return charge

    def _est_revoque(self, jti: str) -> bool:
        if not jti:
            return True                    # jeton sans identifiant : suspect → refus
        curseur = self._executer(
            "SELECT 1 FROM jetons_revoques WHERE jti=?", (jti,))
        return curseur.fetchone() is not None if curseur else True

    def revoquer_jeton(self, jeton: str) -> None:
        """Révoque un jeton (par son jti). Vérifie d'abord sa signature et sa
        charge (via _charge_signee, qui normalise toute erreur en ErreurSecurite)
        pour ne pas polluer la liste avec des valeurs arbitraires."""
        charge = self._charge_signee(jeton)
        jti = charge.get("jti", "")
        if not isinstance(jti, str) or not jti:
            raise ErreurSecurite("Jeton sans identifiant révocable (jti).")
        self._executer(
            "INSERT OR IGNORE INTO jetons_revoques (jti, revoque_le, expire_le) "
            "VALUES (?, ?, ?)",
            (jti, _horodatage(), float(self._entier(charge.get("exp", 0)))))

    def purger_revocations(self) -> int:
        """Supprime de la liste de révocation les jetons déjà expirés (ils sont
        de toute façon refusés par l'expiration). Retourne le nombre purgé."""
        curseur = self._executer(
            "DELETE FROM jetons_revoques WHERE expire_le < ?", (time.time(),))
        return curseur.rowcount if curseur else 0

    # ── Permissions ───────────────────────────────────────────────────────────

    @staticmethod
    def permissions_du_role(role: str) -> set:
        return set(PERMISSIONS.get(role, set()))

    @staticmethod
    def a_permission(role: str, permission: str) -> bool:
        return permission in PERMISSIONS.get(role, set())

    def jeton_autorise(self, jeton: str, permission: str) -> dict:
        """Vérifie le jeton PUIS la permission. Retourne la charge si tout est
        bon, sinon lève ErreurSecurite (fail closed)."""
        charge = self.verifier_jeton(jeton)
        if not self.a_permission(charge.get("role", ""), permission):
            raise ErreurSecurite(
                f"Permission refusée : le rôle {charge.get('role')!r} ne peut pas "
                f"« {permission} ».")
        return charge

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def fermer(self) -> None:
        if self._connexion is not None:
            try:
                self._connexion.close()
            except sqlite3.Error:
                pass
            self._connexion = None
