"""
main.py — Orchestrateur principal du Studio IA Cinématographique.

Architecture :
  Input utilisateur
       │
       ▼
  [Agent 01 : DirecteurCreatif]   → vision_globale, genre, ton
       │
       ▼
  [Agent 02 : ArchitecteNarratif] → synopsis, actes, scènes clés
       │
       ▼
  [Agent 03 : Scenariste]         → dialogues, personnages
       │
       ▼
  [Agent 04 : DirecteurArtistique]→ script Blender (.py)
       │
       ▼
  [Agent 05 : DirecteurTechnique] → script Unreal (.sh)
       │
       ▼
  [Agent 06 : SuperviseurPostProduction] → audit de conformité,
                                            déclenche GIMP/Kdenlive
                                            SEULEMENT si nécessaire
        │
        ▼
  [Agent 07 : ExporteurMultiFormat] → déclinaison multi-format

Usage :
    cd agents/
    python main.py
"""

import os
import sys
import importlib.util

# On importe la gestion de l'état (la Bible de production)
from shared_state import WorldState
from dotenv import load_dotenv

# Chargement des variables d'environnement (.env)
load_dotenv()


def _charger_agent(filename: str):
    """
    Charge un module Python depuis un fichier dont le nom commence par un chiffre.
    Python n'autorise pas `from 01_directeur_creatif import ...` directement.
    """
    agents_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(agents_dir, filename)
    module_name = filename.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _afficher_erreur_agent(agent_nom: str, e: Exception, conseil: str = "") -> None:
    """Affiche un message d'erreur clair quand un agent critique échoue."""
    print(f"\n❌ [{agent_nom}] Échec : {e}")
    if conseil:
        print(f"\n{conseil}")
    print("\nConseils généraux :")
    print("  - Réessayez (les réponses LLM varient légèrement)")
    print("  - Vérifiez votre quota sur platform.openai.com/usage")
    print("  - Vérifiez que votre fichier .env contient une clé OPENAI_API_KEY valide")


def _arreter_avec_etat(state: WorldState, agent_nom: str, e: Exception) -> None:
    """Sauvegarde l'état courant et arrête proprement le pipeline."""
    saved_path = state.save()
    print(f"\n💾 État partiel sauvegardé → {saved_path}")
    print(f"\n⛔ Le pipeline s'arrête ici car {agent_nom} est une étape critique.")
    print("   Corrigez le problème et relancez. Le travail déjà effectué est conservé.")
    sys.exit(1)


def lancer_studio():
    # ── 1. INITIALISATION ─────────────────────────────────────────────────────
    # On crée l'objet qui gère la mémoire commune
    state = WorldState()

    # Chargement d'un état précédent si disponible
    if state.load():
        print("[Système] : État précédent chargé depuis output/world_state.json")

    # ── 2. TON INPUT (La communication par prompt) ────────────────────────────
    print("=" * 45)
    print("=== BIENVENUE DANS VOTRE STUDIO IA ===")
    print("=" * 45)
    concept_initial = input("Quelle est votre idée de film aujourd'hui ?\n> ")

    if not concept_initial.strip():
        print("[Erreur] : L'idée ne peut pas être vide. Relancez le studio.")
        sys.exit(1)

    # Sauvegarde de l'idée initiale dans la mémoire commune
    state.update("idea", concept_initial)

    # ── 3. L'ACTION DE L'AGENT 01 ─────────────────────────────────────────────
    # On charge le module via importlib (les noms commençant par un chiffre
    # ne sont pas importables avec `from 01_... import ...` en Python standard)
    module_01 = _charger_agent("01_directeur_creatif.py")
    DirecteurCreatif = module_01.DirecteurCreatif

    print(f"\n[Système] : Analyse du concept par le Directeur Créatif...")

    try:
        boss = DirecteurCreatif()
        vision = boss.generer_vision(concept_initial)
    except Exception as e:
        _afficher_erreur_agent("Agent 01 - Directeur Créatif", e)
        _arreter_avec_etat(state, "Agent 01 - Directeur Créatif", e)

    # ── 4. SAUVEGARDE DANS LA MÉMOIRE (L'étape cruciale) ─────────────────────
    # On enregistre la vision pour que les agents 02, 03, 04 puissent la lire
    state.update("vision_globale", vision)
    state.update("genre", boss.dernier_genre)
    state.update("tone", boss.dernier_ton)
    saved_path = state.save()

    print("\n--- VISION VALIDÉE ET ENREGISTRÉE ---")
    print(vision)
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 5. L'ACTION DE L'AGENT 02 ─────────────────────────────────────────────
    module_02 = _charger_agent("02_architecte_narratif.py")
    ArchitecteNarratif = module_02.ArchitecteNarratif

    print("\n[Système] : Construction de la structure narrative par l'Architecte...")

    try:
        architecte = ArchitecteNarratif()
        structure = architecte.construire_structure(
            vision_globale=state.get("vision_globale"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except Exception as e:
        _afficher_erreur_agent("Agent 02 - Architecte Narratif", e)
        _arreter_avec_etat(state, "Agent 02 - Architecte Narratif", e)

    # ── 6. SAUVEGARDE DANS LA MÉMOIRE ─────────────────────────────────────────
    state.update("synopsis",   structure["synopsis"])
    state.update("acts",       structure["acts"])
    state.update("key_scenes", structure["key_scenes"])
    saved_path = state.save()

    print("\n--- STRUCTURE NARRATIVE VALIDÉE ET ENREGISTRÉE ---")
    print(architecte.afficher_structure())
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 7. L'ACTION DE L'AGENT 03 ─────────────────────────────────────────────
    module_03 = _charger_agent("03_scenariste.py")
    Scenariste = module_03.Scenariste

    print("\n[Système] : Écriture du scénario par le Scénariste...")

    try:
        scribe = Scenariste()
        scenario = scribe.ecrire_scenario(
            synopsis=state.get("synopsis"),
            acts=state.get("acts"),
            key_scenes=state.get("key_scenes"),
        )
    except Exception as e:
        _afficher_erreur_agent("Agent 03 - Scénariste", e)
        _arreter_avec_etat(state, "Agent 03 - Scénariste", e)

    # ── 8. SAUVEGARDE DANS LA MÉMOIRE ─────────────────────────────────────────
    state.update("character_sheet",    scenario["character_sheet"])
    state.update("screenplay_excerpt", scenario["screenplay_excerpt"])
    saved_path = state.save()

    print("\n--- SCÉNARIO VALIDÉ ET ENREGISTRÉ ---")
    print(scribe.afficher_scenario())
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 9. L'ACTION DE L'AGENT 04 ─────────────────────────────────────────────
    module_04 = _charger_agent("04_directeur_artistique.py")
    DirecteurArtistique = module_04.DirecteurArtistique

    print("\n[Système] : Génération de la scène Blender par le Directeur Artistique...")

    try:
        da = DirecteurArtistique()
        blender = da.creer_scene_blender(
            screenplay_excerpt=state.get("screenplay_excerpt"),
            character_sheet=state.get("character_sheet"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except Exception as e:
        _afficher_erreur_agent(
            "Agent 04 - Directeur Artistique", e,
            "Conseil : la génération de code Blender bénéficie du modèle gpt-4o."
        )
        _arreter_avec_etat(state, "Agent 04 - Directeur Artistique", e)

    # ── 10. SAUVEGARDE DANS LA MÉMOIRE ────────────────────────────────────────
    state.update("visual_style",   blender["visual_style"])
    state.update("blender_script", blender["blender_script"])
    saved_path = state.save()

    print("\n--- SCÈNE BLENDER GÉNÉRÉE ET ENREGISTRÉE ---")
    print(da.afficher_resultat())
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 11. L'ACTION DE L'AGENT 05 ────────────────────────────────────────────
    module_05 = _charger_agent("05_directeur_technique.py")
    DirecteurTechnique = module_05.DirecteurTechnique

    print("\n[Système] : Génération du setup Unreal Engine par le Directeur Technique...")

    try:
        dt = DirecteurTechnique()
        unreal = dt.creer_setup_unreal(
            visual_style=state.get("visual_style"),
            blender_script=state.get("blender_script"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except Exception as e:
        _afficher_erreur_agent(
            "Agent 05 - Directeur Technique", e,
            "Conseil : la génération de code Unreal bénéficie du modèle gpt-4o."
        )
        _arreter_avec_etat(state, "Agent 05 - Directeur Technique", e)

    # ── 12. SAUVEGARDE FINALE DANS LA MÉMOIRE ─────────────────────────────────
    state.update("technical_notes", unreal["technical_notes"])
    state.update("unreal_script",   unreal["unreal_script"])
    saved_path = state.save()

    print("\n--- SETUP UNREAL ENGINE GÉNÉRÉ ET ENREGISTRÉ ---")
    print(dt.afficher_resultat())
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 13. L'ACTION DE L'AGENT 06 (audit conditionnel, entièrement optionnel) ─
    module_06 = _charger_agent("06_superviseur_post_production.py")
    SuperviseurPostProduction = module_06.SuperviseurPostProduction

    print("\n[Système] : Audit de conformité par le Superviseur Post-Production...")
    audit = None
    try:
        superviseur = SuperviseurPostProduction()
        audit = superviseur.analyser_conformite(
            visual_style=state.get("visual_style"),
            technical_notes=state.get("technical_notes"),
            blender_script=state.get("blender_script"),
            unreal_script=state.get("unreal_script"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except Exception as e:
        print(f"\n⚠️  [Agent 06 - Superviseur Post-Production] Échec : {e}")
        print("   L'audit de conformité a échoué — le pipeline continue sans lui.")

    if audit is not None:
        for cle in (
            "coherence_score", "issues",
            "needs_gimp_retouching", "gimp_script",
            "needs_video_editing", "video_editing_notes",
            "needs_inkscape", "inkscape_notes",
            "needs_darktable", "darktable_notes",
            "needs_krita", "krita_script",
            "needs_obs", "obs_notes",
        ):
            state.update(cle, audit[cle])
        saved_path = state.save()

        print("\n--- AUDIT DE CONFORMITÉ ---")
        print(superviseur.afficher_rapport())
        print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 14. L'ACTION DE L'AGENT 07 (export multi-format, optionnel) ─────────
    print("\n[Système] : Préparation des exports multi-format...")
    export = None
    try:
        module_07 = _charger_agent("07_exporteur_multi_format.py")
        ExporteurMultiFormat = module_07.ExporteurMultiFormat
        exporteur = ExporteurMultiFormat()
        export = exporteur.generer_exports(
            vision_globale=state.get("vision_globale"),
            visual_style=state.get("visual_style"),
            technical_notes=state.get("technical_notes"),
            blender_script=state.get("blender_script"),
            unreal_script=state.get("unreal_script"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except Exception as e:
        print(f"\n⚠️  [Agent 07 - Exporteur Multi-Format] Échec : {e}")
        print("   L'export multi-format a échoué — le pipeline continue sans lui.")

    if export is not None:
        state.update("export_formats", export["formats"])
        state.update("ffmpeg_script", export["ffmpeg_script"])
        saved_path = state.save()

        print("\n--- EXPORTS MULTI-FORMAT GÉNÉRÉS ---")
        print(exporteur.afficher_rapport())
        print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 15. FIN DE LA PRODUCTION ───────────────────────────────────────────────
    print("\n" + "=" * 45)
    print("  🎬 PIPELINE COMPLET — PRODUCTION TERMINÉE")
    print("=" * 45)
    print(f"  État complet     : {saved_path}")
    print(f"  Scripts générés  : agents/output/")
    print("  Les 5 agents créatifs ont livré : vision, structure, scénario,")
    print("  scène Blender et setup Unreal Engine.")
    print("  Le Superviseur a déclenché uniquement les outils nécessaires.")
    print("  L'Exporteur a préparé les déclinaisons multi-format.")
    print("\n  ✅ Bonne production !")

    # ── 16. COMMANDES HEADLESS PRÊTES À L'EMPLOI ─────────────────────────────
    module_headless = _charger_agent("utils_headless.py")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

    def _ecrire_notes_si_necessaire(actif: bool, contenu: str, nom_fichier: str) -> str:
        """Écrit les notes d'un outil "instructions" (pas de script direct) dans
        un fichier, uniquement si l'Agent 06 l'a jugé nécessaire. Retourne le
        chemin, ou '' si non nécessaire."""
        if not actif or not contenu:
            return ""
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, nom_fichier)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(contenu)
        return filepath

    gimp_path = ""
    krita_path = ""
    montage_notes_path = ""
    inkscape_notes_path = ""
    darktable_notes_path = ""
    obs_notes_path = ""

    if audit is not None:
        if audit["needs_gimp_retouching"]:
            gimp_path = audit["gimp_saved_path"]
        if audit["needs_krita"]:
            krita_path = audit["krita_saved_path"]
        # Ces outils n'ont pas de vrai mode headless : on sauvegarde des notes
        # d'instructions à suivre plutôt qu'un script directement exécutable.
        montage_notes_path = _ecrire_notes_si_necessaire(
            audit["needs_video_editing"], audit["video_editing_notes"], "notes_montage.txt"
        )
        inkscape_notes_path = _ecrire_notes_si_necessaire(
            audit["needs_inkscape"], audit["inkscape_notes"], "notes_inkscape.txt"
        )
        darktable_notes_path = _ecrire_notes_si_necessaire(
            audit["needs_darktable"], audit["darktable_notes"], "notes_darktable.txt"
        )
        obs_notes_path = _ecrire_notes_si_necessaire(
            audit["needs_obs"], audit["obs_notes"], "notes_obs.txt"
        )

    module_headless.afficher_commandes_headless(
        blender_path=blender["saved_path"],
        unreal_path=unreal["saved_path"],
        gimp_path=gimp_path,
        montage_notes_path=montage_notes_path,
        inkscape_notes_path=inkscape_notes_path,
        darktable_notes_path=darktable_notes_path,
        krita_path=krita_path,
        obs_notes_path=obs_notes_path,
        export_script_path=export["saved_path"] if export else "",
    )
    print()


if __name__ == "__main__":
    lancer_studio()
