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


def commande_inkscape_headless(notes_path: str) -> str:
    """
    L'Agent 06 fournit des notes décrivant l'illustration à créer, pas un
    fichier .svg déjà construit. On affiche donc la marche à suivre : créer
    le SVG à partir des notes, puis l'exporter en PNG/PDF sans interface.

    Args:
        notes_path : Chemin vers les notes d'illustration générées

    Returns:
        Un texte d'instructions (pas une commande one-shot)
    """
    rel_path = os.path.relpath(notes_path)
    return (
        f"1. Créez le fichier illustration.svg à partir des instructions dans {rel_path}\n"
        f"       2. Exportez-le sans ouvrir l'interface :\n"
        f"          inkscape illustration.svg --export-type=png --export-filename=illustration.png"
    )


def commande_darktable_headless(notes_path: str) -> str:
    """
    Construit la commande pour développer un fichier RAW en ligne de commande.

    Args:
        notes_path : Chemin vers les notes de développement générées

    Returns:
        Un texte d'instructions (le fichier RAW source n'est pas généré par le studio)
    """
    rel_path = os.path.relpath(notes_path)
    return (
        f"1. Consultez les réglages recommandés dans {rel_path}\n"
        f"       2. Développez en ligne de commande :\n"
        f"          darktable-cli photo_source.raw sortie.jpg"
    )


def commande_krita_headless(script_path: str) -> str:
    """
    Construit la commande pour exécuter un script Python (API Krita) en
    mode batch, sans ouvrir l'interface graphique.

    Args:
        script_path : Chemin vers le script généré par l'Agent 06

    Returns:
        La commande shell prête à copier-coller
    """
    rel_path = os.path.relpath(script_path)
    return f"krita --nosplash -b {rel_path}"


def commande_obs_headless(notes_path: str) -> str:
    """
    Construit la commande pour démarrer un enregistrement OBS sans ouvrir
    l'interface (nécessite un profil/une scène déjà configurés dans OBS).

    Args:
        notes_path : Chemin vers les notes de configuration générées

    Returns:
        Un texte d'instructions
    """
    rel_path = os.path.relpath(notes_path)
    return (
        f"1. Configurez la scène OBS selon {rel_path}\n"
        f"       2. Lancez l'enregistrement sans interface :\n"
        f"          obs --startrecording --minimize-to-tray"
    )


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
    inkscape_notes_path: str = "",
    darktable_notes_path: str = "",
    krita_path: str = "",
    obs_notes_path: str = "",
) -> None:
    """
    Affiche un bloc récapitulatif avec les commandes headless à copier-coller.
    N'affiche les commandes des outils annexes que si l'Agent 06 les a jugés
    nécessaires (chemin non vide) — aucun outil n'est proposé si le résultat
    est déjà conforme.

    Args:
        blender_path         : Chemin du script Blender généré (toujours affiché)
        unreal_path          : Chemin du script Unreal généré (toujours affiché)
        gimp_path            : Chemin du script GIMP, vide si non nécessaire
        montage_notes_path   : Chemin des notes de montage, vide si non nécessaire
        inkscape_notes_path  : Chemin des notes Inkscape, vide si non nécessaire
        darktable_notes_path : Chemin des notes Darktable, vide si non nécessaire
        krita_path           : Chemin du script Krita, vide si non nécessaire
        obs_notes_path       : Chemin des notes OBS, vide si non nécessaire
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

    if inkscape_notes_path:
        print("\n  Inkscape (illustration jugée nécessaire par le Superviseur Post-Production) :")
        print(f"    {commande_inkscape_headless(inkscape_notes_path)}")
        _verifier_outil("inkscape", "Inkscape")

    if darktable_notes_path:
        print("\n  Darktable (développement RAW jugé nécessaire) :")
        print(f"    {commande_darktable_headless(darktable_notes_path)}")
        _verifier_outil("darktable-cli", "Darktable")

    if krita_path:
        print("\n  Krita (dessin numérique jugé nécessaire) :")
        print(f"    {commande_krita_headless(krita_path)}")
        _verifier_outil("krita", "Krita")

    if obs_notes_path:
        print("\n  OBS Studio (capture/streaming jugée nécessaire) :")
        print(f"    {commande_obs_headless(obs_notes_path)}")
        _verifier_outil("obs", "OBS Studio")

    print("\n" + "─" * 60)


if __name__ == "__main__":
    # Test rapide avec des chemins fictifs
    afficher_commandes_headless(
        blender_path="agents/output/scene_01_opening.py",
        unreal_path="agents/output/setup_scene_01.sh",
    )
