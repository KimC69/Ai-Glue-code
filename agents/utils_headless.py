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


def commande_gimp_headless(script_path: str) -> str:
    """
    Construit la commande pour exécuter un script de retouche GIMP en batch,
    sans ouvrir l'interface graphique.

    Args:
        script_path : Chemin vers le script Python-Fu généré par l'Agent 06

    Returns:
        La commande shell prête à copier-coller
    """
    rel_path = os.path.relpath(script_path)
    return f"gimp -i -b - < {rel_path}"


def commande_montage_headless(notes_path: str) -> str:
    """
    Le montage (Kdenlive/Shotcut) n'a pas de vrai mode headless : les deux
    reposent sur le moteur MLT en interne. On ne peut donc pas exécuter
    automatiquement un montage sans projet .mlt/.kdenlive déjà construit ;
    on affiche donc la marche à suivre plutôt qu'une commande directe.

    Args:
        notes_path : Chemin vers le fichier de notes de montage généré

    Returns:
        Un texte d'instructions (pas une commande one-shot)
    """
    rel_path = os.path.relpath(notes_path)
    return (
        f"1. Ouvrez Kdenlive ou Shotcut et suivez les instructions dans {rel_path}\n"
        f"       2. Une fois le projet construit (.kdenlive ou .mlt), le rendu peut être automatisé :\n"
        f"          melt votre_projet.mlt -consumer avformat:sortie.mp4"
    )


def _verifier_outil(nom_binaire: str, nom_affiche: str) -> None:
    """Affiche un avertissement si un outil externe n'est pas détecté sur la machine."""
    if shutil.which(nom_binaire) is None:
        print(f"    ⚠️  {nom_affiche} n'est pas détecté sur cette machine.")
        print(f"       Copiez cette commande et lancez-la sur un ordinateur où {nom_affiche} est installé.")


def afficher_commandes_headless(
    blender_path: str,
    unreal_path: str,
    gimp_path: str = "",
    montage_notes_path: str = "",
) -> None:
    """
    Affiche un bloc récapitulatif avec les commandes headless à copier-coller.
    N'affiche les commandes GIMP / montage que si l'Agent 06 les a jugées
    nécessaires (gimp_path / montage_notes_path non vides) — aucun outil
    n'est proposé si le résultat est déjà conforme.

    Args:
        blender_path       : Chemin du script Blender généré (toujours affiché)
        unreal_path        : Chemin du script Unreal généré (toujours affiché)
        gimp_path          : Chemin du script GIMP, vide si retouche non nécessaire
        montage_notes_path : Chemin des notes de montage, vide si non nécessaire
    """
    print("\n" + "─" * 60)
    print("  ▶ COMMANDES PRÊTES À L'EMPLOI (mode headless)")
    print("─" * 60)

    print("\n  Blender (génère la scène 3D sans ouvrir l'interface) :")
    print(f"    {commande_blender_headless(blender_path)}")
    _verifier_outil("blender", "Blender")

    print("\n  Unreal Engine (configure la scène cinématique) :")
    print(f"    {commande_unreal_headless(unreal_path)}")
    print("    ⚠️  Nécessite Unreal Engine 5 installé et son CLI configuré.")

    if gimp_path:
        print("\n  GIMP (retouche jugée nécessaire par le Superviseur Post-Production) :")
        print(f"    {commande_gimp_headless(gimp_path)}")
        _verifier_outil("gimp", "GIMP")

    if montage_notes_path:
        print("\n  Montage vidéo (jugé nécessaire par le Superviseur Post-Production) :")
        print(f"    {commande_montage_headless(montage_notes_path)}")

    print("\n" + "─" * 60)


if __name__ == "__main__":
    # Test rapide avec des chemins fictifs
    afficher_commandes_headless(
        blender_path="agents/output/scene_01_opening.py",
        unreal_path="agents/output/setup_scene_01.sh",
    )
