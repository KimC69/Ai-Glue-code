"""
executeur_local.py — Exécution AUTOMATIQUE des scripts sur CETTE machine.

Jusqu'ici, les agents produisaient des scripts (Blender, Unreal, FFmpeg,
Csound) que l'on lançait à la main, ou via le worker distant. Ce module
permet au studio de LANCER LUI-MÊME les rendus, en local, sans intervention :
l'agent « ouvre » réellement le logiciel (en mode headless) et produit le
fichier final.

⚠️  Sécurité — à lire absolument
    Exécuter localement des scripts *générés par un LLM*, c'est exécuter du
    code sur votre propre machine. Pour Blender (.py) et Unreal/FFmpeg (.sh),
    cela revient à exécuter du Python / du shell arbitraire. Csound (.csd) est
    beaucoup moins risqué (langage de synthèse musicale). L'exécution locale
    est donc **désactivée par défaut** : elle ne s'active qu'avec l'option
    explicite `--local` de main.py, qui affiche un avertissement clair.

Garde-fous conservés (échoue-fermé) :
    - liste blanche stricte des outils (worker_distant.OUTILS_STUDIO) ;
    - la commande est construite par NOTRE code (construire_commande), jamais
      par le LLM, et exécutée SANS shell (liste d'arguments) ;
    - nom de fichier assaini (nom_script_securise) — pas de traversée ;
    - chaque rendu tourne dans un dossier isolé, avec un délai maximal.

Bibliothèque standard uniquement (subprocess, shutil…) : cohérent avec le
reste du projet, testable sans dépendance. Aucune fonction n'appelle
sys.exit() — les erreurs lèvent ErreurExecutionLocale et c'est l'orchestrateur
qui décide (les étapes de rendu sont critique=False, donc non bloquantes).
"""

import os
import subprocess
import time
import uuid

from worker_distant import (
    ConfigWorker,
    OUTILS_STUDIO,
    Travail,
    construire_commande,
    nom_script_securise,
    outils_disponibles,
)


class ErreurExecutionLocale(Exception):
    """Échec de préparation ou d'exécution d'un rendu local."""


class ExecuteurLocal:
    """
    « Agent » d'exécution locale branché dans le pipeline (champ fabrique
    d'une Etape). Même interface publique que ExecuteurDistant
    (executer_blender / unreal / ffmpeg / csound) et même contrat de retour,
    pour que les étapes et l'affichage soient identiques — seule l'exécution
    change (locale au lieu de distante).
    """

    def __init__(self, config: ConfigWorker = None, dossier_rendus: str = "output/rendus_local"):
        self.config = config or ConfigWorker()
        self.dossier_rendus = dossier_rendus
        # Racine réelle sous laquelle TOUT rendu local doit rester : sert de
        # frontière pour le chaînage (échoue-fermé contre un chemin falsifié).
        self._racine = os.path.realpath(dossier_rendus)

    # Méthodes appelées par les étapes du pipeline (via Etape.methode)

    def executer_blender(self, chemin_script: str) -> dict:
        return self._executer("blender", chemin_script)

    def executer_unreal(self, chemin_script: str) -> dict:
        return self._executer("unreal", chemin_script)

    def executer_ffmpeg(self, chemin_script: str, poursuivre_dossier: str = "") -> dict:
        # Chaînage local : si le rendu Blender a produit sa vidéo dans un
        # dossier, l'export FFmpeg s'exécute dans CE dossier pour l'y retrouver.
        return self._executer("ffmpeg", chemin_script, poursuivre_dossier=poursuivre_dossier)

    def executer_csound(self, chemin_script: str) -> dict:
        # Rend la bande son (.csd) en audio : autonome, aucun chaînage.
        return self._executer("csound", chemin_script)

    def _chainage_autorise(self, dossier: str) -> bool:
        """Vrai seulement si `dossier` est un répertoire existant situé SOUS la
        racine des rendus locaux. Empêche un chemin falsifié (via l'état) de
        faire exécuter un rendu — et d'écrire ses fichiers — hors périmètre."""
        cible = os.path.realpath(dossier)
        if not os.path.isdir(cible):
            return False
        return cible == self._racine or cible.startswith(self._racine + os.sep)

    # ── Mécanique commune ────────────────────────────────────────────────────

    def _executer(self, outil: str, chemin_script: str, poursuivre_dossier: str = "") -> dict:
        # 1) Liste blanche stricte (échoue-fermé) — jamais un outil hors studio.
        if outil not in OUTILS_STUDIO:
            raise ErreurExecutionLocale(
                f"Outil « {outil} » hors de la liste blanche {OUTILS_STUDIO}.")

        # 2) Le script doit exister et ne pas être vide.
        if not chemin_script or not os.path.isfile(chemin_script):
            raise ErreurExecutionLocale(
                f"Script {outil} introuvable ({chemin_script or 'non généré'}) — "
                "lancez d'abord la production complète pour le générer.")
        with open(chemin_script, encoding="utf-8") as f:
            script = f.read()
        if not script.strip():
            raise ErreurExecutionLocale(f"Le script {outil} ({chemin_script}) est vide.")

        # 3) Le logiciel doit être installé sur CETTE machine.
        if not outils_disponibles(self.config).get(outil):
            raise ErreurExecutionLocale(
                f"« {outil} » n'est pas installé (ou introuvable) sur cette machine — "
                "impossible de lancer le rendu localement.")

        identifiant = uuid.uuid4().hex[:12]

        # 4) Dossier d'exécution : isolé, ou celui d'un rendu LOCAL précédent
        #    (chaînage FFmpeg après Blender). Échoue-fermé : on ne chaîne QUE
        #    vers un dossier situé SOUS notre racine de rendus locaux. Le chemin
        #    vient de l'état (world_state.json) — s'il a été falsifié pour
        #    pointer ailleurs sur le disque, on refuse (comme le worker distant
        #    qui ne chaîne que vers un identifiant de travail de son registre).
        if poursuivre_dossier:
            if not self._chainage_autorise(poursuivre_dossier):
                raise ErreurExecutionLocale(
                    f"Chaînage refusé : « {poursuivre_dossier} » n'est pas un "
                    f"dossier de rendu local sous {self.dossier_rendus} — "
                    "relancez le rendu Blender en local (--local) au préalable.")
            dossier = poursuivre_dossier
        else:
            dossier = os.path.join(self.dossier_rendus, outil, identifiant)
            os.makedirs(dossier, exist_ok=True)

        # 5) Écriture du script sous un nom assaini (anti-traversée).
        nom_script = nom_script_securise(outil, os.path.basename(chemin_script), identifiant)
        with open(os.path.join(dossier, nom_script), "w", encoding="utf-8") as f:
            f.write(script)
        avant = set(os.listdir(dossier))

        # 6) Commande construite par NOTRE code (liste d'arguments, sans shell).
        travail = Travail(identifiant, outil, nom_script, dossier)
        commande = construire_commande(self.config, travail)

        journal_path = os.path.join(dossier, f"journal_{identifiant}.log")
        debut = time.time()
        print(f"  ▶ Rendu {outil} lancé localement (travail {identifiant})...")
        try:
            with open(journal_path, "w", encoding="utf-8") as journal:
                journal.write("$ " + " ".join(commande) + "\n")
                journal.flush()
                resultat = subprocess.run(
                    commande, cwd=dossier, env=os.environ.copy(),
                    stdout=journal, stderr=subprocess.STDOUT,
                    timeout=self.config.delai_max, check=False)
            code_retour = resultat.returncode
        except subprocess.TimeoutExpired as e:
            raise ErreurExecutionLocale(
                f"Rendu {outil} interrompu : délai maximal dépassé "
                f"({self.config.delai_max}s) — journal : {journal_path}") from e
        except OSError as e:
            raise ErreurExecutionLocale(
                f"Impossible de lancer {outil} localement : {e}") from e
        duree = time.time() - debut

        # 7) Fichiers produits = nouveautés dans le dossier (hors script/journal).
        produits = [n for n in sorted(set(os.listdir(dossier)) - avant)
                    if n != os.path.basename(journal_path)]

        if code_retour != 0:
            raise ErreurExecutionLocale(
                f"Exécution {outil} en échec (code {code_retour}) — "
                f"journal : {journal_path}")

        return {
            "travail_id": identifiant,
            "code_retour": code_retour,
            "duree": duree,
            "journal_path": journal_path,
            "nb_fichiers": len(produits),
            # Toujours renseigné : sert aussi de dossier de chaînage pour FFmpeg.
            "dossier_fichiers": dossier,
        }
