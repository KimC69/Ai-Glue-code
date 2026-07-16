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
from univers.agents.modelisateur_blender import (
    _valider_script_blender, _detecter_blender, _extraire_couleurs_rgb,
    ModelisateurBlender
)


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


class TestValidateurScriptBlender(unittest.TestCase):
    """Valide que _valider_script_blender accepte les scripts légitimes
    et rejette les scripts dangereux ou syntaxiquement invalides."""

    _SCRIPT_VALIDE = """import bpy
import os
import math

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.89))
obj = bpy.context.active_object
obj.name = "hero_base"
obj.scale = (0.22, 0.15, 0.89)
bpy.ops.object.transform_apply(scale=True)
mat = bpy.data.materials.new(name="hero_mat_0")
mat.use_nodes = True
bpy.ops.wm.save_as_mainfile(filepath="/tmp/test/hero.blend")
"""

    def test_script_valide_accepte(self):
        ok, msg = _valider_script_blender(self._SCRIPT_VALIDE)
        self.assertTrue(ok, f"Script valide refusé : {msg}")

    def test_script_syntaxe_invalide_rejete(self):
        mauvais = "import bpy\nbpy.ops.object.select_all(action='SELECT'\n# parenthèse manquante"
        ok, msg = _valider_script_blender(mauvais)
        self.assertFalse(ok)
        self.assertIn("Syntaxe", msg)

    def test_import_dangereux_subprocess_rejete(self):
        script = "import bpy\nimport subprocess\nsubprocess.run(['rm', '-rf', '/'])"
        ok, msg = _valider_script_blender(script)
        self.assertFalse(ok)
        self.assertIn("subprocess", msg)

    def test_import_dangereux_socket_rejete(self):
        script = "import bpy\nimport socket\ns = socket.socket()"
        ok, msg = _valider_script_blender(script)
        self.assertFalse(ok)
        self.assertIn("socket", msg)

    def test_appel_exec_rejete(self):
        script = "import bpy\nexec('import os; os.system(\"id\")')"
        ok, msg = _valider_script_blender(script)
        self.assertFalse(ok)

    def test_fallback_statique_toujours_valide(self):
        """Le script statique généré par _script_fallback doit toujours passer
        la validation (c'est le filet de sécurité utilisé si le LLM échoue)."""
        fiche = {
            "nom": "TestEntite",
            "type": "Humain",
            "taille_cm": 170,
            "poids_kg": 65.0,
            "apparence": "cheveux blancs, manteau noir",
        }
        m = ModelisateurBlender()
        couleurs = _extraire_couleurs_rgb(fiche["apparence"])
        script = m._script_fallback(fiche, {}, "/tmp/test/test.blend", couleurs)
        ok, msg = _valider_script_blender(script)
        self.assertTrue(ok, f"Script fallback invalide : {msg}")


class TestDetectionBlender(unittest.TestCase):
    """Vérifie la cohérence de _detecter_blender : la commande retournée
    doit être exécutable et correspondre à ce que la détection a trouvé."""

    def test_retourne_trois_elements(self):
        resultat = _detecter_blender()
        self.assertEqual(len(resultat), 3,
                         "_detecter_blender doit retourner (disponible, version, commande)")

    def test_commande_coherente_avec_disponibilite(self):
        disponible, version, commande = _detecter_blender()
        if disponible:
            # La commande doit être non vide et exécutable
            self.assertIn(commande, ("blender", "blender3d"),
                          f"Commande inattendue : '{commande}'")
            self.assertTrue(version, "Version vide alors que Blender est disponible")
        else:
            # Si non disponible, la commande doit être vide
            self.assertEqual(commande, "",
                             "Commande non vide alors que Blender est indisponible")

    def test_script_fallback_executable_si_blender_disponible(self):
        """Si Blender est disponible, le script fallback (validé) doit
        s'exécuter sans erreur et produire le .blend."""
        disponible, _, commande = _detecter_blender()
        if not disponible:
            self.skipTest("Blender non disponible sur cet environnement")

        import subprocess, tempfile, re as _re
        fiche = {
            "nom": "TestBlenderExec",
            "type": "Objet",
            "taille_cm": 50,
            "poids_kg": 2.0,
            "apparence": "acier gris",
        }
        m = ModelisateurBlender()
        couleurs = _extraire_couleurs_rgb(fiche["apparence"])

        with tempfile.TemporaryDirectory() as tmp:
            chemin_blend = os.path.join(tmp, "TestBlenderExec.blend")
            script = m._script_fallback(fiche, {}, chemin_blend, couleurs)
            chemin_script = os.path.join(tmp, "test_exec.py")
            with open(chemin_script, "w", encoding="utf-8") as f:
                f.write(script)

            # Utilise la commande détectée, pas "blender" hardcodé
            result = subprocess.run(
                [commande, "--background", "--python", chemin_script],
                capture_output=True, text=True, timeout=60,
            )
            self.assertTrue(
                os.path.isfile(chemin_blend),
                f"Le .blend n'a pas été créé. stderr:\n{result.stderr[-500:]}"
            )


if __name__ == "__main__":
    unittest.main()
