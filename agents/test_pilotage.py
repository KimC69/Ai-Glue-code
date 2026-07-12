"""
test_pilotage.py — Tests des fonctions de « contrôle production à distance ».

Couvre les briques ajoutées pour le pilotage depuis la PWA et le bureau, en
restant fidèle à la philosophie du projet : bibliothèque standard uniquement,
AUCUN appel réseau ni clé OpenAI. Les agents (LangChain) sont remplacés par un
faux pour tester le chat sans dépendance.

Lancement :  python -m unittest test_pilotage    (ou : python test_pilotage.py)
"""

import os
import tempfile
import types
import unittest

import controle_production as cp
import config_agents as ca
import memoire
import chat_agents
from orchestrateur import Orchestrateur, ArretUtilisateur, _ControleNul


# ── Doublures de test (aucun réseau, aucun agent réel) ───────────────────────

class FauxEtape:
    def __init__(self, numero=1, nom="Étape de test"):
        self.numero = numero
        self.nom = nom


class FauxState:
    def save(self):
        return "/tmp/faux_state.json"


class FauxJournal:
    """Compte les appels de pause/reprise pour vérifier le comportement."""
    def __init__(self):
        self.pauses = 0
        self.reprises = 0
        self.evenements = 0

    def evenement(self, *a, **k):
        self.evenements += 1

    def production_en_pause(self):
        self.pauses += 1

    def production_reprise(self):
        self.reprises += 1


class ControleScript:
    """Contrôleur scénarisé : renvoie des commandes dans l'ordre, puis ""."""
    def __init__(self, commandes):
        self.commandes = list(commandes)
        self.effacements = 0

    def lire(self):
        return self.commandes.pop(0) if self.commandes else ""

    def effacer(self):
        self.effacements += 1


def orchestrateur_test(controle, journal=None):
    return Orchestrateur(
        state=FauxState(), etapes=[], dossier_agents=".",
        journal=journal, controle=controle, intervalle_pause=0.001)


# ── controle_production ──────────────────────────────────────────────────────

class TestControleProduction(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def test_ecrire_lire_effacer(self):
        cp.ecrire_commande("abc123abc123", "pause", dossier=self.dossier)
        self.assertEqual(cp.lire_commande("abc123abc123", self.dossier), "pause")
        cp.effacer_commande("abc123abc123", self.dossier)
        self.assertEqual(cp.lire_commande("abc123abc123", self.dossier), "")

    def test_commande_invalide_leve(self):
        with self.assertRaises(ValueError):
            cp.ecrire_commande("abc123abc123", "exploser", dossier=self.dossier)

    def test_lecture_echoue_sur(self):
        # Fichier absent → "" ; fichier illisible → "" (jamais d'exception).
        self.assertEqual(cp.lire_commande("inexistant0000", self.dossier), "")
        chemin = cp.chemin_controle("corrompu00000", self.dossier)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("{ ceci n'est pas du json")
        self.assertEqual(cp.lire_commande("corrompu00000", self.dossier), "")

    def test_effacer_absent_ne_leve_pas(self):
        cp.effacer_commande("jamais_ecrit0", self.dossier)  # ne doit pas lever


# ── config_agents ────────────────────────────────────────────────────────────

class TestConfigAgents(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def test_tous_actifs_par_defaut(self):
        for a in ca.CATALOGUE_AGENTS:
            self.assertTrue(ca.est_actif(a["numero"], dossier=self.dossier))

    def test_desactiver_optionnel_persiste(self):
        ca.definir_agent(6, False, dossier=self.dossier)
        self.assertFalse(ca.est_actif(6, dossier=self.dossier))
        # Rechargé depuis le disque : la désactivation a bien persisté.
        self.assertFalse(ca.charger_config(self.dossier).get(6))

    def test_indispensable_toujours_actif(self):
        # est_actif ignore toute config pour les agents 1 à 5.
        self.assertTrue(ca.est_actif(1, config={1: False}, dossier=self.dossier))

    def test_desactiver_indispensable_refuse(self):
        with self.assertRaises(ValueError):
            ca.definir_agent(1, False, dossier=self.dossier)

    def test_agent_inconnu_leve(self):
        with self.assertRaises(ValueError):
            ca.agent(99)

    def test_liste_agents_forme(self):
        liste = ca.liste_agents(self.dossier)
        self.assertEqual(len(liste), len(ca.CATALOGUE_AGENTS))
        self.assertEqual(set(liste[0]), {"numero", "nom", "optionnel", "actif"})


# ── memoire ──────────────────────────────────────────────────────────────────

class TestMemoire(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def test_objectifs_roundtrip_et_horodatage(self):
        objet = memoire.ecrire_objectifs("Ton poétique.", par="alice",
                                         dossier=self.dossier)
        self.assertTrue(objet["modifie_le"])          # horodaté automatiquement
        relu = memoire.lire_objectifs(self.dossier)
        self.assertEqual(relu["texte"], "Ton poétique.")
        self.assertEqual(relu["par"], "alice")

    def test_objectifs_absents_champs_vides(self):
        self.assertEqual(memoire.lire_objectifs(self.dossier)["texte"], "")

    def test_resume_world_state_tronque_et_ignore_vides(self):
        import json
        chemin = os.path.join(self.dossier, memoire.NOM_WORLD_STATE)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"production_id": "id123456789a", "vision": "V",
                       "scenario": "x" * 500, "vide": ""}, f)
        resume = memoire.resume_world_state(self.dossier)
        self.assertTrue(resume["present"])
        self.assertIn("vision", resume["cles"])
        self.assertNotIn("vide", resume["cles"])       # clé vide ignorée
        self.assertTrue(resume["cles"]["scenario"].endswith("…"))  # tronqué

    def test_comptage_actives_echoue_ferme(self):
        # Garde-fou : si le journal est dégradé, le comptage LÈVE (échoue fermé)
        # au lieu de renvoyer 0 — sinon un reset pourrait passer à tort.
        from journal_production import JournalProduction
        jour = JournalProduction(production_id="zzzzzzzzzzzz", dossier=self.dossier)
        jour._degrade = True
        with self.assertRaises(RuntimeError):
            jour.compter_productions_actives()

    def test_reset(self):
        memoire.ecrire_objectifs("x", dossier=self.dossier)  # crée le dossier
        import json
        chemin = os.path.join(self.dossier, memoire.NOM_WORLD_STATE)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"a": 1}, f)
        self.assertTrue(memoire.reinitialiser_world_state(self.dossier))
        self.assertFalse(memoire.reinitialiser_world_state(self.dossier))  # déjà vide


# ── Point de contrôle de l'orchestrateur ─────────────────────────────────────

class TestPointDeControle(unittest.TestCase):
    def test_controle_nul_ne_fait_rien(self):
        orch = orchestrateur_test(_ControleNul(), FauxJournal())
        orch._point_de_controle(FauxEtape())   # ne doit rien lever

    def test_arreter_leve_arret_utilisateur(self):
        controle = ControleScript(["arreter"])
        orch = orchestrateur_test(controle, FauxJournal())
        with self.assertRaises(ArretUtilisateur):
            orch._point_de_controle(FauxEtape())
        self.assertEqual(controle.effacements, 1)   # canal nettoyé à l'arrêt

    def test_pause_puis_reprise(self):
        # 1er lire → "pause" (entre en attente) ; puis "pause" ; puis "reprendre".
        controle = ControleScript(["pause", "pause", "reprendre"])
        journal = FauxJournal()
        orch = orchestrateur_test(controle, journal)
        orch._point_de_controle(FauxEtape())        # doit revenir sans lever
        self.assertEqual(journal.pauses, 1)
        self.assertEqual(journal.reprises, 1)
        self.assertEqual(controle.effacements, 1)

    def test_pause_puis_arret(self):
        controle = ControleScript(["pause", "arreter"])
        orch = orchestrateur_test(controle, FauxJournal())
        with self.assertRaises(ArretUtilisateur):
            orch._point_de_controle(FauxEtape())

    def test_pause_reste_en_pause_si_lecture_vide(self):
        # « échoue sûr » : une lecture "" (fichier effacé/illisible) NE DOIT PAS
        # reprendre — seule la commande explicite « reprendre » relance.
        controle = ControleScript(["pause", "", "", "reprendre"])
        journal = FauxJournal()
        orch = orchestrateur_test(controle, journal)
        orch._point_de_controle(FauxEtape())
        self.assertEqual(journal.pauses, 1)
        self.assertEqual(journal.reprises, 1)


# ── chat_agents (agent réel remplacé par un faux) ────────────────────────────

class TestChatAgents(unittest.TestCase):
    def test_agent_inconnu_leve(self):
        with self.assertRaises(ValueError):
            chat_agents.repondre(99, "bonjour")

    def test_message_vide_leve(self):
        with self.assertRaises(ValueError):
            chat_agents.repondre(1, "   ")

    def test_reponse_via_faux_agent(self):
        class FauxAgent:
            def __init__(self, **k):
                pass

            def discuter(self, message, role=""):
                return f"[{role[:10]}] {message}"

        faux_module = types.SimpleNamespace(DirecteurCreatif=FauxAgent)
        original = chat_agents.charger_module
        chat_agents.charger_module = lambda chemin: faux_module
        try:
            reponse = chat_agents.repondre(1, "Bonjour")
            self.assertTrue(reponse.startswith("["))
            self.assertIn("Bonjour", reponse)
        finally:
            chat_agents.charger_module = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
