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
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from shared_state import WorldState
from orchestrateur import Etape, Orchestrateur, ErreurEtapeCritique
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


# ── Définition déclarative du pipeline ───────────────────────────────────────

def construire_pipeline() -> list:
    """Décrit les 7 étapes du studio. L'Orchestrateur se charge du reste."""
    return [
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
            cles_sortie=("visual_style", "blender_script"),
            titre="SCÈNE BLENDER GÉNÉRÉE ET ENREGISTRÉE",
            afficher=lambda agent, r: agent.afficher_resultat(),
            critique=True,
            conseil="Conseil : la génération de code Blender bénéficie du modèle gpt-4o.",
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
            cles_sortie=("technical_notes", "unreal_script"),
            titre="SETUP UNREAL ENGINE GÉNÉRÉ ET ENREGISTRÉ",
            afficher=lambda agent, r: agent.afficher_resultat(),
            critique=True,
            conseil="Conseil : la génération de code Unreal bénéficie du modèle gpt-4o.",
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
            cles_sortie=("ffmpeg_script",),
            titre="EXPORTS MULTI-FORMAT GÉNÉRÉS",
            afficher=lambda agent, r: agent.afficher_rapport(),
            critique=False,   # l'export ne bloque jamais la production
        ),
    ]


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
        )
    else:
        print("\n  ℹ️  Chemins des scripts Blender/Unreal absents de l'état —")
        print("     commandes headless non affichées. Relancez le pipeline complet.")
    print()


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
    args = parser.parse_args(argv)

    # ── 1. Initialisation de la mémoire commune ──────────────────────────────
    state = WorldState()
    if state.load():
        print("[Système] : État précédent chargé depuis output/world_state.json")

    # ── 2. L'idée initiale ───────────────────────────────────────────────────
    print("=" * 45)
    print("=== BIENVENUE DANS VOTRE STUDIO IA ===")
    print("=" * 45)

    concept_initial = args.idea.strip()
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

    # ── 3. Exécution du pipeline par l'orchestrateur central ────────────────
    orchestrateur = Orchestrateur(
        state=state,
        etapes=construire_pipeline(),
        dossier_agents=AGENTS_DIR,
        surcharge_modele=args.model.strip() or None,
        reprendre=args.reprendre,
    )

    try:
        bilan = orchestrateur.executer()
    except ErreurEtapeCritique:
        # L'orchestrateur a déjà tout affiché et sauvegardé l'état partiel.
        sys.exit(1)

    # ── 4. Récapitulatif final ───────────────────────────────────────────────
    _afficher_recap_final(state, bilan)


if __name__ == "__main__":
    lancer_studio()
