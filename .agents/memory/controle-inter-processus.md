---
name: Contrôle inter-processus par fichier de commande
description: Décision d'archi — piloter une production détachée (pause/reprise/arrêt) via un fichier JSON de commande, avec règles de robustesse asymétriques.
---

# Pilotage d'une production en cours (pause / reprise / arrêt)

Une production tourne dans un **sous-processus détaché** (lancé par l'API ou la
CLI) : plus aucun canal clavier. Le pilotage passe par un **fichier de commande
par production** (`output/controle/<id>.json`, commandes `pause`/`reprendre`/
`arreter`). L'orchestrateur le consulte au **début de chaque étape**, donc une
commande prend effet **à la granularité de l'étape**, jamais au milieu.

**Why:** philosophie du projet = stdlib d'abord, zéro dépendance, pas de socket
ni de broker. Un fichier + `os.replace` atomique suffit et reste testable sans
réseau ni clé.

## Règles de robustesse — asymétriques selon le sens
- **Écriture (interfaces) = échoue FERMÉ** : si la commande ne peut pas être
  écrite, on lève ; l'interface dit honnêtement « non transmise » plutôt que de
  faire croire à une pause. Le fichier temporaire porte un **suffixe uuid unique**
  (sinon collision de `<id>.json.tmp` entre écritures concurrentes).
- **Lecture au checkpoint (orchestrateur) = échoue SÛR** : fichier illisible →
  "" = aucune commande, la production continue. Une lecture ratée ne tue jamais
  une prod.
- **Boucle de pause = ne reprend QUE sur `reprendre` explicite.** "" (fichier
  effacé/illisible) ou `pause` → rester en pause. **Why:** sous « échoue sûr »,
  traiter "" comme reprise = reprise involontaire sur simple incident de lecture.

## Garde-fous d'intégrité d'état (piège du fail-open)
Un check qui protège une action **destructive** (ex. reset de `world_state`) ne
doit PAS réutiliser une lecture « échoue sûr » qui renvoie 0/vide en cas
d'échec : c'est un **fail-open**. Il doit **échouer fermé** — comptage direct
SQL (`WHERE statut IN (...)`, sans `LIMIT`) qui **lève** si indéterminé (journal
dégradé/curseur None), et l'appelant refuse l'action (503) au lieu de supposer
« rien d'actif ». **How to apply:** tout nouveau garde-fou basé sur l'état DB
avant une suppression/écrasement.

## Permissions (rappel)
`piloter_production` = pause/reprise/arrêt + objectifs + chat ; `consulter` =
lectures ; `gerer_utilisateurs` (admin) = toggle agents + reset mémoire. Agents
désactivables = **optionnels 6/7/8 uniquement** (1–5 indispensables → refus 409).
