"""
test_projets.py — Tests unitaires (stdlib) des dossiers par projet et du mode
« suite / inspiration ». Aucun appel réseau ni LLM : tout est local et rapide.

Lancer :  python -m unittest test_projets
"""

import json
import os
import tempfile
import unittest

import projets
import shared_state
from journal_production import JournalProduction
from api_serveur import ConfigAPI, commande_lancement


class TestSlug(unittest.TestCase):

    def test_slug_basique(self):
        self.assertEqual(projets.slugifier("Alien"), "alien")

    def test_slug_accents_et_ponctuation(self):
        self.assertEqual(projets.slugifier("Alien 2 : le Rétour"),
                         "alien-2-le-retour")

    def test_slug_vide_leve(self):
        with self.assertRaises(ValueError):
            projets.slugifier("  :::  ")


class TestProjets(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def test_creer_puis_ouvrir_preserve_date_creation(self):
        a = projets.creer_ou_ouvrir("Alien", dossier=self.dossier)
        self.assertTrue(os.path.isdir(a["chemin"]))
        self.assertEqual(a["slug"], "alien")
        # Ré-ouverture : la date de création doit être préservée.
        b = projets.creer_ou_ouvrir("Alien", dossier=self.dossier)
        self.assertEqual(a["cree_le"], b["cree_le"])

    def test_lister_projets(self):
        projets.creer_ou_ouvrir("Alien", dossier=self.dossier)
        projets.creer_ou_ouvrir("Blade Runner", dossier=self.dossier)
        slugs = {p["slug"] for p in projets.lister_projets(self.dossier)}
        self.assertEqual(slugs, {"alien", "blade-runner"})

    def test_lister_projets_vide_echoue_sur(self):
        # Aucun dossier projets/ : renvoie [] sans lever.
        self.assertEqual(projets.lister_projets(self.dossier), [])

    def test_archiver_et_resume_reference(self):
        projets.creer_ou_ouvrir("Alien", dossier=self.dossier)
        # On archive l'état EN MÉMOIRE de la production (un dict), pas un fichier.
        etat = {"synopsis": "Un équipage face à une créature.",
                "character_sheet": "Ripley, officier.",
                "blender_script": "x" * 5000}
        chemin = projets.archiver_etat("alien", etat, dossier=self.dossier)
        self.assertTrue(os.path.exists(chemin))
        ref = projets.resume_reference("alien", dossier=self.dossier)
        self.assertIn("Ripley", ref)
        self.assertIn("Synopsis", ref)
        # Les scripts techniques bruts NE sont PAS injectés en référence.
        self.assertNotIn("blender_script", ref)

    def test_resume_reference_absent_echoue_sur(self):
        # Projet inexistant : "" au lieu d'une exception.
        self.assertEqual(projets.resume_reference("inconnu", self.dossier), "")

    def test_enregistrer_production_sans_meta_ne_fait_rien(self):
        # Aucun meta : ne doit pas lever.
        projets.enregistrer_production("fantome", "aaaaaaaaaaaa",
                                       dossier=self.dossier)


class TestDossierSortie(unittest.TestCase):

    def test_par_defaut_output(self):
        avant = os.environ.pop("STUDIO_OUTPUT_DIR", None)
        try:
            self.assertTrue(shared_state.dossier_sortie().endswith("output"))
        finally:
            if avant is not None:
                os.environ["STUDIO_OUTPUT_DIR"] = avant

    def test_env_redirige_les_scripts(self):
        # C'est le levier que les agents (04–08) utilisent pour ranger leurs
        # scripts dans le dossier du projet quand --projet est actif.
        cible = os.path.join(tempfile.mkdtemp(), "projets", "alien")
        avant = os.environ.get("STUDIO_OUTPUT_DIR")
        os.environ["STUDIO_OUTPUT_DIR"] = cible
        try:
            self.assertEqual(shared_state.dossier_sortie(), cible)
        finally:
            if avant is None:
                os.environ.pop("STUDIO_OUTPUT_DIR", None)
            else:
                os.environ["STUDIO_OUTPUT_DIR"] = avant


class TestJournalProjet(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def test_projet_enregistre_dans_le_journal(self):
        j = JournalProduction(production_id="aaaaaaaaaaaa", dossier=self.dossier)
        j.demarrer_production("Un chat détective", modele="", projet="alien")
        prod = next(p for p in j.lister_productions() if p["id"] == "aaaaaaaaaaaa")
        self.assertEqual(prod["projet"], "alien")
        j.fermer()

    def test_reprise_sans_projet_conserve_le_projet(self):
        j = JournalProduction(production_id="bbbbbbbbbbbb", dossier=self.dossier)
        j.demarrer_production("Idée", projet="alien")
        # Reprise ultérieure sans repréciser le projet : il doit être conservé.
        j.demarrer_production("Idée", projet="")
        prod = next(p for p in j.lister_productions() if p["id"] == "bbbbbbbbbbbb")
        self.assertEqual(prod["projet"], "alien")
        j.fermer()


class TestCommandeLancement(unittest.TestCase):

    def test_projet_et_inspiration_dans_la_commande(self):
        cfg = ConfigAPI()
        cmd = commande_lancement(cfg, "aaaaaaaaaaaa", "une idée",
                                 modele="gpt-4o", projet="Alien 2",
                                 inspiration="Alien")
        self.assertIn("--projet", cmd)
        self.assertIn("Alien 2", cmd)
        self.assertIn("--inspiration", cmd)
        self.assertIn("Alien", cmd)

    def test_sans_projet_pas_d_option(self):
        cfg = ConfigAPI()
        cmd = commande_lancement(cfg, "aaaaaaaaaaaa", "une idée")
        self.assertNotIn("--projet", cmd)
        self.assertNotIn("--inspiration", cmd)


if __name__ == "__main__":
    unittest.main()
