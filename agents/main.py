"""
main.py — Point d'entrée du Studio IA Cinématographique.

Architecture :
  Input utilisateur (--idea ou saisie interactive)
       │
       ▼
  [Orchestrateur central]  → planifie, exécute, réessaie, valide, journalise
       │  (pipeline déclaratif : chaque étape décrit son agent, ses
       │   entrées/sorties, sa criticité et son nombre de tentatives)
       ▼
  Agent 01 : DirecteurCreatif        → vision_globale, genre, ton       [critique]
  Agent 02 : ArchitecteNarratif      → synopsis, actes, scènes clés     [critique]
  Agent 03 : Scenariste              → dialogues, personnages           [critique]
  Agent 04 : DirecteurArtistique     → script Blender (.py)             [critique]
  Agent 05 : DirecteurTechnique      → script Unreal (.sh)              [critique]
  Agent 06 : SuperviseurPostProd     → audit + outils conditionnels     [optionnel]
  Agent 07 : ExporteurMultiFormat    → script FFmpeg multi-format       [optionnel]
       │
       ▼
  output/ (scripts, notes, world_state.json)

Usage :
    cd agents/
    python main.py                                     # saisie interactive
    python main.py --idea "Un détective robot dans une ville néon"
    python main.py --model gpt-4o                      # force un modèle partout
    python main.py --reprendre                         # reprend après un échec
    python main.py --interactif                        # validation humaine (HITL)
    python main.py --reprendre --worker http://IP:8765 # rendu sur machine distante
"""

import argparse
import getpass
import os
import re
import sys
import uuid

from dotenv import load_dotenv

from shared_state import WorldState
from orchestrateur import Etape, Orchestrateur, ErreurEtapeCritique, ArretUtilisateur
from client_worker import ClientWorker, ExecuteurDistant, ErreurWorker
from executeur_local import ExecuteurLocal
from worker_distant import ConfigWorker, outils_disponibles
from journal_production import JournalProduction
from securite import Securite, ErreurSecurite, ROLES_VALIDES, ROLE_DEFAUT
import utils_headless

# Chargement des variables d'environnement (.env)
load_dotenv()

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(AGENTS_DIR, "output")


# ── Enregistrement des sorties de chaque agent dans WorldState ──────────────
# Chaque callback reçoit (state, agent, resultat) et écrit les clés d'état.

def _enregistrer_vision(state, agent, vision):
    state.update("vision_globale", vision)
    state.update("genre", agent.dernier_genre)
    state.update("tone", agent.dernier_ton)


def _enregistrer_structure(state, agent, structure):
    state.update("synopsis",   structure["synopsis"])
    state.update("acts",       structure["acts"])
    state.update("key_scenes", structure["key_scenes"])


def _enregistrer_scenario(state, agent, scenario):
    state.update("character_sheet",    scenario["character_sheet"])
    state.update("screenplay_excerpt", scenario["screenplay_excerpt"])


def _enregistrer_blender(state, agent, blender):
    state.update("visual_style",       blender["visual_style"])
    state.update("blender_script",     blender["blender_script"])
    state.update("blender_saved_path", blender.get("saved_path", ""))


def _enregistrer_unreal(state, agent, unreal):
    state.update("technical_notes",   unreal["technical_notes"])
    state.update("unreal_script",     unreal["unreal_script"])
    state.update("unreal_saved_path", unreal.get("saved_path", ""))


_CLES_AUDIT = (
    "coherence_score", "issues",
    "needs_gimp_retouching", "gimp_script",
    "needs_video_editing", "video_editing_notes",
    "needs_inkscape", "inkscape_notes",
    "needs_darktable", "darktable_notes",
    "needs_krita", "krita_script",
    "needs_obs", "obs_notes",
)


def _enregistrer_audit(state, agent, audit):
    for cle in _CLES_AUDIT:
        state.update(cle, audit[cle])
    state.update("gimp_saved_path",  audit.get("gimp_saved_path", ""))
    state.update("krita_saved_path", audit.get("krita_saved_path", ""))


def _enregistrer_export(state, agent, export):
    state.update("export_formats",    export["formats"])
    state.update("ffmpeg_script",     export["ffmpeg_script"])
    state.update("export_saved_path", export.get("saved_path", ""))


def _enregistrer_son(state, agent, son):
    state.update("mood_musical",     son["mood_musical"])
    state.update("csound_script",    son["csound_script"])
    state.update("sound_saved_path", son.get("saved_path", ""))


# ── Définition déclarative du pipeline ───────────────────────────────────────

def construire_pipeline(executeur_distant=None, outils_worker=None,
                        executeur_local=None, outils_local=None) -> list:
    """
    Décrit les étapes du studio. L'Orchestrateur se charge du reste.

    Si un exécuteur distant est fourni (--worker), les étapes de rendu
    (exécution des scripts Blender / Unreal / FFmpeg sur la machine de
    rendu) sont ajoutées à la suite — uniquement pour les outils que le
    worker déclare disponibles.

    Si un exécuteur local est fourni (--local), ces mêmes rendus sont
    exécutés AUTOMATIQUEMENT sur cette machine — pour les logiciels
    installés localement. Les deux modes sont mutuellement exclusifs.
    """
    etapes = [
        Etape(
            numero=1, nom="Agent 01 - Directeur Créatif",
            fichier="01_directeur_creatif.py",
            classe="DirecteurCreatif", methode="generer_vision",
            preparer=lambda s: {"idea": s.get("idea")},
            enregistrer=_enregistrer_vision,
            cles_sortie=("vision_globale", "genre", "tone"),
            titre="VISION VALIDÉE ET ENREGISTRÉE",
            afficher=lambda agent, vision: str(vision),
            critique=True,
            point_validation=True, champ_feedback="idea",
        ),
        Etape(
            numero=2, nom="Agent 02 - Architecte Narratif",
            fichier="02_architecte_narratif.py",
            classe="ArchitecteNarratif", methode="construire_structure",
            preparer=lambda s: {
                "vision_globale": s.get("vision_globale"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_structure,
            cles_sortie=("synopsis", "acts", "key_scenes"),
            titre="STRUCTURE NARRATIVE VALIDÉE ET ENREGISTRÉE",
            afficher=lambda agent, r: agent.afficher_structure(),
            critique=True,
            point_validation=True, champ_feedback="vision_globale",
        ),
        Etape(
            numero=3, nom="Agent 03 - Scénariste",
            fichier="03_scenariste.py",
            classe="Scenariste", methode="ecrire_scenario",
            preparer=lambda s: {
                "synopsis": s.get("synopsis"),
                "acts": s.get("acts"),
                "key_scenes": s.get("key_scenes"),
            },
            enregistrer=_enregistrer_scenario,
            cles_sortie=("character_sheet", "screenplay_excerpt"),
            titre="SCÉNARIO VALIDÉ ET ENREGISTRÉ",
            afficher=lambda agent, r: agent.afficher_scenario(),
            critique=True,
            point_validation=True, champ_feedback="synopsis",
        ),
        Etape(
            numero=4, nom="Agent 04 - Directeur Artistique",
            fichier="04_directeur_artistique.py",
            classe="DirecteurArtistique", methode="creer_scene_blender",
            preparer=lambda s: {
                "screenplay_excerpt": s.get("screenplay_excerpt"),
                "character_sheet": s.get("character_sheet"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_blender,
            cles_sortie=("visual_style", "blender_script", "blender_saved_path"),
            titre="SCÈNE BLENDER GÉNÉRÉE ET ENREGISTRÉE",
            afficher=lambda agent, r: agent.afficher_resultat(),
            critique=True,
            conseil="Conseil : la génération de code Blender bénéficie du modèle gpt-4o.",
            point_validation=True, champ_feedback="screenplay_excerpt",
        ),
        Etape(
            numero=5, nom="Agent 05 - Directeur Technique",
            fichier="05_directeur_technique.py",
            classe="DirecteurTechnique", methode="creer_setup_unreal",
            preparer=lambda s: {
                "visual_style": s.get("visual_style"),
                "blender_script": s.get("blender_script"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_unreal,
            cles_sortie=("technical_notes", "unreal_script", "unreal_saved_path"),
            titre="SETUP UNREAL ENGINE GÉNÉRÉ ET ENREGISTRÉ",
            afficher=lambda agent, r: agent.afficher_resultat(),
            critique=True,
            conseil="Conseil : la génération de code Unreal bénéficie du modèle gpt-4o.",
            point_validation=True, champ_feedback="visual_style",
        ),
        Etape(
            numero=6, nom="Agent 06 - Superviseur Post-Production",
            fichier="06_superviseur_post_production.py",
            classe="SuperviseurPostProduction", methode="analyser_conformite",
            preparer=lambda s: {
                "visual_style": s.get("visual_style"),
                "technical_notes": s.get("technical_notes"),
                "blender_script": s.get("blender_script"),
                "unreal_script": s.get("unreal_script"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_audit,
            cles_sortie=("coherence_score",),
            titre="AUDIT DE CONFORMITÉ",
            afficher=lambda agent, r: agent.afficher_rapport(),
            critique=False,   # l'audit ne bloque jamais la production
            purger=_CLES_AUDIT + ("gimp_saved_path", "krita_saved_path"),
        ),
        Etape(
            numero=7, nom="Agent 07 - Exporteur Multi-Format",
            fichier="07_exporteur_multi_format.py",
            classe="ExporteurMultiFormat", methode="generer_exports",
            preparer=lambda s: {
                "vision_globale": s.get("vision_globale"),
                "visual_style": s.get("visual_style"),
                "technical_notes": s.get("technical_notes"),
                "blender_script": s.get("blender_script"),
                "unreal_script": s.get("unreal_script"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_export,
            cles_sortie=("ffmpeg_script", "export_saved_path"),
            titre="EXPORTS MULTI-FORMAT GÉNÉRÉS",
            afficher=lambda agent, r: agent.afficher_rapport(),
            critique=False,   # l'export ne bloque jamais la production
            purger=("export_formats", "ffmpeg_script", "export_saved_path"),
        ),
        Etape(
            numero=8, nom="Agent 08 - Ingénieur du Son",
            fichier="08_ingenieur_son.py",
            classe="IngenieurSon", methode="composer_bande_son",
            preparer=lambda s: {
                "vision_globale": s.get("vision_globale"),
                "visual_style": s.get("visual_style"),
                "key_scenes": s.get("key_scenes"),
                "genre": s.get("genre"),
                "tone": s.get("tone"),
            },
            enregistrer=_enregistrer_son,
            cles_sortie=("csound_script", "sound_saved_path"),
            titre="BANDE SON COMPOSÉE (Csound)",
            afficher=lambda agent, r: agent.afficher_rapport(),
            critique=False,   # la bande son ne bloque jamais la production
            conseil="Conseil : la composition d'une partition Csound bénéficie du modèle gpt-4o.",
            purger=("mood_musical", "csound_script", "sound_saved_path"),
        ),
    ]

    if executeur_distant is not None:
        etapes += etapes_rendu_distant(executeur_distant, outils_worker or {},
                                       prochain_numero=len(etapes) + 1)
    if executeur_local is not None:
        etapes += etapes_rendu_local(executeur_local, outils_local or {},
                                     prochain_numero=len(etapes) + 1)
    return etapes


# ── Étapes d'exécution distante (worker de rendu) ────────────────────────────

def _enregistrer_rendu(prefixe: str):
    """Callback d'enregistrement d'une étape de rendu distant."""
    def _callback(state, agent, resultat):
        state.update(f"rendu_{prefixe}_statut", "ok")
        state.update(f"rendu_{prefixe}_travail_id", resultat["travail_id"])
        state.update(f"rendu_{prefixe}_journal", resultat["journal_path"])
        state.update(f"rendu_{prefixe}_fichiers", resultat["dossier_fichiers"])
    return _callback


def _purger_rendu(prefixe: str) -> tuple:
    return (f"rendu_{prefixe}_statut", f"rendu_{prefixe}_travail_id",
            f"rendu_{prefixe}_journal", f"rendu_{prefixe}_fichiers")


def _afficher_rendu(agent, resultat) -> str:
    lignes = [f"  Durée sur le worker : {resultat['duree']:.0f}s",
              f"  Journal rapatrié    : {resultat['journal_path']}"]
    if resultat["nb_fichiers"]:
        lignes.append(f"  Fichiers produits   : {resultat['nb_fichiers']} "
                      f"→ {resultat['dossier_fichiers']}")
    else:
        lignes.append("  Fichiers produits   : aucun (détail dans le journal)")
    return "\n".join(lignes)


def etapes_rendu_distant(executeur, outils: dict, prochain_numero: int) -> list:
    """
    Étapes 8+ : exécution des scripts générés, sur le worker distant.
    Toutes optionnelles (un rendu raté n'invalide pas la production) et
    en un seul essai (relancer un rendu coûteux se décide à la main,
    via --reprendre).
    """
    etapes = []
    conseil = ("Conseil : le journal complet du worker est rapatrié dans "
               "agents/output/rendus/ — il contient l'erreur exacte.")

    def indisponible(outil):
        print(f"[Avertissement] : « {outil} » indisponible sur le worker — "
              "étape de rendu distante non planifiée.")

    if outils.get("blender"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Rendu Blender (worker distant)",
            fichier="", classe="", methode="executer_blender",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("blender_saved_path")},
            enregistrer=_enregistrer_rendu("blender"),
            cles_sortie=("rendu_blender_statut",),
            titre="RENDU BLENDER EXÉCUTÉ SUR LE WORKER",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("blender"),
        ))
    else:
        indisponible("blender")

    if outils.get("unreal"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Setup Unreal (worker distant)",
            fichier="", classe="", methode="executer_unreal",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("unreal_saved_path")},
            enregistrer=_enregistrer_rendu("unreal"),
            cles_sortie=("rendu_unreal_statut",),
            titre="SETUP UNREAL EXÉCUTÉ SUR LE WORKER",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("unreal"),
        ))
    else:
        indisponible("unreal")

    if outils.get("ffmpeg"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Exports FFmpeg (worker distant)",
            fichier="", classe="", methode="executer_ffmpeg",
            fabrique=lambda: executeur,
            # Chaînage : l'export s'exécute dans le dossier du rendu Blender
            # (si effectué), où la vidéo master est disponible.
            preparer=lambda s: {
                "chemin_script": s.get("export_saved_path"),
                "poursuivre_id": s.get("rendu_blender_travail_id", ""),
            },
            enregistrer=_enregistrer_rendu("ffmpeg"),
            cles_sortie=("rendu_ffmpeg_statut",),
            titre="EXPORTS FFMPEG EXÉCUTÉS SUR LE WORKER",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("ffmpeg"),
        ))
    else:
        indisponible("ffmpeg")

    if outils.get("csound"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Rendu bande son (worker distant)",
            fichier="", classe="", methode="executer_csound",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("sound_saved_path")},
            enregistrer=_enregistrer_rendu("csound"),
            cles_sortie=("rendu_csound_statut",),
            titre="BANDE SON RENDUE SUR LE WORKER",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("csound"),
        ))
    else:
        indisponible("csound")

    return etapes


# ── Étapes d'exécution locale automatique (--local) ──────────────────────────

def etapes_rendu_local(executeur, outils: dict, prochain_numero: int) -> list:
    """
    Étapes 8+ : exécution AUTOMATIQUE des scripts générés, sur CETTE machine.
    Le studio lance lui-même les logiciels (headless) et produit les fichiers,
    sans intervention. Mêmes garanties que le rendu distant : toutes
    optionnelles (critique=False) et en un seul essai.
    """
    etapes = []
    conseil = ("Conseil : le journal complet est écrit dans "
               "agents/output/rendus_local/ — il contient l'erreur exacte.")

    def indisponible(outil):
        print(f"[Avertissement] : « {outil} » n'est pas installé localement — "
              "étape de rendu locale non planifiée.")

    if outils.get("blender"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Rendu Blender (local)",
            fichier="", classe="", methode="executer_blender",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("blender_saved_path")},
            enregistrer=_enregistrer_rendu("blender"),
            cles_sortie=("rendu_blender_statut",),
            titre="RENDU BLENDER EXÉCUTÉ EN LOCAL",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("blender"),
        ))
    else:
        indisponible("blender")

    if outils.get("unreal"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Setup Unreal (local)",
            fichier="", classe="", methode="executer_unreal",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("unreal_saved_path")},
            enregistrer=_enregistrer_rendu("unreal"),
            cles_sortie=("rendu_unreal_statut",),
            titre="SETUP UNREAL EXÉCUTÉ EN LOCAL",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("unreal"),
        ))
    else:
        indisponible("unreal")

    if outils.get("ffmpeg"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Exports FFmpeg (local)",
            fichier="", classe="", methode="executer_ffmpeg",
            fabrique=lambda: executeur,
            # Chaînage : l'export s'exécute dans le dossier du rendu Blender
            # local (si effectué), où la vidéo master est disponible.
            preparer=lambda s: {
                "chemin_script": s.get("export_saved_path"),
                "poursuivre_dossier": s.get("rendu_blender_fichiers", ""),
            },
            enregistrer=_enregistrer_rendu("ffmpeg"),
            cles_sortie=("rendu_ffmpeg_statut",),
            titre="EXPORTS FFMPEG EXÉCUTÉS EN LOCAL",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("ffmpeg"),
        ))
    else:
        indisponible("ffmpeg")

    if outils.get("csound"):
        etapes.append(Etape(
            numero=prochain_numero + len(etapes),
            nom="Rendu bande son (local)",
            fichier="", classe="", methode="executer_csound",
            fabrique=lambda: executeur,
            preparer=lambda s: {"chemin_script": s.get("sound_saved_path")},
            enregistrer=_enregistrer_rendu("csound"),
            cles_sortie=("rendu_csound_statut",),
            titre="BANDE SON RENDUE EN LOCAL",
            afficher=_afficher_rendu,
            critique=False, essais=1, conseil=conseil,
            purger=_purger_rendu("csound"),
        ))
    else:
        indisponible("csound")

    return etapes


# ── Récapitulatif final et commandes headless ────────────────────────────────

def _ecrire_notes_si_necessaire(actif, contenu: str, nom_fichier: str) -> str:
    """
    Écrit les notes d'un outil « instructions » (pas de script direct) dans un
    fichier, uniquement si l'Agent 06 l'a jugé nécessaire.
    Retourne le chemin, ou '' si non nécessaire.
    """
    if not actif or not contenu:
        return ""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, nom_fichier)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(contenu)
    return filepath


def _afficher_recap_final(state: WorldState, bilan: dict) -> None:
    """Bannière de fin + commandes headless prêtes à l'emploi."""
    print("\n" + "=" * 45)
    print("  🎬 PIPELINE COMPLET — PRODUCTION TERMINÉE")
    print("=" * 45)
    print(f"  État complet     : {WorldState.SAVE_PATH}")
    print(f"  Scripts générés  : agents/output/")
    print(f"  Étapes réussies  : {len(bilan['reussies'])}"
          + (f" | ignorées (reprise) : {len(bilan['ignorees'])}" if bilan["ignorees"] else "")
          + (f" | échouées (optionnelles) : {len(bilan['echouees'])}" if bilan["echouees"] else ""))
    print("\n  ✅ Bonne production !")

    # Notes des outils « instructions » (pas de mode headless one-shot)
    montage_notes_path = _ecrire_notes_si_necessaire(
        state.get("needs_video_editing"), state.get("video_editing_notes"), "notes_montage.txt")
    inkscape_notes_path = _ecrire_notes_si_necessaire(
        state.get("needs_inkscape"), state.get("inkscape_notes"), "notes_inkscape.txt")
    darktable_notes_path = _ecrire_notes_si_necessaire(
        state.get("needs_darktable"), state.get("darktable_notes"), "notes_darktable.txt")
    obs_notes_path = _ecrire_notes_si_necessaire(
        state.get("needs_obs"), state.get("obs_notes"), "notes_obs.txt")

    # Rendus effectués sur le worker distant (--worker)
    rendus = [(prefixe, label) for prefixe, label in
              (("blender", "Rendu Blender"), ("unreal", "Setup Unreal"),
               ("ffmpeg", "Exports FFmpeg"), ("csound", "Rendu bande son"))
              if state.get(f"rendu_{prefixe}_statut") == "ok"]
    if rendus:
        print("\n  ▶ RENDUS EXÉCUTÉS AUTOMATIQUEMENT (worker distant ou local) :")
        for prefixe, label in rendus:
            print(f"    ✅ {label}")
            print(f"       Journal  : {state.get(f'rendu_{prefixe}_journal')}")
            dossier_fichiers = state.get(f"rendu_{prefixe}_fichiers")
            if dossier_fichiers:
                print(f"       Fichiers : {dossier_fichiers}")

    blender_path = state.get("blender_saved_path", "")
    unreal_path = state.get("unreal_saved_path", "")

    if blender_path and unreal_path:
        utils_headless.afficher_commandes_headless(
            blender_path=blender_path,
            unreal_path=unreal_path,
            gimp_path=state.get("gimp_saved_path", "") if state.get("needs_gimp_retouching") else "",
            montage_notes_path=montage_notes_path,
            inkscape_notes_path=inkscape_notes_path,
            darktable_notes_path=darktable_notes_path,
            krita_path=state.get("krita_saved_path", "") if state.get("needs_krita") else "",
            obs_notes_path=obs_notes_path,
            export_script_path=state.get("export_saved_path", ""),
            sound_path=state.get("sound_saved_path", ""),
        )
    else:
        print("\n  ℹ️  Chemins des scripts Blender/Unreal absents de l'état —")
        print("     commandes headless non affichées. Relancez le pipeline complet.")
    print()


# ── Journal / historique ──────────────────────────────────────────────────────

def _mode_execution(args) -> str:
    """Résumé du mode d'exécution, tracé dans le journal (ex : « interactif+worker »)."""
    modes = []
    if args.interactif:
        modes.append("interactif")
    if args.worker:
        modes.append("worker")
    if args.local:
        modes.append("local")
    if args.reprendre:
        modes.append("reprise")
    return "+".join(modes) or "standard"


def _afficher_historique(limite: int = 20) -> None:
    """Affiche les dernières productions enregistrées dans output/studio.db."""
    journal = JournalProduction()          # ouverture en lecture (aucune production créée)
    productions = journal.lister_productions(limite=limite)
    journal.fermer()

    print("\n" + "═" * 68)
    print("  🗂  HISTORIQUE DES PRODUCTIONS")
    print("═" * 68)
    if not productions:
        print("  (aucune production enregistrée pour l'instant)")
        print("═" * 68 + "\n")
        return

    for p in productions:
        idee = (p["idee"] or "").strip().replace("\n", " ")
        if len(idee) > 52:
            idee = idee[:49] + "..."
        symbole = {"terminee": "✅", "echec": "❌",
                   "arretee": "⏸️ ", "en_cours": "⏳"}.get(p["statut"], "•")
        print(f"\n  {symbole} {p['id']}  ({p['statut']})")
        print(f"     Idée    : {idee}")
        print(f"     Étapes  : {p['etapes_reussies']} réussie(s)"
              f"   |   Modèle : {p['modele'] or '—'}   |   Mode : {p['mode'] or '—'}")
        print(f"     Démarrée: {p['demarree_le']}"
              + (f"   →   {p['terminee_le']}" if p["terminee_le"] else ""))
    print("\n" + "═" * 68)
    print(f"  Détail d'une production : ouvrez output/journaux/<id>.jsonl")
    print("═" * 68 + "\n")


# ── Sécurité : gestion des comptes (mode administration) ───────────────────────

def _saisir_mot_de_passe(confirmer: bool = False) -> str:
    """Demande un mot de passe sans l'afficher (getpass). Si confirmer=True,
    le redemande et vérifie la correspondance."""
    mdp = getpass.getpass("Mot de passe : ")
    if confirmer and mdp != getpass.getpass("Confirmez le mot de passe : "):
        print("[Erreur] : les deux mots de passe ne correspondent pas.")
        sys.exit(1)
    return mdp


def _gerer_securite(args) -> bool:
    """Traite une commande de gestion des comptes (création, liste, etc.) puis
    retourne True. Retourne False si aucune commande de sécurité n'est demandée.

    Ces commandes s'exécutent puis quittent, sans lancer de production — comme
    --historique. Les mots de passe sont TOUJOURS saisis au clavier (getpass),
    jamais passés en argument de ligne de commande (sinon ils resteraient dans
    l'historique du shell et la liste des processus)."""
    commandes = (args.creer_utilisateur or args.lister_utilisateurs
                 or args.changer_mdp or args.supprimer_utilisateur
                 or args.connexion or args.definir_role)
    if not commandes:
        return False

    try:
        securite = Securite()
    except ErreurSecurite as e:
        print(f"[Erreur sécurité] : {e}")
        sys.exit(1)

    try:
        if args.creer_utilisateur:
            role = args.role or ROLE_DEFAUT
            print(f"Création de l'utilisateur {args.creer_utilisateur!r} "
                  f"(rôle : {role})")
            mdp = _saisir_mot_de_passe(confirmer=True)
            securite.creer_utilisateur(args.creer_utilisateur, mdp, role)
            print(f"[OK] Utilisateur {args.creer_utilisateur!r} créé.")

        elif args.changer_mdp:
            print(f"Changement du mot de passe de {args.changer_mdp!r}")
            mdp = _saisir_mot_de_passe(confirmer=True)
            securite.changer_mot_de_passe(args.changer_mdp, mdp)
            print(f"[OK] Mot de passe de {args.changer_mdp!r} mis à jour.")

        elif args.definir_role:
            if not args.role:
                print("[Erreur] : --definir-role NOM nécessite aussi --role RÔLE.")
                sys.exit(1)
            securite.definir_role(args.definir_role, args.role)
            print(f"[OK] {args.definir_role!r} a désormais le rôle {args.role!r}.")

        elif args.supprimer_utilisateur:
            securite.supprimer_utilisateur(args.supprimer_utilisateur)
            print(f"[OK] Utilisateur {args.supprimer_utilisateur!r} supprimé.")

        elif args.connexion:
            print(f"Connexion de {args.connexion!r}")
            mdp = _saisir_mot_de_passe()
            jeton = securite.authentifier(args.connexion, mdp)
            print("[OK] Connexion réussie. Jeton de session "
                  "(à transmettre à l'API à l'étape 7) :\n")
            print(f"  {jeton}\n")
            print("Ce jeton expire automatiquement ; ne le partagez pas.")

        elif args.lister_utilisateurs:
            _afficher_utilisateurs(securite.lister_utilisateurs())

    except ErreurSecurite as e:
        print(f"[Erreur sécurité] : {e}")
        securite.fermer()
        sys.exit(1)

    securite.fermer()
    return True


def _afficher_utilisateurs(utilisateurs: list) -> None:
    print("\n" + "═" * 60)
    print("  👤  UTILISATEURS")
    print("═" * 60)
    if not utilisateurs:
        print("  (aucun utilisateur — créez-en un avec --creer-utilisateur NOM)")
        print("═" * 60 + "\n")
        return
    for u in utilisateurs:
        etat = "actif" if u["actif"] else "désactivé"
        print(f"  • {u['nom']:<20} rôle : {u['role']:<12} ({etat})")
        print(f"    créé le {u['cree_le']}")
    print("═" * 60 + "\n")


# ── Point d'entrée ────────────────────────────────────────────────────────────

def lancer_studio(argv=None):
    parser = argparse.ArgumentParser(
        description="Studio IA Cinématographique — pipeline multi-agents "
                    "(vision → scénario → Blender → Unreal → post-prod → exports).")
    parser.add_argument("--idea", type=str, default="",
                        help="Idée de film (sinon : saisie interactive)")
    parser.add_argument("--model", type=str, default="",
                        help="Force un modèle OpenAI pour TOUS les agents (ex : gpt-4o)")
    parser.add_argument("--reprendre", action="store_true",
                        help="Reprend une production interrompue : saute les étapes "
                             "dont les résultats sont déjà dans world_state.json")
    parser.add_argument("--interactif", action="store_true",
                        help="Active les points de validation Human-in-the-loop : après "
                             "chaque étape créative (Agents 01 à 05), validez le résultat, "
                             "demandez une révision avec vos directives, ou arrêtez proprement")
    parser.add_argument("--worker", type=str, default="",
                        help="URL du worker distant (ex : http://192.168.1.50:8765) — "
                             "exécute les scripts Blender/Unreal/FFmpeg sur la machine "
                             "de rendu après leur génération (voir worker_distant.py)")
    parser.add_argument("--worker-jeton", type=str, default="",
                        help="Jeton d'accès au worker (sinon : variable WORKER_JETON, "
                             "affiché par le worker à son démarrage)")
    parser.add_argument("--local", action="store_true",
                        help="Lance les rendus AUTOMATIQUEMENT sur cette machine "
                             "(headless), pour les logiciels installés localement : "
                             "Csound (bande son), et Blender/FFmpeg si présents. "
                             "⚠️ exécute des scripts générés par IA sur votre machine "
                             "— incompatible avec --worker.")
    parser.add_argument("--historique", action="store_true",
                        help="Affiche l'historique des productions (base output/studio.db) "
                             "puis quitte, sans rien lancer")
    parser.add_argument("--production-id", type=str, default="",
                        help="Impose l'identifiant de la production (12 caractères "
                             "hexadécimaux). Utilisé par l'API (étape 7) : elle génère "
                             "l'identifiant, le renvoie au client, puis lance le pipeline "
                             "avec cette option pour que le suivi retrouve la production")

    # ── Gestion des comptes (authentification, étape 6) ──────────────────────
    # Ces commandes s'exécutent puis quittent, sans lancer de production. Les
    # mots de passe sont saisis au clavier, jamais en argument.
    securite_grp = parser.add_argument_group(
        "Comptes et sécurité",
        "Gestion des utilisateurs qui pourront commander le studio via l'API "
        "(étape 7) et les interfaces à venir. Base : output/securite.db.")
    securite_grp.add_argument("--creer-utilisateur", metavar="NOM", default="",
                              help="Crée un compte (mot de passe demandé au clavier) ; "
                                   "combiner avec --role")
    securite_grp.add_argument("--role", default="",
                              choices=sorted(ROLES_VALIDES),
                              help=f"Rôle du compte (défaut : {ROLE_DEFAUT}) — "
                                   "utilisé avec --creer-utilisateur ou --definir-role")
    securite_grp.add_argument("--definir-role", metavar="NOM", default="",
                              help="Change le rôle d'un utilisateur existant "
                                   "(nécessite --role)")
    securite_grp.add_argument("--changer-mdp", metavar="NOM", default="",
                              help="Change le mot de passe d'un utilisateur")
    securite_grp.add_argument("--supprimer-utilisateur", metavar="NOM", default="",
                              help="Supprime un compte")
    securite_grp.add_argument("--lister-utilisateurs", action="store_true",
                              help="Affiche la liste des comptes puis quitte")
    securite_grp.add_argument("--connexion", metavar="NOM", default="",
                              help="Vérifie un mot de passe et affiche un jeton de "
                                   "session (à utiliser par l'API à l'étape 7)")
    args = parser.parse_args(argv)

    # ── Historique : lecture seule, aucune production lancée ──────────────────
    if args.historique:
        _afficher_historique()
        return

    # ── Commandes de gestion des comptes : s'exécutent puis quittent ─────────
    if _gerer_securite(args):
        return

    # ── Validation de --production-id (imposé par l'API) ─────────────────────
    if args.production_id:
        if args.reprendre:
            print("[Erreur] : --production-id et --reprendre sont incompatibles.")
            print("           --reprendre réutilise l'identifiant de la production en")
            print("           cours ; --production-id en impose un nouveau.")
            sys.exit(1)
        if not re.fullmatch(r"[0-9a-f]{12}", args.production_id):
            print("[Erreur] : --production-id doit comporter 12 caractères "
                  "hexadécimaux (0-9, a-f).")
            sys.exit(1)

    if args.interactif and not sys.stdin.isatty():
        print("[Avertissement] : --interactif sans terminal interactif — "
              "les validations seront acceptées automatiquement.")

    # ── Rendu local OU distant, jamais les deux ──────────────────────────────
    if args.local and args.worker:
        print("[Erreur] : --local et --worker sont incompatibles (rendu local "
              "OU sur machine distante, pas les deux).")
        sys.exit(1)

    # ── 0. Connexion au worker distant (si demandé) ──────────────────────────
    # Vérifiée AVANT de lancer le pipeline : inutile de consommer des appels
    # LLM si la machine de rendu est injoignable.
    executeur_distant = None
    outils_worker: dict = {}
    if args.worker:
        jeton = args.worker_jeton.strip() or os.getenv("WORKER_JETON", "").strip()
        if not jeton:
            print("[Erreur] : --worker nécessite un jeton d'accès : option --worker-jeton")
            print("           ou variable WORKER_JETON (le worker l'affiche à son démarrage).")
            sys.exit(1)
        client = ClientWorker(args.worker.strip(), jeton)
        try:
            sante = client.sante()
        except ErreurWorker as e:
            print(f"[Erreur] : {e}")
            print("           Sur la machine de rendu : python3 worker_distant.py "
                  "--hote 0.0.0.0")
            sys.exit(1)
        outils_worker = sante.get("outils", {})
        executeur_distant = ExecuteurDistant(client, os.path.join(OUTPUT_DIR, "rendus"))
        disponibles = [o for o, ok in outils_worker.items() if ok]
        print(f"[Système] : Worker connecté ({args.worker}) — outils disponibles : "
              + (", ".join(disponibles) if disponibles else "aucun"))

    # ── 0bis. Exécution locale automatique (--local) ─────────────────────────
    # Le studio lance lui-même les logiciels installés sur cette machine.
    executeur_local = None
    outils_local: dict = {}
    if args.local:
        outils_local = outils_disponibles(ConfigWorker())
        executeur_local = ExecuteurLocal(
            dossier_rendus=os.path.join(OUTPUT_DIR, "rendus_local"))
        disponibles = [o for o, ok in outils_local.items() if ok]
        print("[Système] : Rendu LOCAL activé — le studio lancera lui-même : "
              + (", ".join(disponibles) if disponibles else "aucun outil détecté"))
        print("            ⚠️  Rappel : les scripts exécutés (Blender/Unreal/FFmpeg) "
              "sont générés par IA et tournent sur cette machine.")

    # ── 1. Initialisation de la mémoire commune ──────────────────────────────
    # L'état précédent n'est rechargé qu'en mode --reprendre : une nouvelle
    # production démarre toujours d'un état vierge, sinon les sorties d'une
    # ancienne production pourraient se mélanger à la nouvelle au moment de
    # la reprise (étapes sautées sur la base de données périmées).
    state = WorldState()
    if args.reprendre:
        if state.load():
            print("[Système] : État précédent chargé depuis output/world_state.json")
        else:
            print("[Avertissement] : --reprendre demandé mais aucun état précédent "
                  "trouvé — la production repart du début.")

    # ── 2. L'idée initiale ───────────────────────────────────────────────────
    print("=" * 45)
    print("=== BIENVENUE DANS VOTRE STUDIO IA ===")
    print("=" * 45)

    concept_initial = args.idea.strip()
    if args.reprendre and concept_initial:
        idee_en_cours = str(state.get("idea", "")).strip()
        if idee_en_cours and idee_en_cours != concept_initial:
            print("[Erreur] : --reprendre continue la production en cours, mais --idea")
            print("           fournit une idée différente de celle de cette production.")
            print(f"           Idée de la production en cours : {idee_en_cours}")
            print("           → Pour reprendre :               python main.py --reprendre")
            print("           → Pour une nouvelle production : python main.py --idea \"...\"")
            sys.exit(1)
    if not concept_initial and args.reprendre:
        # En reprise, on réutilise l'idée de la production interrompue
        concept_initial = str(state.get("idea", "")).strip()
        if concept_initial:
            print(f"[Système] : Reprise de la production — idée : {concept_initial}")
    if not concept_initial:
        concept_initial = input("Quelle est votre idée de film aujourd'hui ?\n> ").strip()

    if not concept_initial:
        print("[Erreur] : L'idée ne peut pas être vide. Relancez le studio.")
        sys.exit(1)

    state.update("idea", concept_initial)

    # ── 3. Journal de production (SQLite + logs structurés JSONL) ─────────────
    # L'identifiant de production est persisté dans l'état : une reprise
    # (--reprendre) réutilise le même identifiant, si bien que ses nouvelles
    # étapes s'ajoutent à l'historique de la production d'origine au lieu d'en
    # créer une nouvelle.
    production_id = str(state.get("production_id", "")).strip()
    if args.production_id:
        # Identifiant imposé par l'appelant (l'API le génère et le renvoie au
        # client AVANT de lancer le pipeline, pour que le suivi le retrouve).
        production_id = args.production_id
        state.update("production_id", production_id)
    elif not production_id:
        production_id = uuid.uuid4().hex[:12]
        state.update("production_id", production_id)
    journal = JournalProduction(production_id=production_id)
    journal.demarrer_production(
        idee=concept_initial,
        modele=args.model.strip() or "défaut",
        mode=_mode_execution(args))

    # ── 4. Exécution du pipeline par l'orchestrateur central ────────────────
    orchestrateur = Orchestrateur(
        state=state,
        etapes=construire_pipeline(executeur_distant, outils_worker,
                                   executeur_local, outils_local),
        dossier_agents=AGENTS_DIR,
        surcharge_modele=args.model.strip() or None,
        reprendre=args.reprendre,
        interactif=args.interactif,
        journal=journal,
    )

    # try/finally : la fermeture du journal (et donc de la connexion SQLite)
    # est garantie sur TOUS les chemins de sortie, y compris une exception
    # inattendue ou un sys.exit (qui lève SystemExit, propagé par le finally).
    try:
        try:
            bilan = orchestrateur.executer()
        except ErreurEtapeCritique:
            # L'orchestrateur a déjà tout affiché et sauvegardé l'état partiel.
            journal.terminer_production("echec")
            sys.exit(1)
        except ArretUtilisateur:
            # Arrêt volontaire à un point de validation : état déjà sauvegardé,
            # reprise possible avec --reprendre. Ce n'est pas une erreur.
            journal.terminer_production("arretee")
            sys.exit(0)
        except Exception:
            # Exception inattendue (hors étapes déjà gérées) : marquer la
            # production en échec plutôt que de la laisser « en_cours », puis
            # laisser l'erreur remonter. (SystemExit n'est pas une Exception :
            # les sys.exit ci-dessus ne sont pas interceptés ici.)
            journal.terminer_production("echec")
            raise
        journal.terminer_production("terminee")
    finally:
        journal.fermer()

    # ── 5. Récapitulatif final ───────────────────────────────────────────────
    _afficher_recap_final(state, bilan)
    print(f"  🗂  Historique : python main.py --historique  "
          f"(production {production_id})")


if __name__ == "__main__":
    lancer_studio()
