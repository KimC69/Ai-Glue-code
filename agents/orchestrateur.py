"""
orchestrateur.py — Moteur d'exécution central du Studio IA.

Sépare le « quoi » du « comment » :
  - le QUOI : le pipeline déclaratif défini dans main.py (quelles étapes,
    quels agents, quelles entrées/sorties, quelle criticité) ;
  - le COMMENT : l'exécution (chargement des modules, instanciation,
    tentatives multiples, validation des sorties, sauvegarde de l'état,
    arrêt propre ou poursuite selon la criticité, bilan final).

Human-in-the-loop (mode --interactif) : les étapes marquées
`point_validation=True` s'arrêtent après exécution pour laisser
l'utilisateur valider, demander une révision (ses directives sont
réinjectées dans l'entrée de l'agent), ou arrêter proprement la
production (reprise possible avec --reprendre).

Ce module ne dépend d'aucune bibliothèque externe (stdlib uniquement) :
il peut être testé sans clé API ni dépendances LangChain.
"""

import importlib.util
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


def charger_module(filepath: str):
    """
    Charge un module Python depuis un chemin de fichier.
    Nécessaire pour les fichiers dont le nom commence par un chiffre
    (ex : 01_directeur_creatif.py), non importables directement.
    """
    module_name = os.path.basename(filepath).replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErreurEtapeCritique(Exception):
    """Levée quand une étape critique échoue : le pipeline doit s'arrêter."""

    def __init__(self, etape: "Etape", cause: Exception):
        self.etape = etape
        self.cause = cause
        super().__init__(f"Étape critique « {etape.nom} » en échec : {cause}")


class ArretUtilisateur(Exception):
    """Levée quand l'utilisateur choisit d'arrêter à un point de validation."""

    def __init__(self, etape: "Etape"):
        self.etape = etape
        super().__init__(f"Arrêt demandé par l'utilisateur après « {etape.nom} »")


@dataclass
class Etape:
    """
    Description déclarative d'une étape du pipeline.

    Champs :
        numero           : position de l'étape (1..N), pour l'affichage
        nom              : nom lisible (ex : "Agent 01 - Directeur Créatif")
        fichier          : nom du fichier de l'agent (ex : "01_directeur_creatif.py")
        classe           : nom de la classe à instancier dans ce module
        methode          : nom de la méthode métier à appeler
        preparer         : state -> dict des kwargs à passer à la méthode
        enregistrer      : (state, agent, resultat) -> None, écrit les sorties dans l'état
        cles_sortie      : clés d'état que l'étape doit remplir (validation + reprise)
        titre            : bannière affichée après succès (ex : "VISION VALIDÉE")
        afficher         : (agent, resultat) -> str, restitution après succès
        critique         : True = son échec arrête le pipeline ; False = on continue
        essais           : nombre total de tentatives de la méthode (retry LLM)
        conseil          : conseil spécifique affiché en cas d'échec
        point_validation : True = arrêt contrôlé après l'étape en mode --interactif
        champ_feedback   : nom du kwarg dans lequel réinjecter les directives
                           utilisateur lors d'une demande de révision
        purger           : clés d'état à réinitialiser si l'étape échoue
                           définitivement (évite d'afficher des données
                           obsolètes d'une production précédente)
        fabrique         : optionnel — fonction sans argument retournant un
                           « agent » déjà construit, au lieu de charger
                           fichier/classe (étapes non-LLM : exécution
                           distante, outils locaux...)
    """
    numero: int
    nom: str
    fichier: str
    classe: str
    methode: str
    preparer: Callable[[Any], dict]
    enregistrer: Callable[[Any, Any, Any], None]
    cles_sortie: tuple = ()
    titre: str = ""
    afficher: Optional[Callable[[Any, Any], str]] = None
    critique: bool = True
    essais: int = 2
    conseil: str = ""
    point_validation: bool = False
    champ_feedback: str = ""
    purger: tuple = ()
    fabrique: Optional[Callable[[], Any]] = None


class Orchestrateur:
    """
    Moteur central : planifie, exécute, réessaie, valide et journalise
    chaque étape du pipeline, avec points de validation humaine optionnels.

    `state` doit exposer : update(cle, valeur), get(cle, defaut),
    save() -> chemin, to_dict() -> dict (utilisé pour le rollback des
    révisions Human-in-the-loop). Les callbacks `enregistrer` doivent
    écrire un jeu de clés stable d'un tour à l'autre.

    Usage :
        orchestrateur = Orchestrateur(
            state=state,
            etapes=construire_pipeline(),
            dossier_agents="/chemin/vers/agents",
            surcharge_modele="gpt-4o",   # optionnel : force un modèle partout
            reprendre=True,              # optionnel : saute les étapes déjà faites
            interactif=True,             # optionnel : active le Human-in-the-loop
        )
        bilan = orchestrateur.executer()
    """

    def __init__(
        self,
        state: Any,
        etapes: list,
        dossier_agents: str,
        surcharge_modele: Optional[str] = None,
        reprendre: bool = False,
        interactif: bool = False,
    ):
        self.state = state
        self.etapes = etapes
        self.dossier_agents = dossier_agents
        self.surcharge_modele = surcharge_modele
        self.reprendre = reprendre
        self.interactif = interactif

    # ── Cycle de vie d'une étape ─────────────────────────────────────────────

    def _etape_deja_faite(self, etape: Etape) -> bool:
        """Une étape est « déjà faite » si toutes ses clés de sortie sont remplies."""
        if not etape.cles_sortie:
            return False
        return all(self.state.get(cle, "") != "" for cle in etape.cles_sortie)

    def _instancier(self, etape: Etape):
        """Construit l'« agent » : via fabrique si fournie, sinon module + classe."""
        if etape.fabrique is not None:
            return etape.fabrique()
        filepath = os.path.join(self.dossier_agents, etape.fichier)
        module = charger_module(filepath)
        classe = getattr(module, etape.classe)
        kwargs = {}
        if self.surcharge_modele:
            kwargs["model"] = self.surcharge_modele
        return classe(**kwargs)

    def _executer_methode(self, etape: Etape, agent: Any, feedbacks: list):
        """
        Appelle la méthode métier avec retry (les réponses LLM varient).
        Si des directives utilisateur existent (révisions Human-in-the-loop),
        elles sont réinjectées dans le kwarg désigné par `champ_feedback`.
        """
        kwargs = etape.preparer(self.state)
        if feedbacks and etape.champ_feedback:
            directives = "\n".join(f"- {f}" for f in feedbacks)
            bloc = ("\n\n[DIRECTIVES DU PRODUCTEUR — à respecter impérativement "
                    "dans cette nouvelle version]\n" + directives)
            base = str(kwargs.get(etape.champ_feedback, ""))
            kwargs[etape.champ_feedback] = base + bloc

        derniere_erreur: Optional[Exception] = None
        for tentative in range(1, etape.essais + 1):
            try:
                methode = getattr(agent, etape.methode)
                return methode(**kwargs)
            except Exception as e:
                derniere_erreur = e
                if tentative < etape.essais:
                    print(f"\n⚠️  [{etape.nom}] Tentative {tentative}/{etape.essais} "
                          f"échouée : {e}")
                    print("   Nouvel essai...")
        raise derniere_erreur

    def _valider_sorties(self, etape: Etape) -> None:
        """Vérifie qu'après enregistrement, toutes les clés attendues sont remplies."""
        manquantes = [c for c in etape.cles_sortie if self.state.get(c, "") == ""]
        if manquantes:
            raise ValueError(
                f"Sorties manquantes après exécution : {', '.join(manquantes)}"
            )

    def _executer_tour(self, etape: Etape, agent: Any, feedbacks: list):
        """
        Un tour complet d'exécution : méthode métier (avec retry) +
        enregistrement + validation des sorties + sauvegarde + affichage.
        """
        resultat = self._executer_methode(etape, agent, feedbacks)
        etape.enregistrer(self.state, agent, resultat)
        self._valider_sorties(etape)
        saved_path = self.state.save()

        if etape.titre:
            print(f"\n--- {etape.titre} ---")
        if etape.afficher is not None:
            print(etape.afficher(agent, resultat))
        print(f"\n[Système] : État sauvegardé → {saved_path}")
        return resultat

    def _gerer_echec(self, etape: Etape, e: Exception, bilan: dict) -> None:
        """Échec définitif d'une étape : arrêt si critique, poursuite sinon."""
        bilan["echouees"].append(etape.nom)

        # Réinitialise les sorties de l'étape pour ne jamais laisser traîner
        # des données obsolètes d'une production précédente.
        for cle in etape.purger:
            self.state.update(cle, "")

        if etape.critique:
            print(f"\n❌ [{etape.nom}] Échec : {e}")
            if etape.conseil:
                print(f"\n{etape.conseil}")
            print("\nConseils généraux :")
            print("  - Réessayez (les réponses LLM varient légèrement)")
            print("  - Vérifiez votre quota sur platform.openai.com/usage")
            print("  - Vérifiez que votre fichier .env contient une clé OPENAI_API_KEY valide")
            saved_path = self.state.save()
            print(f"\n💾 État partiel sauvegardé → {saved_path}")
            print(f"\n⛔ Le pipeline s'arrête ici car {etape.nom} est une étape critique.")
            print("   Corrigez le problème et relancez avec --reprendre : le travail")
            print("   déjà effectué est conservé.")
            raise ErreurEtapeCritique(etape, e)

        print(f"\n⚠️  [{etape.nom}] Échec : {e}")
        print("   Cette étape est optionnelle — le pipeline continue sans elle.")
        if etape.purger:
            self.state.save()
            print("   Sorties de cette étape réinitialisées (pas de données obsolètes).")

    # ── Human-in-the-loop ────────────────────────────────────────────────────

    def _demander_validation(self, etape: Etape) -> tuple:
        """
        Point de validation : interroge l'utilisateur.
        Retourne ("valider" | "reviser" | "arreter", directives).
        """
        print("\n" + "─" * 60)
        print(f"  🎬 POINT DE VALIDATION — {etape.nom}")
        print("─" * 60)
        print("  [Entrée] Valider et continuer la production")
        print("  [r]      Demander une révision (avec vos directives)")
        print("  [q]      Arrêter proprement (reprise possible : --reprendre)")

        while True:
            try:
                choix = input("\n  Votre choix : ").strip().lower()
            except EOFError:
                print("  (entrée non disponible — validation automatique)")
                return ("valider", "")

            if choix in ("", "o", "oui", "v", "valider"):
                return ("valider", "")
            if choix in ("q", "quitter", "stop", "arreter", "arrêter"):
                return ("arreter", "")
            if choix in ("r", "reviser", "réviser", "revision", "révision"):
                try:
                    directives = input(
                        "  Vos directives pour la révision "
                        "(ligne vide = simplement régénérer) :\n  > ").strip()
                except EOFError:
                    directives = ""
                return ("reviser", directives)
            print("  Choix non reconnu — répondez [Entrée], r ou q.")

    def _boucle_validation(self, etape: Etape, agent: Any, resultat: Any) -> tuple:
        """
        Boucle Human-in-the-loop après une étape réussie.
        Retourne (resultat_final, nombre_de_revisions).
        Lève ArretUtilisateur si l'utilisateur choisit d'arrêter.
        """
        feedbacks: list = []
        revisions = 0

        while True:
            decision, directives = self._demander_validation(etape)

            if decision == "valider":
                if revisions:
                    print(f"\n[Système] : {etape.nom} validé après "
                          f"{revisions} révision(s).")
                else:
                    print(f"\n[Système] : {etape.nom} validé — la production continue.")
                return resultat, revisions

            if decision == "arreter":
                saved_path = self.state.save()
                print(f"\n⏸️  Production arrêtée à votre demande après {etape.nom}.")
                print(f"💾 État sauvegardé → {saved_path}")
                print("   Reprenez plus tard avec : python main.py --reprendre --interactif")
                raise ArretUtilisateur(etape)

            # decision == "reviser"
            revisions += 1
            if directives:
                feedbacks.append(directives)
                print(f"\n[Système] : Révision {revisions} de {etape.nom} "
                      "avec vos directives...")
            else:
                print(f"\n[Système] : Nouvelle génération de {etape.nom} "
                      "(sans directives particulières)...")
            # Tour de révision transactionnel : si quoi que ce soit échoue
            # (appel LLM, enregistrement partiel, validation), l'état est
            # restauré à l'identique — le résultat validé précédent reste
            # la seule vérité.
            instantane = dict(self.state.to_dict())
            try:
                resultat = self._executer_tour(etape, agent, feedbacks)
            except Exception as e:
                for cle, valeur in instantane.items():
                    self.state.update(cle, valeur)
                self.state.save()
                print(f"\n⚠️  La révision a échoué : {e}")
                print("   Le résultat précédent a été restauré et reste en vigueur.")

    # ── Boucle principale ────────────────────────────────────────────────────

    def executer(self) -> dict:
        """
        Exécute toutes les étapes dans l'ordre.

        Returns:
            bilan : {
              "reussies":  [noms...],
              "ignorees":  [noms...],   # sautées via --reprendre
              "echouees":  [noms...],
              "resultats": {numero: resultat brut de la méthode},
              "durees":    {nom: secondes},
              "revisions": {nom: nb de révisions humaines demandées},
            }

        Raises:
            ErreurEtapeCritique si une étape critique échoue définitivement.
            ArretUtilisateur si l'utilisateur arrête à un point de validation.
        """
        bilan: dict = {
            "reussies": [], "ignorees": [], "echouees": [],
            "resultats": {}, "durees": {}, "revisions": {},
        }
        total = len(self.etapes)

        for etape in self.etapes:
            if self.reprendre and self._etape_deja_faite(etape):
                print(f"\n[Système] : Étape {etape.numero}/{total} — {etape.nom} : "
                      "déjà complétée, ignorée (--reprendre).")
                bilan["ignorees"].append(etape.nom)
                continue

            print(f"\n[Système] : Étape {etape.numero}/{total} — {etape.nom}...")
            debut = time.time()

            try:
                agent = self._instancier(etape)
                resultat = self._executer_tour(etape, agent, feedbacks=[])
            except Exception as e:
                self._gerer_echec(etape, e, bilan)
                continue

            # Point de validation Human-in-the-loop (peut lever ArretUtilisateur)
            revisions = 0
            if self.interactif and etape.point_validation:
                resultat, revisions = self._boucle_validation(etape, agent, resultat)

            duree = time.time() - debut
            bilan["reussies"].append(etape.nom)
            bilan["resultats"][etape.numero] = resultat
            bilan["durees"][etape.nom] = duree
            if revisions:
                bilan["revisions"][etape.nom] = revisions

        self._afficher_bilan(bilan)
        return bilan

    def _afficher_bilan(self, bilan: dict) -> None:
        """Affiche le bilan récapitulatif de l'exécution du pipeline."""
        print("\n" + "─" * 60)
        print("  ▶ BILAN DU PIPELINE")
        print("─" * 60)
        for nom in bilan["reussies"]:
            duree = bilan["durees"].get(nom)
            suffixe = f"  ({duree:.1f}s" if duree is not None else "  ("
            nb_revisions = bilan["revisions"].get(nom, 0)
            if nb_revisions:
                suffixe += f", {nb_revisions} révision(s)"
            suffixe += ")" if duree is not None or nb_revisions else ""
            suffixe = suffixe if suffixe != "  (" else ""
            print(f"  ✅ {nom}{suffixe}")
        for nom in bilan["ignorees"]:
            print(f"  ↷  {nom}  (déjà complétée)")
        for nom in bilan["echouees"]:
            print(f"  ⚠️  {nom}  (échec — étape optionnelle ignorée)")
        print("─" * 60)
