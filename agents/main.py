"""
main.py — Orchestrateur principal du système multi-agents cinématographique.

Architecture LangChain :
  Idée → [Agent 01: Directeur] → [Agent 02: Architecte] → [Agent 03: Scénariste]
       → [Agent 04: Dir. Artistique (Blender)] → [Agent 05: Dir. Technique (Unreal)]

Usage :
  cd agents/
  python main.py
  python main.py --idea "Un vaisseau fantôme dérive dans une nébuleuse rouge"
  python main.py --model gpt-4o --idea "..."
"""

import os
import sys
import json
import argparse
import importlib.util
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from shared_state import ProjectState

# ─── Chargement des agents (noms de fichiers à préfixe numérique) ─────────────

def _load_agent(filename: str):
    """
    Charge un module Python depuis un fichier dont le nom commence par un chiffre.
    Nécessaire car Python n'autorise pas `import 01_directeur` directement.
    """
    agents_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(agents_dir, filename)
    module_name = filename.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_01 = _load_agent("01_directeur.py")
agent_02 = _load_agent("02_architecte_narratif.py")
agent_03 = _load_agent("03_scenariste.py")
agent_04 = _load_agent("04_directeur_artistique.py")
agent_05 = _load_agent("05_directeur_technique.py")

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

DEFAULT_IDEA = "Un astronaute découvre une civilisation bioluminescente sous les glaces d'Europe, lune de Jupiter"
DEFAULT_MODEL = "gpt-4o-mini"

# Libellés lisibles pour l'affichage des erreurs
AGENT_LABELS = {
    "agent_01": "Agent 01 — Directeur",
    "agent_02": "Agent 02 — Architecte Narratif",
    "agent_03": "Agent 03 — Scénariste",
    "agent_04": "Agent 04 — Directeur Artistique (Blender)",
    "agent_05": "Agent 05 — Directeur Technique (Unreal)",
}


# ─── Rapport final ────────────────────────────────────────────────────────────

def save_final_report(state: ProjectState) -> str:
    """Sauvegarde un rapport Markdown complet de la production."""
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"rapport_production_{timestamp}.md")

    report = f"""# Rapport de Production Cinématographique
Généré le : {datetime.now().strftime("%d/%m/%Y à %H:%M")}

---

## Idée Originale
{state.idea}

---

## 🎬 Agent 01 — Vision du Directeur
**Genre :** {state.genre}
**Ton :** {state.tone}

{state.director_vision}

---

## 📖 Agent 02 — Structure Narrative

### Synopsis
{state.synopsis}

### Structure en Actes
{state.acts}

### Scènes Clés
{state.key_scenes}

---

## ✍️ Agent 03 — Scénario

### Fiches Personnages
{state.character_sheet}

### Extrait de Scénario
```
{state.screenplay_excerpt}
```

---

## 🎨 Agent 04 — Direction Artistique (Blender)

### Style Visuel
{state.visual_style}

### Script Blender
```python
{state.blender_script}
```

---

## ⚙️ Agent 05 — Direction Technique (Unreal Engine)

### Notes Techniques
{state.technical_notes}

### Script Unreal
```bash
{state.unreal_script}
```

---

*Rapport généré automatiquement par le système multi-agents LangChain*
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return report_path


def save_state_json(state: ProjectState) -> str:
    """Sauvegarde l'état JSON complet pour réutilisation ou debug."""
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"state_{timestamp}.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(state.model_dump(), f, ensure_ascii=False, indent=2)

    return json_path


# ─── Pipeline principal ───────────────────────────────────────────────────────

def run_pipeline(idea: str, model: str = DEFAULT_MODEL) -> ProjectState:
    """
    Lance la chaîne complète des 5 agents avec gestion centralisée des erreurs.

    Chaque agent reçoit l'état enrichi par les agents précédents et y ajoute
    ses propres sorties. Si un agent échoue, le pipeline s'arrête et affiche
    un message d'erreur clair avec l'agent responsable.

    Args:
        idea: L'idée de film à développer
        model: Le modèle OpenAI à utiliser

    Returns:
        L'état final complet avec tous les livrables

    Raises:
        SystemExit: Si la clé API est manquante ou si un agent échoue fatalement
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY manquante !")
        print("   1. Copiez le fichier .env.example en .env")
        print("   2. Ajoutez votre clé OpenAI dans .env")
        print("   3. Relancez : python main.py\n")
        sys.exit(1)

    # LLM partagé entre tous les agents
    llm = ChatOpenAI(
        model=model,
        temperature=0.7,
        api_key=api_key,
    )

    print("=" * 60)
    print("  SYSTÈME MULTI-AGENTS CINÉMATOGRAPHIQUE — LangChain")
    print("=" * 60)
    print(f"  Modèle : {model}")
    print(f"  Idée   : {idea[:70]}{'...' if len(idea) > 70 else ''}")
    print("=" * 60)

    state = ProjectState(idea=idea)

    # Définition de la chaîne : (clé_agent, module, label)
    pipeline = [
        ("agent_01", agent_01, AGENT_LABELS["agent_01"]),
        ("agent_02", agent_02, AGENT_LABELS["agent_02"]),
        ("agent_03", agent_03, AGENT_LABELS["agent_03"]),
        ("agent_04", agent_04, AGENT_LABELS["agent_04"]),
        ("agent_05", agent_05, AGENT_LABELS["agent_05"]),
    ]

    for key, agent, label in pipeline:
        try:
            state = agent.invoke(state, llm)
        except RuntimeError as e:
            # Erreur de parsing LangChain : afficher et arrêter proprement
            print(f"\n❌ Échec — {label}")
            print(f"   {e}")
            print("\n   Conseils :")
            print("   - Réessayez (les réponses LLM varient légèrement à chaque appel)")
            print("   - Utilisez --model gpt-4o pour de meilleures réponses structurées")
            print("   - Vérifiez votre quota API sur platform.openai.com/usage\n")
            sys.exit(1)
        except Exception as e:
            # Erreur inattendue (réseau, quota, etc.)
            print(f"\n❌ Erreur inattendue — {label} : {e}\n")
            sys.exit(1)

    return state


# ─── Point d'entrée ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Système multi-agents cinématographique LangChain"
    )
    parser.add_argument(
        "--idea",
        type=str,
        default=DEFAULT_IDEA,
        help="L'idée de film à développer",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        choices=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        help="Modèle OpenAI à utiliser",
    )
    args = parser.parse_args()

    # Lancement du pipeline
    final_state = run_pipeline(idea=args.idea, model=args.model)

    # Sauvegarde des résultats
    print("\n" + "=" * 60)
    print("  PRODUCTION TERMINÉE — Sauvegarde des livrables...")
    print("=" * 60)

    report_path = save_final_report(final_state)
    json_path = save_state_json(final_state)

    print(f"\n  📄 Rapport Markdown : {report_path}")
    print(f"  📦 État JSON        : {json_path}")
    print(f"  📂 Scripts générés  : agents/output/")
    print("\n  ✅ Pipeline complet. Bonne production !\n")


if __name__ == "__main__":
    main()
