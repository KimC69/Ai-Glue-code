#!/usr/bin/env python3
"""
export_local.py — Prépare une archive autonome du Studio IA pour un PC local.

Ce script crée un fichier ZIP contenant le dossier `agents/` (code Python de
l'API/agent, PWA, outil desktop, builder APK) prêt à être décompressé sur un
ordinateur personnel. L'archive exclut les données générées (output/,
lancements_api/, builds Android, node_modules, etc.) pour rester légère.

Usage :
    cd agents
    python export_local.py

Résultat :
    ../studio-ia-local.zip

Une fois décompressé sur un PC, il suffit de :
    1. Installer Python 3.10+ et les dépendances Python (pip install -r requirements.txt).
    2. Installer Node.js + npm.
    3. Installer un JDK 17 et l'Android SDK (ou utiliser Android Studio).
    4. Lancer python api_serveur.py --hote 0.0.0.0 --port 8000.
    5. Générer l'APK : cd mobile-apk && python build_apk.py --api-url http://IP:8000.
"""

import os
import zipfile
from datetime import datetime
from pathlib import Path

DOSSIER_AGENTS = Path(__file__).resolve().parent
DOSSIER_PROJET = DOSSIER_AGENTS.parent
FICHIER_ZIP = DOSSIER_PROJET / "studio-ia-local.zip"

EXCLUSIONS = {
    # Données générées à l'exécution (ne jamais emporter).
    "output",
    "lancements_api",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    ".env.local",
    ".env.*",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    
    # Build mobile (se régénère sur le PC local).
    "mobile-apk/android",
    "mobile-apk/node_modules",
    "mobile-apk/dist",
    "mobile-apk/*.keystore",
    "mobile-apk/*.jks",
    "mobile-apk/.gradle",
}


DOSSIERS_EXCLUS = {
    "__pycache__",
    ".venv",
    "venv",
    "output",
    "lancements_api",
    "node_modules",
    "android",
    "dist",
    ".gradle",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

FICHIERS_EXCLUS = {
    ".env",
    ".env.local",
    ".env.production",
    ".coverage",
}

EXTENSIONS_EXCLUES = {
    ".pyc",
    ".pyo",
    ".egg-info",
    ".keystore",
    ".jks",
}


def devrait_exclure(chemin: Path, racine: Path) -> bool:
    """Détermine si un chemin relatif doit être ignoré dans l'archive."""
    rel_parts = chemin.relative_to(racine).parts
    nom = chemin.name

    # Exclure si l'un des segments du chemin est un dossier interdit.
    if any(part in DOSSIERS_EXCLUS for part in rel_parts):
        return True

    # Exclure certains fichiers par nom (mais garder .env.example).
    if nom in FICHIERS_EXCLUS:
        return True

    # Exclure par extension.
    if any(nom.endswith(ext) for ext in EXTENSIONS_EXCLUES):
        return True

    return False


def creer_archive():
    """Crée le ZIP autonome."""
    fichiers = 0
    octets = 0
    taille_max = 0

    with zipfile.ZipFile(FICHIER_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in sorted(DOSSIER_AGENTS.rglob("*")):
            if not chemin.is_file():
                continue
            if devrait_exclure(chemin, DOSSIER_AGENTS):
                continue

            arcname = str(chemin.relative_to(DOSSIER_PROJET))
            zf.write(chemin, arcname)
            taille = chemin.stat().st_size
            fichiers += 1
            octets += taille
            taille_max = max(taille_max, taille)

    print(f"Archive créée : {FICHIER_ZIP}")
    print(f"  Fichiers : {fichiers}")
    print(f"  Taille   : {octets / 1024 / 1024:.2f} Mo")
    print(f"\nPour l'utiliser : décompressez studio-ia-local.zip sur votre PC,")
    print("puis suivez agents/mobile-apk/README.md > 'Mode 100% local sans Replit'.")


if __name__ == "__main__":
    try:
        creer_archive()
    except Exception as e:
        print(f"Erreur lors de la création de l'archive : {e}", file=__import__("sys").stderr)
        raise
