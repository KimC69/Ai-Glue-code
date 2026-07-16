"""
test_univers.py — Tests unitaires du Générateur d'Univers.

Teste la gestion des projets, le découpage d'image et les clients sans appel
réseau (mocks). Nécessite Pillow.
"""

import json
import os
import tempfile
import unittest

from univers.projet_manager import (
    creer_ou_ouvrir, lister_projets, sauver_fiche, lire_fiche,
    lister_fiches, chemin_croquis, slugifier
)
from univers.agents.decoupeur_3d import Decoupeur3D


class TestProjets(unittest.TestCase):
    def setUp(self):
        self.dossier_temp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dossier_temp, ignore_errors=True)

    def test_slugifier_accents(self):
        self.assertEqual(slugifier("Alien 2 : le Retour"), "alien-2-le-retour")

    def test_creer_projet_structure(self):
        projet = creer_ou_ouvrir("Mon Jeu", self.dossier_temp)
        self.assertTrue(os.path.isdir(projet["chemin"]))
        for cat in ("characters", "objects", "flora"):
            self.assertTrue(os.path.isdir(
                os.path.join(projet["chemin"], "universe_bible", cat)))
            self.assertTrue(os.path.isdir(
                os.path.join(projet["chemin"], "sketches", cat)))
        self.assertTrue(os.path.isdir(
            os.path.join(projet["chemin"], "models")))

    def test_lister_projets_tri(self):
        import time
        creer_ou_ouvrir("Ancien", self.dossier_temp)
        time.sleep(1.1)  # modifie_le est à la seconde
        creer_ou_ouvrir("Recent", self.dossier_temp)
        projets = lister_projets(self.dossier_temp)
        self.assertEqual(projets[0]["nom"], "Recent")

    def test_sauver_lire_fiche(self):
        projet = creer_ou_ouvrir("Test", self.dossier_temp)
        sauver_fiche(projet, "characters", "Heros", {"nom": "Heros", "type": "Humain"})
        fiche = lire_fiche(projet, "characters", "Heros")
        self.assertEqual(fiche["nom"], "Heros")
        self.assertIn("Heros.json", lister_fiches(projet, "characters"))


class TestDecoupeur(unittest.TestCase):
    def setUp(self):
        self.dossier_temp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dossier_temp, ignore_errors=True)

    def test_decouper_3_vues(self):
        from PIL import Image
        chemin = os.path.join(self.dossier_temp, "sketch.png")
        img = Image.new("RGB", (300, 100), color=(255, 255, 255))
        img.save(chemin)

        decoupeur = Decoupeur3D()
        resultat = decoupeur.decouper(chemin, noms=("face", "profile", "back"))
        self.assertTrue(resultat["success"])
        self.assertEqual(len(resultat["vues"]), 3)
        for nom in ("face", "profile", "back"):
            self.assertTrue(os.path.exists(resultat["vues"][nom]))


if __name__ == "__main__":
    unittest.main()
