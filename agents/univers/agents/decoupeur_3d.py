"""
decoupeur_3d.py — Agent Découpeur 3D (équivalent Agent 05).

Découpe un croquis technique en vues orthographiques (face, profil, dos) pour
préparer la modélisation 3D. Les vues sont enregistrées à côté du croquis source.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent


class Decoupeur3D(BaseAgent):
    """Agent qui découpe un croquis en vues orthographiques."""

    def __init__(self, model="gpt-4o-mini", temperature=0.0):
        super().__init__(model, temperature, dict, agent_id="Découpeur 3D")

    def decouper(self, chemin_image: str, dossier_sortie: str = "",
                 noms: tuple = ("face", "profile", "back")) -> dict:
        """Découpe une image en 3 bandes verticales (face, profil, dos) et
        sauvegarde chaque vue. Retourne les chemins générés."""
        try:
            from PIL import Image
        except ImportError as e:
            return {"success": False, "error": f"PIL (Pillow) requis : {e}"}

        if not os.path.isfile(chemin_image):
            return {"success": False, "error": f"Image introuvable : {chemin_image}"}

        try:
            img = Image.open(chemin_image)
        except Exception as e:
            return {"success": False, "error": f"Impossible d'ouvrir l'image : {e}"}

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        largeur, hauteur = img.size
        if largeur < 3:
            return {"success": False, "error": "Image trop petite pour découper."}

        # Découpe en 3 bandes verticales égales
        bande = largeur // 3
        vues = {}
        os.makedirs(dossier_sortie or os.path.dirname(chemin_image), exist_ok=True)

        for i, nom in enumerate(noms):
            x0 = i * bande
            x1 = (i + 1) * bande if i < 2 else largeur
            vue = img.crop((x0, 0, x1, hauteur))
            base = os.path.splitext(os.path.basename(chemin_image))[0]
            chemin_vue = os.path.join(
                dossier_sortie or os.path.dirname(chemin_image),
                f"{base}_{nom}.png"
            )
            vue.save(chemin_vue, "PNG")
            vues[nom] = chemin_vue

        return {
            "success": True,
            "vues": vues,
            "dimensions": {"largeur": largeur, "hauteur": hauteur},
            "source": chemin_image,
        }

    def decouper_grid(self, chemin_image: str, dossier_sortie: str = "",
                      lignes: int = 1, colonnes: int = 3) -> dict:
        """Découpe une image en grille régulière (ex: 1x3)."""
        try:
            from PIL import Image
        except ImportError as e:
            return {"success": False, "error": f"PIL (Pillow) requis : {e}"}

        if not os.path.isfile(chemin_image):
            return {"success": False, "error": f"Image introuvable : {chemin_image}"}

        img = Image.open(chemin_image)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        largeur, hauteur = img.size
        w = largeur // colonnes
        h = hauteur // lignes
        vues = {}
        os.makedirs(dossier_sortie or os.path.dirname(chemin_image), exist_ok=True)

        idx = 0
        for li in range(lignes):
            for co in range(colonnes):
                x0 = co * w
                y0 = li * h
                x1 = largeur if co == colonnes - 1 else (co + 1) * w
                y1 = hauteur if li == lignes - 1 else (li + 1) * h
                vue = img.crop((x0, y0, x1, y1))
                base = os.path.splitext(os.path.basename(chemin_image))[0]
                chemin_vue = os.path.join(
                    dossier_sortie or os.path.dirname(chemin_image),
                    f"{base}_vue_{idx}.png"
                )
                vue.save(chemin_vue, "PNG")
                vues[f"vue_{idx}"] = chemin_vue
                idx += 1

        return {
            "success": True,
            "vues": vues,
            "dimensions": {"largeur": largeur, "hauteur": hauteur},
            "source": chemin_image,
        }

    def discuter(self, message: str, role: str = "", contexte: str = "") -> str:
        return super().discuter(message, role or "Découpeur 3D", contexte)
