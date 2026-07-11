"""
orchestrateur.py — Moteur d'exécution central du Studio IA.

Sépare le « quoi » du « comment » :
  - le QUOI : le pipeline déclaratif défini dans main.py (quelles étapes,
    quels agents, quelles entrées/sorties, quelle criticité) ;
  - le COMMENT : l'exécution (chargement des modules, instanciation,
    tentatives multiples, validation des sorties, sauvegarde de l'état,
    arrêt propre ou poursuite selon la criticité, bilan final).

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


@dataclass
class Etape:
    """
    Description déclarative d'une étape du pipeline.

    Champs :
        numero       : position de l'étape (1..N), pour l'affichage
        nom          : nom lisible (ex : "Agent 01 - Directeur Créatif")
        fichier      : nom du fichier de l'agent (ex : "01_directeur_creatif.py")
        classe       : nom de la classe à instancier dans ce module
        methode      : nom de la méthode métier à appeler
        preparer     : state -> dict des kwargs à passer à la méthode
        enregistrer  : (state, agent, resultat) -> None, écrit les sorties dans l'état
        cles_sortie  : clés d'état que l'étape doit remplir (validation + reprise)
        titre        : bannière affichée après succès (ex : "VISION VALIDÉE")
        afficher     : (agent, resultat) -> str, texte de restitution après succès
        critique     : True = son échec arrête le pipeline ; False = on continue
        essais       : nombre total de tentatives de la méthode (retry LLM)
        conseil      : conseil spécifique affiché en cas d'échec
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


class Orchestrateur:
    """
    Moteur central : planifie, exécute, réessaie, valide et journalise
    chaque étape du pipeline.

    Usage :
        orchestrateur = Orchestrateur(
            state=state,
            etapes=construire_pipeline(),
            dossier_agents="/chemin/vers/agents",
            surcharge_modele="gpt-4o",   # optionnel : force un modèle partout
            reprendre=True,              # optionnel : saute les étapes déjà faites
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
    ):
        self.state = state
        self.etapes = etapes
        self.dossier_agents = dossier_agents
        self.surcharge_modele = surcharge_modele
        self.reprendre = reprendre

    # ── Cycle de vie d'une étape ─────────────────────────────────────────────

    def _etape_deja_faite(self, etape: Etape) -> bool:
        """Une étape est « déjà faite » si toutes ses clés de sortie sont remplies."""
        if not etape.cles_sortie:
            return False
        return all(self.state.get(cle, "") != "" for cle in etape.cles_sortie)

    def _instancier(self, etape: Etape):
        """Charge le module de l'agent et instancie sa classe."""
        filepath = os.path.join(self.dossier_agents, etape.fichier)
        module = charger_module(filepath)
        classe = getattr(module, etape.classe)
        kwargs = {}
        if self.surcharge_modele:
            kwargs["model"] = self.surcharge_modele
        return classe(**kwargs)

    def _executer_methode(self, etape: Etape, agent: Any):
        """Appelle la méthode métier avec retry (les réponses LLM varient)."""
        derniere_erreur: Optional[Exception] = None
        for tentative in range(1, etape.essais + 1):
            try:
                methode = getattr(agent, etape.methode)
                return methode(**etape.preparer(self.state))
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

    def _gerer_echec(self, etape: Etape, e: Exception, bilan: dict) -> None:
        """Échec définitif d'une étape : arrêt si critique, poursuite sinon."""
        bilan["echouees"].append(etape.nom)

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
            }

        Raises:
            ErreurEtapeCritique si une étape critique échoue définitivement.
        """
        bilan: dict = {
            "reussies": [], "ignorees": [], "echouees": [],
            "resultats": {}, "durees": {},
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
                resultat = self._executer_methode(etape, agent)
                etape.enregistrer(self.state, agent, resultat)
                self._valider_sorties(etape)
            except ErreurEtapeCritique:
                raise
            except Exception as e:
                self._gerer_echec(etape, e, bilan)
                continue

            duree = time.time() - debut
            saved_path = self.state.save()
            bilan["reussies"].append(etape.nom)
            bilan["resultats"][etape.numero] = resultat
            bilan["durees"][etape.nom] = duree

            if etape.titre:
                print(f"\n--- {etape.titre} ---")
            if etape.afficher is not None:
                print(etape.afficher(agent, resultat))
            print(f"\n[Système] : État sauvegardé → {saved_path}  ({duree:.1f}s)")

        self._afficher_bilan(bilan)
        return bilan

    def _afficher_bilan(self, bilan: dict) -> None:
        """Affiche le bilan récapitulatif de l'exécution du pipeline."""
        print("\n" + "─" * 60)
        print("  ▶ BILAN DU PIPELINE")
        print("─" * 60)
        for nom in bilan["reussies"]:
            duree = bilan["durees"].get(nom)
            suffixe = f"  ({duree:.1f}s)" if duree is not None else ""
            print(f"  ✅ {nom}{suffixe}")
        for nom in bilan["ignorees"]:
            print(f"  ↷  {nom}  (déjà complétée)")
        for nom in bilan["echouees"]:
            print(f"  ⚠️  {nom}  (échec — étape optionnelle ignorée)")
        print("─" * 60)
