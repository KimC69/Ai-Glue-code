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
    print("[Système] : En attente de l'Agent 02 (Architecte Narratif)...")


if __name__ == "__main__":
    lancer_studio()
