"""
bootstrap.py — Vérification et réparation automatique de l'environnement Studio IA.

Vérifie que tous les logiciels requis (Blender, ComfyUI, A1111, Python packages)
sont présents et à la bonne version. Crée `.studio_env_validated` si tout est OK.

Utilisation CLI :
    python agents/bootstrap.py [--reparer]

Utilisation programmatique :
    from bootstrap import BootstrapEnvironnement
    bs = BootstrapEnvironnement()
    rapport = bs.verifier_tout()
    bs.afficher_rapport(rapport)
"""

import importlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
import urllib.error
from typing import Optional


# Chemin de ce fichier → racine agents/
RACINE_AGENTS = os.path.dirname(os.path.abspath(__file__))
FICHIER_REQUIREMENTS = os.path.join(RACINE_AGENTS, "requirements_logiciels.json")
FICHIER_VALIDATION = os.path.join(RACINE_AGENTS, ".studio_env_validated")


def _lire_requirements() -> list:
    """Lit requirements_logiciels.json (échoue sûr)."""
    try:
        with open(FICHIER_REQUIREMENTS, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("logiciels", [])
    except (OSError, ValueError):
        return []


def _comparer_versions(v_trouvee: str, v_min: str) -> bool:
    """Retourne True si v_trouvee >= v_min (comparaison tuple d'entiers)."""
    def _tuple(v):
        parts = re.findall(r"\d+", v)
        return tuple(int(x) for x in parts[:3])
    try:
        return _tuple(v_trouvee) >= _tuple(v_min)
    except Exception:
        return False


class BootstrapEnvironnement:
    """Vérifie et répare l'environnement logiciel du Studio IA."""

    def __init__(self):
        self.logiciels = _lire_requirements()
        self.systeme = platform.system()  # "Linux", "Windows", "Darwin"

    # ── Vérification ──────────────────────────────────────────────────────────

    def verifier_tout(self) -> dict:
        """Vérifie tous les logiciels et retourne un rapport structuré.

        Rapport : {
          "tous_ok": bool,
          "systeme": str,
          "items": [
            {
              "id": str, "nom": str, "statut": "ok"|"absent"|"vieux"|"non_verifie",
              "version_trouvee": str|None, "version_min": str|None,
              "message": str, "obligatoire": bool, "action": str|None
            }, ...
          ]
        }
        """
        items = []
        for spec in self.logiciels:
            t = spec.get("type", "binaire")
            if t == "binaire" or "commandes_detection" in spec:
                item = self._verifier_binaire(spec)
            elif t == "service_http":
                item = self._verifier_service_http(spec)
            elif t == "pip":
                item = self._verifier_pip(spec)
            else:
                item = {
                    "id": spec.get("id", "?"),
                    "nom": spec.get("nom", "?"),
                    "statut": "non_verifie",
                    "version_trouvee": None,
                    "version_min": None,
                    "message": "Type de vérification inconnu",
                    "obligatoire": spec.get("obligatoire", False),
                    "action": None,
                }
            items.append(item)

        tous_ok = all(
            i["statut"] in ("ok", "non_verifie")
            for i in items
            if i.get("obligatoire", False)
        )

        return {
            "tous_ok": tous_ok,
            "systeme": self.systeme,
            "items": items,
        }

    def _verifier_binaire(self, spec: dict) -> dict:
        """Vérifie un exécutable CLI (ex : Blender)."""
        commandes = spec.get("commandes_detection", [spec.get("id", "")])
        arg_version = spec.get("arg_version", "--version")
        regex = spec.get("regex_version", r"(\d+\.\d+(?:\.\d+)?)")
        version_min = spec.get("version_min")

        version_trouvee = None
        commande_ok = None

        for cmd in commandes:
            try:
                res = subprocess.run(
                    [cmd, arg_version],
                    capture_output=True, text=True, timeout=10
                )
                texte = (res.stdout or "") + (res.stderr or "")
                m = re.search(regex, texte)
                if m:
                    version_trouvee = m.group(1)
                    commande_ok = cmd
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        if version_trouvee is None:
            return {
                "id": spec["id"],
                "nom": spec["nom"],
                "statut": "absent",
                "version_trouvee": None,
                "version_min": version_min,
                "message": f"{spec['nom']} introuvable sur ce PC.",
                "obligatoire": spec.get("obligatoire", False),
                "action": spec.get("install_note", "Installez depuis le site officiel."),
            }

        ok = _comparer_versions(version_trouvee, version_min) if version_min else True
        return {
            "id": spec["id"],
            "nom": spec["nom"],
            "statut": "ok" if ok else "vieux",
            "version_trouvee": version_trouvee,
            "version_min": version_min,
            "commande": commande_ok,
            "message": (
                f"{spec['nom']} {version_trouvee} ✅"
                if ok
                else f"{spec['nom']} {version_trouvee} trop ancien (minimum {version_min})."
            ),
            "obligatoire": spec.get("obligatoire", False),
            "action": None if ok else spec.get("install_note"),
        }

    def _verifier_service_http(self, spec: dict) -> dict:
        """Vérifie qu'un service HTTP local répond (ComfyUI / A1111)."""
        env_var = spec.get("env_var_url", "")
        url = os.environ.get(env_var, spec.get("url_defaut", ""))
        disponible = False
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as r:
                disponible = r.status < 500
        except Exception:
            disponible = False

        return {
            "id": spec["id"],
            "nom": spec["nom"],
            "statut": "ok" if disponible else "absent",
            "version_trouvee": None,
            "version_min": None,
            "url": url,
            "message": (
                f"{spec['nom']} répond sur {url} ✅"
                if disponible
                else f"{spec['nom']} ne répond pas sur {url}."
            ),
            "obligatoire": spec.get("obligatoire", False),
            "action": None if disponible else spec.get("install_note"),
        }

    def _verifier_pip(self, spec: dict) -> dict:
        """Vérifie les packages Python critiques."""
        packages_critiques = spec.get("packages_critiques", [])
        manquants = []
        for pkg in packages_critiques:
            # Normalise le nom (tirets → underscores)
            nom_module = pkg.replace("-", "_")
            try:
                importlib.import_module(nom_module.split(".")[0])
            except ImportError:
                manquants.append(pkg)

        if manquants:
            return {
                "id": spec["id"],
                "nom": spec["nom"],
                "statut": "absent",
                "version_trouvee": None,
                "version_min": None,
                "message": f"Paquets manquants : {', '.join(manquants)}",
                "obligatoire": spec.get("obligatoire", True),
                "action": f"Lancez : pip install -r {spec.get('fichier_requirements', 'requirements.txt')}",
            }

        return {
            "id": spec["id"],
            "nom": spec["nom"],
            "statut": "ok",
            "version_trouvee": "installés",
            "version_min": None,
            "message": f"Paquets Python ✅ ({len(packages_critiques)} vérifiés)",
            "obligatoire": spec.get("obligatoire", True),
            "action": None,
        }

    # ── Réparation automatique ─────────────────────────────────────────────────

    def reparer_blender_linux(self) -> str:
        """Tente d'installer Blender via apt sur Linux. Retourne le résultat."""
        if self.systeme != "Linux":
            return "Installation automatique disponible sur Linux uniquement."
        try:
            res = subprocess.run(
                ["apt-get", "install", "-y", "blender"],
                capture_output=True, text=True, timeout=120
            )
            if res.returncode == 0:
                return "✅ Blender installé via apt."
            return f"❌ apt-get a échoué : {res.stderr[:300]}"
        except Exception as e:
            return f"❌ Impossible de lancer apt-get : {e}"

    def reparer_pip(self) -> str:
        """Installe les paquets Python manquants via pip."""
        req_path = os.path.join(RACINE_AGENTS, "requirements.txt")
        if not os.path.isfile(req_path):
            return "❌ requirements.txt introuvable."
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path],
                capture_output=True, text=True, timeout=120
            )
            if res.returncode == 0:
                return "✅ Paquets Python installés."
            return f"❌ pip a échoué : {res.stderr[:300]}"
        except Exception as e:
            return f"❌ Erreur pip : {e}"

    # ── Validation ────────────────────────────────────────────────────────────

    def marquer_valide(self) -> None:
        """Crée `.studio_env_validated` pour signaler que l'env est prêt."""
        try:
            with open(FICHIER_VALIDATION, "w", encoding="utf-8") as f:
                import datetime
                f.write(datetime.datetime.now().isoformat())
        except OSError:
            pass

    @staticmethod
    def est_valide() -> bool:
        """Retourne True si `.studio_env_validated` existe."""
        return os.path.isfile(FICHIER_VALIDATION)

    @staticmethod
    def invalider() -> None:
        """Supprime `.studio_env_validated` pour forcer une re-vérification."""
        try:
            os.remove(FICHIER_VALIDATION)
        except OSError:
            pass

    # ── Affichage CLI ─────────────────────────────────────────────────────────

    @staticmethod
    def afficher_rapport(rapport: dict) -> None:
        """Affiche le rapport de vérification dans le terminal."""
        print(f"\n🖥️  Vérification de l'environnement Studio IA ({rapport['systeme']})")
        print("=" * 60)
        for item in rapport["items"]:
            icone = {"ok": "✅", "absent": "❌", "vieux": "⚠️", "non_verifie": "ℹ️"}.get(
                item["statut"], "?"
            )
            print(f"  {icone}  {item['message']}")
            if item.get("action"):
                print(f"      → {item['action']}")
        print()
        if rapport["tous_ok"]:
            print("✅ Environnement prêt.")
        else:
            print("⚠️  Des composants obligatoires sont manquants ou incorrects.")
        print()


# ── Point d'entrée CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    reparer = "--reparer" in sys.argv
    bs = BootstrapEnvironnement()
    rapport = bs.verifier_tout()
    bs.afficher_rapport(rapport)

    if reparer:
        print("🔧 Mode réparation activé…")
        for item in rapport["items"]:
            if item["statut"] in ("absent", "vieux"):
                if item["id"] == "blender":
                    print(bs.reparer_blender_linux())
                elif item["id"] == "python_packages":
                    print(bs.reparer_pip())
        # Re-vérifie
        rapport = bs.verifier_tout()
        bs.afficher_rapport(rapport)

    if rapport["tous_ok"]:
        bs.marquer_valide()
        sys.exit(0)
    else:
        sys.exit(1)
