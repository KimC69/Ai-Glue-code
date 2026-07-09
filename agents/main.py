"""
main.py — Orchestrateur principal du Studio IA Cinématographique.

Architecture :
  Input utilisateur
       │
       ▼
  [Agent 01 : DirecteurCreatif]   → vision_globale, genre, ton
       │
       ▼
  [Agent 02 : ArchitecteNarratif] → synopsis, actes, scènes clés   (à venir)
       │
       ▼
  [Agent 03 : Scenariste]         → dialogues, personnages          (à venir)
       │
       ▼
  [Agent 04 : DirecteurArtistique]→ script Blender (.py)            (à venir)
       │
       ▼
  [Agent 05 : DirecteurTechnique] → script Unreal (.sh)             (à venir)

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
    boss = DirecteurCreatif()

    try:
        vision = boss.generer_vision(concept_initial)
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nConseils :")
        print("  - Réessayez (les réponses LLM varient légèrement)")
        print("  - Vérifiez votre quota sur platform.openai.com/usage")
        sys.exit(1)

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
    architecte = ArchitecteNarratif()

    try:
        structure = architecte.construire_structure(
            vision_globale=state.get("vision_globale"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nConseils :")
        print("  - Réessayez (les réponses LLM varient légèrement)")
        print("  - Vérifiez votre quota sur platform.openai.com/usage")
        sys.exit(1)

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
    scribe = Scenariste()

    try:
        scenario = scribe.ecrire_scenario(
            synopsis=state.get("synopsis"),
            acts=state.get("acts"),
            key_scenes=state.get("key_scenes"),
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nConseils :")
        print("  - Réessayez (les réponses LLM varient légèrement)")
        print("  - Vérifiez votre quota sur platform.openai.com/usage")
        sys.exit(1)

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
    da = DirecteurArtistique()

    try:
        blender = da.creer_scene_blender(
            screenplay_excerpt=state.get("screenplay_excerpt"),
            character_sheet=state.get("character_sheet"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nConseils :")
        print("  - Réessayez (les réponses LLM varient légèrement)")
        print("  - Utilisez --model gpt-4o pour de meilleures réponses de code")
        print("  - Vérifiez votre quota sur platform.openai.com/usage")
        sys.exit(1)

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
    dt = DirecteurTechnique()

    try:
        unreal = dt.creer_setup_unreal(
            visual_style=state.get("visual_style"),
            blender_script=state.get("blender_script"),
            genre=state.get("genre"),
            tone=state.get("tone"),
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nConseils :")
        print("  - Réessayez (les réponses LLM varient légèrement)")
        print("  - Utilisez --model gpt-4o pour de meilleures réponses de code")
        print("  - Vérifiez votre quota sur platform.openai.com/usage")
        sys.exit(1)

    # ── 12. SAUVEGARDE FINALE DANS LA MÉMOIRE ─────────────────────────────────
    state.update("technical_notes", unreal["technical_notes"])
    state.update("unreal_script",   unreal["unreal_script"])
    saved_path = state.save()

    print("\n--- SETUP UNREAL ENGINE GÉNÉRÉ ET ENREGISTRÉ ---")
    print(dt.afficher_resultat())
    print(f"\n[Système] : État sauvegardé → {saved_path}")

    # ── 13. FIN DE LA PRODUCTION ───────────────────────────────────────────────
    print("\n" + "=" * 45)
    print("  🎬 PIPELINE COMPLET — PRODUCTION TERMINÉE")
    print("=" * 45)
    print(f"  État complet     : {saved_path}")
    print(f"  Scripts générés  : agents/output/")
    print("  Les 5 agents ont livré : vision, structure, scénario,")
    print("  scène Blender et setup Unreal Engine.")
    print("\n  ✅ Bonne production !\n")


if __name__ == "__main__":
    lancer_studio()
