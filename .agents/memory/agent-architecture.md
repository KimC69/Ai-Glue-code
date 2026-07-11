---
name: Architecture des agents
description: Décisions d'architecture pour les agents du studio cinématographique (initialisation, erreurs, orchestrateur).
---

# Architecture des agents

## Règle

Tous les agents héritent d'une classe de base `BaseAgent` qui centralise :
- la vérification de la clé API OpenAI (lève `RuntimeError` si manquante) ;
- l'initialisation du LLM, du parser Pydantic et du prompt ;
- l'identifiant de l'agent pour les messages d'erreur.

Aucune classe d'agent ne doit appeler `sys.exit()` : elle lève une exception claire, et c'est l'orchestrateur qui décide d'arrêter ou de continuer.

**Why:** Avant la refactorisation, chaque agent dupliquait l'initialisation du LLM/parser et utilisait `sys.exit()` en cas d'erreur, ce qui rendait impossible une reprise propre, un test unitaire, ou un traitement différencié selon la criticité de l'agent.

**How to apply:**
- Lors de la création d'un nouvel agent, hériter de `BaseAgent`, passer `output_schema` et `agent_id`, puis appeler `self._build_prompt()`.
- Dans l'orchestrateur, envelopper instanciation + exécution de l'agent dans un même `try/except`.
- Pour les agents critiques (01–05), sauvegarder l'état partiel et arrêter proprement.
- Pour les agents optionnels (06–07), logger l'erreur et continuer sans bloquer le pipeline.
