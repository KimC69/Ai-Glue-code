#!/usr/bin/env python3
"""
build_apk.py — Génère un APK Android à partir de la PWA Studio IA.

Ce script automatise l'empaquetage Capacitor :
  1. Vérifie les prérequis (JDK, Android SDK).
  2. Installe les dépendances Node si nécessaire.
  3. Configure l'URL de l'API dans www/config.js.
  4. Ajoute la plateforme Android et synchronise les ressources.
  5. Compile le projet Android (debug ou release).
  6. Copie le APK produit dans agents/mobile-apk/dist/.

Usage :
    cd agents/mobile-apk
    python build_apk.py --api-url http://192.168.1.42:8000
    python build_apk.py --release --api-url http://192.168.1.42:8000

Prérequis :
    - JDK 17 (JAVA_HOME)
    - Android SDK avec build-tools 34, platform-tools, platform android-34
    - Node.js / npm

Sur Replit : ouvrir un shell via `nix-shell shell.nix` avant de lancer ce script.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DOSSIER_RACINE = Path(__file__).resolve().parent
DOSSIER_WWW = DOSSIER_RACINE / "www"
DOSSIER_ANDROID = DOSSIER_RACINE / "android"
DOSSIER_DIST = DOSSIER_RACINE / "dist"

CONFIG_JS = DOSSIER_WWW / "config.js"
APK_DEBUG_SRC = DOSSIER_ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
APK_RELEASE_SRC = DOSSIER_ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release-unsigned.apk"


def executer(cmd, cwd=None, env=None, check=True):
    """Exécute une commande shell, affiche la sortie, et lève en cas d'erreur."""
    print(f"\n▶ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Commande échouée : {' '.join(cmd)} (code {result.returncode})")
    return result


def verifier_prerequis():
    """Vérifie que Java, Android SDK et Node sont accessibles."""
    java = shutil.which("java")
    if not java:
        raise RuntimeError("Java non trouvé. Définissez JAVA_HOME ou lancez `nix-shell shell.nix`.")

    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk or not Path(sdk).is_dir():
        raise RuntimeError(
            "Android SDK non trouvé. Définissez ANDROID_HOME "
            "ou lancez `nix-shell shell.nix`."
        )

    node = shutil.which("node") and shutil.which("npm")
    if not node:
        raise RuntimeError("Node.js et npm sont requis.")

    print(f"✓ Java  : {java}")
    print(f"✓ SDK   : {sdk}")
    print(f"✓ Node  : {shutil.which('node')}")


def installer_dependances():
    """Installe les dépendances Capacitor si nécessaire."""
    if (DOSSIER_RACINE / "node_modules").is_dir():
        print("✓ node_modules déjà présent")
        return
    print("Installation des dépendances Capacitor…")
    executer(["npm", "install"], cwd=DOSSIER_RACINE)


def configurer_api(api_url: str):
    """Injecte l'URL de l'API dans www/config.js."""
    if not api_url:
        print("⚑ Aucune --api-url : config.js reste en mode web (même origine)")
        return

    # Validation légère pour éviter les injections grossières.
    if not re.match(r"^https?://[\w\-.]+(:\d+)?(/.*)?$", api_url):
        raise ValueError(f"URL d'API invalide : {api_url}")

    contenu = CONFIG_JS.read_text(encoding="utf-8")
    contenu = re.sub(
        r'window\.API_BASE_URL\s*=\s*"[^"]*";',
        f'window.API_BASE_URL = "{api_url}";',
        contenu,
    )
    CONFIG_JS.write_text(contenu, encoding="utf-8")
    print(f"✓ API configurée : {api_url}")


def ajouter_plateforme_android():
    """Ajoute le dossier android/ si nécessaire."""
    if DOSSIER_ANDROID.is_dir():
        print("✓ Plateforme Android déjà présente")
        return
    print("Ajout de la plateforme Android…")
    executer(["npx", "cap", "add", "android"], cwd=DOSSIER_RACINE)


def synchroniser():
    """Synchronise les ressources web avec le projet Android."""
    print("Synchronisation Capacitor…")
    executer(["npx", "cap", "sync", "android"], cwd=DOSSIER_RACINE)


def compiler(release: bool) -> Path:
    """Compile le projet Android et retourne le chemin du APK produit."""
    tache = "assembleRelease" if release else "assembleDebug"
    print(f"Compilation Gradle ({tache})…")

    gradlew = DOSSIER_ANDROID / "gradlew"
    if not gradlew.is_file():
        raise RuntimeError("Gradlew introuvable. La plateforme Android n'est pas initialisée.")

    executer([str(gradlew), tache], cwd=DOSSIER_ANDROID)

    src = APK_RELEASE_SRC if release else APK_DEBUG_SRC
    if not src.is_file():
        raise RuntimeError(f"APK attendu introuvable : {src}")
    return src


def copier_apk(source: Path, release: bool):
    """Copie le APK dans dist/ avec un nom explicite."""
    DOSSIER_DIST.mkdir(exist_ok=True)
    suffix = "release-unsigned" if release else "debug"
    dest = DOSSIER_DIST / f"studio-ia-regie-{suffix}.apk"
    shutil.copy2(source, dest)
    print(f"\n✓ APK généré : {dest}")
    print(f"  Taille : {dest.stat().st_size / 1024 / 1024:.2f} Mo")


def nettoyer():
    """Supprime les dossiers générés pour repartir de zéro."""
    for d in [DOSSIER_ANDROID, DOSSIER_RACINE / "node_modules", DOSSIER_DIST]:
        if d.is_dir():
            print(f"Suppression de {d}…")
            shutil.rmtree(d)


def main():
    parser = argparse.ArgumentParser(
        description="Génère un APK Android pour la régie Studio IA.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python build_apk.py --api-url http://192.168.1.42:8000
  python build_apk.py --release --api-url https://studio.example.com
  python build_apk.py --clean --api-url http://10.0.0.5:8000
        """,
    )
    parser.add_argument("--api-url", help="URL de l'API Studio IA (ex. http://IP:8000)")
    parser.add_argument("--release", action="store_true", help="Build release (non signé par défaut)")
    parser.add_argument("--clean", action="store_true", help="Supprime android/, node_modules/ et dist/ avant de rebuild")
    args = parser.parse_args()

    if args.clean:
        nettoyer()

    try:
        verifier_prerequis()
        installer_dependances()
        configurer_api(args.api_url)
        ajouter_plateforme_android()
        synchroniser()
        apk = compiler(args.release)
        copier_apk(apk, args.release)
    except RuntimeError as e:
        print(f"\n✗ ERREUR : {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERREUR INATTENDUE : {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
