---
name: Objectifs admin-only
description: Permission requise pour modifier la note d'objectifs persistants — réservée à l'administrateur, pas à l'opérateur.
---

# Objectifs persistants : réservés à l'administrateur

**Règle :** la modification des objectifs persistants (`POST /objectifs`) est protégée par la permission `gerer_utilisateurs`, c'est-à-dire le rôle `admin` uniquement. Les opérateurs peuvent lancer et piloter des productions, mais pas changer la ligne éditoriale globale du studio.

**Why :** le producteur a formulé cette séparation dans le cahier des charges de la tâche « Contrôle production à distance » : « piloter/lancer réservé aux rôles autorisés, changer la config des agents/objectifs réservé à l'admin ». Les objectifs sont une config durable, pas une action de production.

**How to apply :**
- Côté API : `api_serveur.py::_definir_objectifs` appelle `_exiger("gerer_utilisateurs")`.
- Côté bureau : `bureau.py` n'active le bouton « Enregistrer les objectifs » que si `self.client.role in ROLES_ADMIN`.
- Côté PWA : `pwa/app.js` n'active le champ et le bouton que pour `ROLES_ADMIN`.
- Côté client : `client_api.py` reflète la permission requise dans sa docstring.
- Docs : `README.md` et `MANUEL.md` listent `POST /objectifs` sous `gerer_utilisateurs`.

Ne pas revenir à `piloter_production` pour les objectifs sans une décision explicite de l'utilisateur.