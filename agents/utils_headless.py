"""
utils_headless.py — Génère les commandes prêtes à l'emploi pour exécuter
les livrables (scripts Blender / Unreal) en mode headless (sans interface).
"""

import os
import shutil


def commande_blender_headless(script_path: str) -> str:
    """
    Construit la commande pour exécuter un script Blender sans ouvrir l'interface.

    Args:
        script_path : Chemin vers le script Python Blender généré

    Returns:
        La commande shell prête à copier-coller
    """
    rel_path = os.path.relpath(script_path)
    return f"blender --background --python {rel_path}"


def commande_unreal_headless(script_path: str) -> str:
    """
    Construit la commande pour exécuter le script Unreal généré.
    Le script est déjà un .sh autonome (permissions d'exécution déjà posées).

    Args:
        script_path : Chemin vers le script Shell Unreal généré

    Returns:
        La commande shell prête à copier-coller
    """
    rel_path = os.path.relpath(script_path)
    return f"bash {rel_path}"


def afficher_commandes_headless(blender_path: str, unreal_path: str) -> None:
    """
    Affiche un bloc récapitulatif avec les commandes headless à copier-coller,
    et prévient si Blender n'est pas détecté sur cette machine.

    Args:
        blender_path : Chemin du script Blender généré
        unreal_path  : Chemin du script Unreal généré
    """
    print("\n" + "─" * 60)
    print("  ▶ COMMANDES PRÊTES À L'EMPLOI (mode headless)")
    print("─" * 60)

    print("\n  Blender (génère la scène 3D sans ouvrir l'interface) :")
    print(f"    {commande_blender_headless(blender_path)}")
    if shutil.which("blender") is None:
        print("    ⚠️  Blender n'est pas détecté sur cette machine.")
        print("       Copiez cette commande et lancez-la sur un ordinateur où Blender est installé.")

    print("\n  Unreal Engine (configure la scène cinématique) :")
    print(f"    {commande_unreal_headless(unreal_path)}")
    print("    ⚠️  Nécessite Unreal Engine 5 installé et son CLI configuré.")

    print("\n" + "─" * 60)


if __name__ == "__main__":
    # Test rapide avec des chemins fictifs
    afficher_commandes_headless(
        blender_path="agents/output/scene_01_opening.py",
        unreal_path="agents/output/setup_scene_01.sh",
    )
