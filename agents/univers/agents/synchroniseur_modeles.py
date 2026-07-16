"""
synchroniseur_modeles.py — Synchronisation des modèles Civitai entre PCs.

Lit le manifeste `manifest_modeles.json` d'un projet, vérifie l'intégrité de
chaque fichier sur le disque (présence + hash SHA256), puis re-télécharge
automatiquement les modèles absents ou corrompus depuis Civitai.

Utilisation autonome :
    from univers.agents.synchroniseur_modeles import SynchroniseurModeles
    sync = SynchroniseurModeles(config)
    rapport = sync.verifier(projet)
    sync.reparer(projet, rapport)
"""

import hashlib
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from univers.civitai_client import CivitaiClient, ErreurCivitai
from univers.config import ConfigUnivers
from univers.projet_manager import lire_manifest, enregistrer_dans_manifest


def _sha256_fichier(chemin: str) -> str:
    """Calcule le SHA256 d'un fichier (bloc par bloc)."""
    h = hashlib.sha256()
    try:
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(65536), b""):
                h.update(bloc)
        return h.hexdigest()
    except OSError:
        return ""


class SynchroniseurModeles:
    """Vérifie et re-télécharge les modèles manquants ou corrompus d'un projet."""

    def __init__(self, config: ConfigUnivers):
        self.config = config
        self.client = CivitaiClient(config)

    # ── Vérification ─────────────────────────────────────────────────────────

    def verifier(self, projet: dict) -> dict:
        """Lit le manifeste et vérifie chaque modèle.

        Retourne :
        {
          "total": int,
          "presents": [entrée, ...],       # fichier ok + hash valide
          "manquants": [entrée, ...],      # fichier absent
          "corrompus": [entrée, ...],      # hash ne correspond pas
          "sans_url": [entrée, ...],       # pas d'URL de téléchargement
        }
        """
        manifest = lire_manifest(projet)
        modeles = manifest.get("modeles", [])

        rapport = {
            "total": len(modeles),
            "presents": [],
            "manquants": [],
            "corrompus": [],
            "sans_url": [],
        }

        for entree in modeles:
            chemin_relatif = entree.get("chemin_relatif", "")
            chemin_absolu = os.path.join(projet["chemin"], chemin_relatif)

            if not os.path.isfile(chemin_absolu):
                rapport["manquants"].append(entree)
                continue

            hash_attendu = entree.get("hash_sha256", "")
            if hash_attendu:
                hash_reel = _sha256_fichier(chemin_absolu)
                if hash_reel != hash_attendu:
                    rapport["corrompus"].append(entree)
                    continue

            if not entree.get("download_url"):
                rapport["sans_url"].append(entree)
                continue

            rapport["presents"].append(entree)

        return rapport

    # ── Réparation ────────────────────────────────────────────────────────────

    def reparer(
        self,
        projet: dict,
        rapport: Optional[dict] = None,
        callback_progres: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Re-télécharge les modèles manquants et corrompus.

        `rapport` peut être le résultat de `verifier()` ; si None, appelle
        `verifier()` automatiquement.

        `callback_progres(message)` est appelé à chaque étape (facultatif).

        Retourne :
        {
          "retelecharges": [nom, ...],
          "echecs": [{"nom": ..., "erreur": ...}, ...],
          "ignores": [nom, ...],   # sans URL
        }
        """
        if rapport is None:
            rapport = self.verifier(projet)

        a_retelecharger = rapport["manquants"] + rapport["corrompus"]
        resultats = {"retelecharges": [], "echecs": [], "ignores": []}

        for entree in rapport["sans_url"]:
            resultats["ignores"].append(entree.get("fichier_nom", "?"))

        for entree in a_retelecharger:
            fichier_nom = entree.get("fichier_nom", "inconnu")
            url = entree.get("download_url", "")

            if not url:
                resultats["ignores"].append(fichier_nom)
                continue

            chemin_relatif = entree.get("chemin_relatif", os.path.join("models", fichier_nom))
            chemin_absolu = os.path.join(projet["chemin"], chemin_relatif)

            if callback_progres:
                callback_progres(f"↓ Téléchargement de {fichier_nom}…")

            try:
                self.client.telecharger_modele(url, chemin_absolu)

                # Met à jour le hash dans le manifeste
                nouveau_hash = _sha256_fichier(chemin_absolu)
                taille = os.path.getsize(chemin_absolu) if os.path.exists(chemin_absolu) else 0
                entree_maj = dict(entree)
                entree_maj["hash_sha256"] = nouveau_hash
                entree_maj["taille_octets"] = taille
                entree_maj["date_telechargement"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                enregistrer_dans_manifest(projet, entree_maj)

                resultats["retelecharges"].append(fichier_nom)
                if callback_progres:
                    callback_progres(f"✅ {fichier_nom} téléchargé")

            except ErreurCivitai as e:
                resultats["echecs"].append({"nom": fichier_nom, "erreur": str(e)})
                if callback_progres:
                    callback_progres(f"❌ {fichier_nom} — {e}")

        return resultats

    # ── Rapport lisible ───────────────────────────────────────────────────────

    @staticmethod
    def resumer_rapport(rapport: dict) -> str:
        """Retourne une ligne de résumé humain du rapport de vérification."""
        p = len(rapport["presents"])
        m = len(rapport["manquants"])
        c = len(rapport["corrompus"])
        s = len(rapport["sans_url"])
        t = rapport["total"]
        parties = [f"{t} modèle(s) dans le manifeste"]
        if p:
            parties.append(f"✅ {p} présent(s)")
        if m:
            parties.append(f"❌ {m} manquant(s)")
        if c:
            parties.append(f"⚠️ {c} corrompu(s)")
        if s:
            parties.append(f"ℹ️ {s} sans URL")
        return " — ".join(parties)
