"""
journal_production.py — Journal de production : base de données SQLite +
logs structurés JSONL.

Trace chaque production, chaque étape et chaque événement de l'orchestrateur
pour deux usages complémentaires :
  - un HISTORIQUE INTERROGEABLE (SQLite) : quelles productions, quelles étapes,
    combien de révisions, durées, échecs — la matière première des futures
    interfaces web/Android (tableau de bord, rapports) ;
  - un FLUX D'ÉVÉNEMENTS STRUCTURÉ (JSONL, une ligne JSON par événement) :
    exploitable en direct pour suivre le raisonnement de l'orchestrateur et
    afficher des journaux d'activité (étapes 8–10 de la feuille de route).

Bibliothèque standard uniquement (sqlite3, json) : aucune dépendance, testable
sans clé API — comme l'orchestrateur et le worker.

Règle d'or : la journalisation ne doit JAMAIS interrompre une production. Toute
erreur d'écriture (disque plein, base verrouillée, chemin en lecture seule) est
absorbée et signalée une fois, puis le journal passe en mode dégradé — la
production continue normalement, sans traces.
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

DOSSIER_DEFAUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

SCHEMA = """
CREATE TABLE IF NOT EXISTS productions (
    id          TEXT PRIMARY KEY,
    idee        TEXT NOT NULL,
    modele      TEXT,
    mode        TEXT,
    statut      TEXT NOT NULL DEFAULT 'en_cours',
    demarree_le TEXT NOT NULL,
    terminee_le TEXT
);
CREATE TABLE IF NOT EXISTS etapes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id TEXT NOT NULL,
    numero        INTEGER,
    nom           TEXT NOT NULL,
    statut        TEXT NOT NULL,          -- reussie | ignoree | echouee
    duree_s       REAL,
    revisions     INTEGER DEFAULT 0,
    detail        TEXT,
    horodatage    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evenements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id TEXT NOT NULL,
    horodatage    TEXT NOT NULL,
    type          TEXT NOT NULL,
    niveau        TEXT NOT NULL DEFAULT 'info',   -- info | avertissement | critique
    message       TEXT,
    donnees       TEXT                            -- JSON des champs additionnels
);
CREATE INDEX IF NOT EXISTS idx_etapes_prod     ON etapes(production_id);
CREATE INDEX IF NOT EXISTS idx_evenements_prod ON evenements(production_id);
"""


def _horodatage() -> str:
    """Horodatage ISO 8601 en UTC (comparable et sans ambiguïté de fuseau)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JournalProduction:
    """
    Journal d'une production : écrit à la fois dans une base SQLite partagée
    (`output/studio.db`) et dans un fichier JSONL propre à la production
    (`output/journaux/<production_id>.jsonl`).

    L'objet expose exactement les méthodes que l'orchestrateur appelle
    (etape_demarree / etape_reussie / etape_ignoree / etape_echouee /
    etape_revisee / evenement) ainsi que les méthodes de cycle de vie
    (demarrer_production / terminer_production) et de lecture pour les
    interfaces (lister_productions / details_production).
    """

    def __init__(self, production_id: str = "", dossier: str = "",
                 nom_bdd: str = "studio.db"):
        self.production_id = production_id or uuid.uuid4().hex[:12]
        self.dossier = dossier or DOSSIER_DEFAUT
        self.bdd_path = os.path.join(self.dossier, nom_bdd)
        self.jsonl_path = os.path.join(self.dossier, "journaux",
                                       f"{self.production_id}.jsonl")
        # Verrou réentrant : evenement() le tient pendant les écritures SQLite
        # ET JSONL d'un même événement (ordre cohérent entre les deux flux),
        # or _executer / _ecrire_jsonl l'acquièrent aussi individuellement.
        self._verrou = threading.RLock()
        self._degrade = False          # base SQLite hors service
        self._jsonl_hs = False         # fichier JSONL hors service
        self._connexion = None
        self._init_bdd()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_bdd(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.jsonl_path), exist_ok=True)
            self._connexion = sqlite3.connect(self.bdd_path, check_same_thread=False)
            self._connexion.row_factory = sqlite3.Row
            self._connexion.executescript(SCHEMA)
            self._connexion.commit()
        except (sqlite3.Error, OSError) as e:
            self._passer_en_degrade(e)

    # ── Écriture bas niveau (défensive) ───────────────────────────────────────

    def _executer(self, sql: str, params: tuple = ()):
        """Exécute une requête SQLite. Retourne le curseur, ou None si le
        journal est dégradé / en échec (jamais d'exception propagée)."""
        if self._degrade or self._connexion is None:
            return None
        try:
            with self._verrou:
                curseur = self._connexion.execute(sql, params)
                self._connexion.commit()
                return curseur
        except sqlite3.Error as e:
            self._passer_en_degrade(e)
            return None

    def _ecrire_jsonl(self, objet: dict) -> None:
        if self._jsonl_hs:
            return
        # 1) Sérialisation (default=str couvre les objets ordinaires). Un
        #    événement irrécupérable (référence circulaire) est réduit à une
        #    ligne sûre : on ne perd JAMAIS tout le flux pour un seul événement.
        try:
            ligne = json.dumps(objet, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            ligne = json.dumps({
                "horodatage": objet.get("horodatage"),
                "production_id": objet.get("production_id"),
                "type": objet.get("type"),
                "niveau": objet.get("niveau"),
                "message": objet.get("message"),
                "_donnees_illisibles": True,
            }, ensure_ascii=False)
        # 2) Écriture. Seule une vraie panne d'E/S (disque) désactive le flux.
        try:
            with self._verrou:
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(ligne + "\n")
        except OSError as e:
            self._jsonl_hs = True
            print(f"[Journal] Log JSONL indisponible ({e}) — la production "
                  "continue sans flux d'événements.")

    @staticmethod
    def _serialiser(donnees: dict) -> str:
        """Sérialise les données d'un événement en JSON sans jamais lever :
        `default=str` couvre les objets ordinaires, et le repli attrape les
        cas extrêmes (références circulaires)."""
        try:
            return json.dumps(donnees, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return json.dumps({"_donnees_illisibles": str(list(donnees.keys()))},
                              ensure_ascii=False)

    def _passer_en_degrade(self, e: Exception) -> None:
        if not self._degrade:
            self._degrade = True
            print(f"[Journal] Base de données indisponible ({e}) — la production "
                  "continue sans historique SQLite.")

    # ── Événement générique (SQLite + JSONL) ──────────────────────────────────

    def evenement(self, type: str, message: str = "", niveau: str = "info",
                  **donnees) -> None:
        """Enregistre un événement dans la base ET dans le flux JSONL.

        Aucune écriture ni sérialisation ne peut lever : `_serialiser`,
        `_executer` et `_ecrire_jsonl` absorbent toutes leurs erreurs. Les deux
        écritures se font sous le même verrou pour que l'ordre des événements
        reste identique entre SQLite et JSONL (best-effort : si un support est
        en panne, l'autre continue seul — la journalisation ne bloque jamais)."""
        horo = _horodatage()
        donnees_json = self._serialiser(donnees) if donnees else None
        with self._verrou:
            self._executer(
                "INSERT INTO evenements (production_id, horodatage, type, niveau, "
                "message, donnees) VALUES (?, ?, ?, ?, ?, ?)",
                (self.production_id, horo, type, niveau, message, donnees_json))
            self._ecrire_jsonl({
                "horodatage": horo, "production_id": self.production_id,
                "type": type, "niveau": niveau, "message": message, **donnees})

    # ── Cycle de vie d'une production ─────────────────────────────────────────

    def demarrer_production(self, idee: str, modele: str = "",
                            mode: str = "standard") -> None:
        """Ouvre (ou rouvre, en cas de reprise) la production courante.

        En reprise, `production_id` est réutilisé : la même ligne est remise en
        « en_cours » et les nouvelles étapes s'ajoutent à l'historique existant."""
        self._executer(
            "INSERT OR IGNORE INTO productions (id, idee, modele, mode, statut, "
            "demarree_le) VALUES (?, ?, ?, ?, 'en_cours', ?)",
            (self.production_id, idee, modele, mode, _horodatage()))
        self._executer(
            "UPDATE productions SET statut='en_cours', modele=?, mode=?, "
            "terminee_le=NULL WHERE id=?",
            (modele, mode, self.production_id))
        self.evenement("production_demarree", f"Production démarrée : {idee}",
                       idee=idee, modele=modele, mode=mode)

    def terminer_production(self, statut: str = "terminee") -> None:
        """Clôt la production. `statut` : terminee | echec | arretee."""
        self._executer(
            "UPDATE productions SET statut=?, terminee_le=? WHERE id=?",
            (statut, _horodatage(), self.production_id))
        self.evenement("production_terminee", f"Production : {statut}",
                       niveau="critique" if statut == "echec" else "info",
                       statut=statut)

    # ── Événements d'étape (appelés par l'orchestrateur) ──────────────────────

    def _enregistrer_etape(self, numero, nom, statut, duree_s, revisions,
                           detail) -> None:
        self._executer(
            "INSERT INTO etapes (production_id, numero, nom, statut, duree_s, "
            "revisions, detail, horodatage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.production_id, numero, nom, statut, duree_s,
             revisions or 0, detail, _horodatage()))

    def etape_demarree(self, numero, nom) -> None:
        self.evenement("etape_demarree", f"Étape {numero} — {nom}",
                       numero=numero, nom=nom)

    def etape_reussie(self, numero, nom, duree_s=None, revisions=0,
                      detail="") -> None:
        self._enregistrer_etape(numero, nom, "reussie", duree_s, revisions,
                                detail or None)
        self.evenement("etape_reussie", f"Étape {numero} réussie — {nom}",
                       numero=numero, nom=nom, duree_s=duree_s,
                       revisions=revisions)

    def etape_ignoree(self, numero, nom) -> None:
        self._enregistrer_etape(numero, nom, "ignoree", None, 0, None)
        self.evenement("etape_ignoree",
                       f"Étape {numero} ignorée (déjà faite) — {nom}",
                       numero=numero, nom=nom)

    def etape_echouee(self, numero, nom, erreur, critique=False) -> None:
        self._enregistrer_etape(numero, nom, "echouee", None, 0, str(erreur))
        self.evenement("etape_echouee",
                       f"Étape {numero} échouée — {nom} : {erreur}",
                       niveau="critique" if critique else "avertissement",
                       numero=numero, nom=nom, erreur=str(erreur),
                       critique=critique)

    def etape_revisee(self, numero, nom, directives="") -> None:
        self.evenement("etape_revisee", f"Révision de l'étape {numero} — {nom}",
                       numero=numero, nom=nom, directives=directives)

    # ── Lecture (pour l'historique et les futures interfaces) ──────────────────

    def lister_productions(self, limite: int = 50) -> list:
        """Productions les plus récentes, avec le nombre d'étapes réussies."""
        curseur = self._executer(
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM etapes e "
            " WHERE e.production_id = p.id AND e.statut='reussie') AS etapes_reussies "
            "FROM productions p ORDER BY p.demarree_le DESC LIMIT ?", (limite,))
        return [dict(r) for r in curseur.fetchall()] if curseur else []

    def details_production(self, production_id: str = "") -> dict:
        """Fiche complète d'une production : entête + étapes + événements."""
        pid = production_id or self.production_id
        entete = self._executer("SELECT * FROM productions WHERE id=?", (pid,))
        ligne = entete.fetchone() if entete else None
        if ligne is None:
            return {}
        etapes = self._executer(
            "SELECT numero, nom, statut, duree_s, revisions, detail, horodatage "
            "FROM etapes WHERE production_id=? ORDER BY id", (pid,))
        evenements = self._executer(
            "SELECT horodatage, type, niveau, message, donnees "
            "FROM evenements WHERE production_id=? ORDER BY id", (pid,))
        return {
            "production": dict(ligne),
            "etapes": [dict(r) for r in etapes.fetchall()] if etapes else [],
            "evenements": [dict(r) for r in evenements.fetchall()] if evenements else [],
        }

    def fermer(self) -> None:
        if self._connexion is not None:
            try:
                self._connexion.close()
            except sqlite3.Error:
                pass
            self._connexion = None
