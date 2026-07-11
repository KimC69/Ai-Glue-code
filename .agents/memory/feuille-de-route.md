---
name: Feuille de route du studio IA
description: Roadmap en 10 étapes validée par l'utilisateur (issue de son audit initial) — statut d'avancement, règles de pilotage, vision cible.
---

# Feuille de route (validée par l'utilisateur)

Issue de l'audit complet demandé par l'utilisateur. **Règle de pilotage : c'est lui qui annonce chaque étape, une à la fois — ne jamais démarrer une étape sans son feu vert.** Principe directeur de son audit : cycle analyser → planifier → répartir → exécuter → vérifier → corriger → présenter, **sans boucle infinie** — après chaque cycle, les agents attendent une validation humaine avant de recommencer.

## Étapes

1. ✅ Orchestrateur robuste — exceptions récupérables (plus de `sys.exit()`), agents isolés (`BaseAgent`).
2. ✅ Orchestrateur central déclaratif — planification, dispatch, retry, validation des sorties, reprise, bilan.
3. ✅ Human-in-the-loop — `--interactif` : valider / réviser avec directives / arrêter proprement (étapes créatives 01–05).
4. ✅ Worker distant — exécution de Blender / Unreal / FFmpeg sur une autre machine (HTTP stdlib + jeton), rapatriement des résultats.
5. ✅ Base de données et logs structurés — SQLite `output/studio.db` + JSONL par production ; `--historique` ; objet nul + mode dégradé (voir agent-architecture.md).
6. ✅ Authentification et sécurité — module `securite.py` : comptes (pbkdf2), rôles admin/operateur/observateur, jetons de session signés (SESSION_SECRET) ; échoue fermé ; base `output/securite.db` (voir agent-architecture.md). N'active pas encore de contrôle sur la CLI (ce sera l'API).
7. ✅ API backend — `api_serveur.py` (HTTP stdlib pur) : met en service l'auth de l'étape 6, lancement de production asynchrone, échoue fermé (jamais de 500 pour un refus). Décisions et invariants dans agent-architecture.md.
8. ⬜ Interface web.
9. ⬜ Application Android — télécommande + tableau de bord : chat avec les agents, envoi d'instructions, suivi des tâches, notifications, rapports, autorisation d'actions.
10. ⬜ Application desktop (Windows/Linux) — interface complète : intervention à tout moment, suggestions, modification d'objectifs, relance de tâches, raisonnement de l'orchestrateur visible, journaux, ajout/suppression d'agents, gestion de la mémoire, performances.

## Vision cible (audit d'origine)

Transformer le workspace en plateforme d'agents IA autonome, extensible, multi-appareils (Android + PC + web), indépendante de Replit. Connexion quasi instantanée à des machines prédéfinies — plusieurs workers possibles (l'étape 4 en est la fondation) — pour ouvrir/contrôler de vrais logiciels, compiler, manipuler des fichiers, récupérer les résultats. Interruption humaine possible à n'importe quel moment, même en production.

**How to apply :** avant toute nouvelle étape, relire ce fichier + `agent-architecture.md` (décisions déjà prises) ; garder la philosophie zéro-dépendance côté infrastructure quand c'est possible (stdlib d'abord), et la compatibilité `--reprendre` à chaque ajout.
