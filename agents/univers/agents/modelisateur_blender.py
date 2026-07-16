"""
modelisateur_blender.py — Agent Modélisateur Blender 3D.

Lit la fiche JSON d'une entité (taille_cm, poids_kg, couleurs, apparence) et les
vues orthographiques (face, profil, dos) produites par le Découpeur 3D, puis :

1. Génère un script Python Blender complet (via LLM) qui :
   - place les 3 vues comme Images de Référence à la bonne échelle (1 BU = 1 m)
   - crée un cuboïde aux proportions taille_cm / poids_kg comme base de modélisation
   - crée des matériaux Principled BSDF avec les couleurs dominantes
   - sauvegarde le .blend

2. Si Blender est disponible en CLI (`blender --background`), exécute le script
   automatiquement et produit le .blend.

3. Sinon, enregistre le script .py avec des instructions d'usage manuel.

Sortie : ResultatModelisation3D (chemin script, chemin .blend, dimensions, couleurs)
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_base import BaseAgent
from univers.schemas import ResultatModelisation3D


# ── Helpers ──────────────────────────────────────────────────────────────────

def _detecter_blender() -> tuple[bool, str, str]:
    """Retourne (disponible, version, commande) pour Blender en ligne de commande.

    Essaie successivement 'blender' puis 'blender3d'.
    Retourne la commande qui a fonctionné, garantissant que l'exécution
    utilise exactement la même commande que la détection.
    """
    for cmd in ("blender", "blender3d"):
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = ""
                for ligne in result.stdout.splitlines():
                    if ligne.lower().startswith("blender"):
                        version = ligne.strip()
                        break
                return True, version, cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False, "", ""


# Modules autorisés dans un script Blender généré
_IMPORTS_AUTORISES = frozenset({"bpy", "os", "math", "json", "re", "pathlib"})

# Noms de fonctions builtin interdits (détectés via AST)
_BUILTINS_INTERDITS = frozenset({"exec", "eval", "compile", "__import__"})

# Modules réseau/système interdits (détectés via AST import + regex)
_MODULES_INTERDITS_RE = re.compile(
    r"\b(subprocess|socket|urllib|requests|http|ftplib|smtplib|"
    r"ctypes|cffi|importlib)\b",
    re.IGNORECASE,
)


def _valider_script_blender(script: str) -> tuple[bool, str]:
    """Valide un script Python Blender avant exécution headless.

    Contrôles effectués (tous via AST, pas de regex fragile) :
    1. Syntaxe Python valide via ast.parse().
    2. Seuls les modules de _IMPORTS_AUTORISES sont importés.
    3. Aucun appel aux builtins dangereux (exec, eval, compile, __import__).
    4. Aucune référence textuelle aux modules réseau/système interdits.

    Retourne (valide, message_erreur).
    """
    # 1. Syntaxe
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return False, f"Syntaxe invalide : {e}"

    # 2 & 3. Parcours AST unique pour imports + appels dangereux
    for node in ast.walk(tree):
        # Imports via `import X`
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_racine = alias.name.split(".")[0]
                if module_racine not in _IMPORTS_AUTORISES:
                    return False, (
                        f"Import non autorisé : '{alias.name}'. "
                        f"Seuls {sorted(_IMPORTS_AUTORISES)} sont permis."
                    )
        # Imports via `from X import Y`
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_racine = node.module.split(".")[0]
                if module_racine not in _IMPORTS_AUTORISES:
                    return False, (
                        f"Import non autorisé : 'from {node.module}'. "
                        f"Seuls {sorted(_IMPORTS_AUTORISES)} sont permis."
                    )
        # Appels à des builtins dangereux : exec(), eval(), compile(), __import__()
        elif isinstance(node, ast.Call):
            func = node.func
            nom_func = None
            if isinstance(func, ast.Name):
                nom_func = func.id
            elif isinstance(func, ast.Attribute):
                nom_func = func.attr
            if nom_func and nom_func in _BUILTINS_INTERDITS:
                return False, f"Appel dangereux détecté : '{nom_func}()'"

    # 4. Vérification textuelle des modules réseau/système (filet de sécurité)
    m = _MODULES_INTERDITS_RE.search(script)
    if m:
        return False, f"Module interdit référencé : '{m.group()}'"

    return True, ""


def _extraire_couleurs_rgb(apparence: str) -> list:
    """Extrait et convertit les couleurs nommées de la description en RGB [0-1]."""
    # Table de correspondance couleurs françaises → RGB (0-1)
    palette = {
        "blanc": [0.95, 0.95, 0.95], "white": [0.95, 0.95, 0.95],
        "noir": [0.05, 0.05, 0.05], "black": [0.05, 0.05, 0.05],
        "gris": [0.5, 0.5, 0.5], "gray": [0.5, 0.5, 0.5], "grey": [0.5, 0.5, 0.5],
        "brun": [0.4, 0.2, 0.1], "marron": [0.4, 0.2, 0.1], "brown": [0.4, 0.2, 0.1],
        "rouge": [0.8, 0.1, 0.1], "red": [0.8, 0.1, 0.1],
        "bleu": [0.1, 0.3, 0.8], "blue": [0.1, 0.3, 0.8],
        "vert": [0.1, 0.6, 0.1], "green": [0.1, 0.6, 0.1],
        "jaune": [0.9, 0.8, 0.1], "yellow": [0.9, 0.8, 0.1],
        "or": [0.8, 0.6, 0.1], "gold": [0.8, 0.6, 0.1], "doré": [0.8, 0.6, 0.1],
        "argent": [0.75, 0.75, 0.75], "silver": [0.75, 0.75, 0.75],
        "cuir": [0.35, 0.18, 0.08], "leather": [0.35, 0.18, 0.08],
        "obsidienne": [0.05, 0.05, 0.07], "obsidian": [0.05, 0.05, 0.07],
        "amber": [0.8, 0.5, 0.1], "ambre": [0.8, 0.5, 0.1],
        "pierre": [0.55, 0.52, 0.48], "stone": [0.55, 0.52, 0.48],
        "acier": [0.6, 0.65, 0.7], "steel": [0.6, 0.65, 0.7],
        "bronze": [0.55, 0.35, 0.15],
        "chair": [0.9, 0.75, 0.65], "skin": [0.9, 0.75, 0.65],
        "roux": [0.7, 0.3, 0.05], "auburn": [0.65, 0.2, 0.05],
        "luminescent": [0.3, 0.5, 1.0], "luminescente": [0.3, 0.5, 1.0],
    }
    texte = apparence.lower()
    trouvees = []
    for mot, rgb in palette.items():
        if mot in texte and rgb not in trouvees:
            trouvees.append(rgb)
    # Toujours au moins une couleur de base
    if not trouvees:
        trouvees.append([0.7, 0.7, 0.7])
    return trouvees[:5]  # Maximum 5 matériaux


class _ScriptBlenderSchema:
    """Pseudo-schéma : l'agent retourne directement le script Python Blender en texte."""
    pass


class ModelisateurBlender(BaseAgent):
    """Agent qui génère un script Python Blender depuis une fiche d'entité."""

    SYSTEM_PROMPT = """Tu es un expert en scripting Blender Python (bpy).
Tu reçois la fiche d'identité d'une entité fictive (personnage, objet, plante)
et tu génères un script Python complet et fonctionnel pour Blender 4.x.

Règles strictes :
- Le script doit utiliser uniquement l'API bpy standard, sans addon externe.
- 1 Blender Unit = 1 mètre. Convertis taille_cm / 100 pour l'échelle réelle.
- Chaque vue de référence (face, profil, dos) est placée comme un Empty Image
  dans le bon plan orthogonal :
    face    → axe -Y (vue de face)
    profile → axe +X (vue de droite)
    back    → axe +Y (vue de dos)
- Le cuboïde de base représente le volume global de l'entité :
    hauteur = taille_cm / 100
    largeur = estimation proportionnelle au type
    profondeur = estimation proportionnelle au type
- Crée un matériau Principled BSDF par couleur importante.
- Sauvegarde le fichier .blend via bpy.ops.wm.save_as_mainfile.
- Commence directement par le code Python, sans explications.
- N'utilise PAS de commentaires markdown (pas de ```, pas de ```python).
"""

    USER_PROMPT = """Génère le script Python Blender pour cette entité :

Nom : {nom}
Type : {type_entite}
Taille : {taille_cm} cm
Poids : {poids_kg} kg
Apparence : {apparence}
Tags visuels : {tags_visuels}

Chemins des vues de référence (peut être vide si pas encore générées) :
- Face    : {vue_face}
- Profil  : {vue_profile}
- Dos     : {vue_back}

Couleurs RGB extraites : {couleurs_rgb}

Chemin de sauvegarde du .blend : {chemin_blend}

Génère uniquement le code Python Blender complet. Pas de markdown, pas d'explication.
"""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.2):
        # BaseAgent attend un output_schema Pydantic ; on passe dict car on récupère
        # le texte brut du script directement, pas un JSON structuré.
        super().__init__(model, temperature, dict, agent_id="Modélisateur Blender")
        # Reconstruction manuelle du prompt (on ne passe pas par base_parser ici)
        from langchain.prompts import ChatPromptTemplate
        self._prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self.USER_PROMPT),
        ])

    def _generer_script(self, fiche: dict, vues: dict, chemin_blend: str,
                        couleurs_rgb: list) -> str:
        """Appelle le LLM et retourne le script Python Blender brut."""
        messages = self._prompt_template.format_messages(
            nom=fiche.get("nom", "entite"),
            type_entite=fiche.get("type", ""),
            taille_cm=fiche.get("taille_cm") or 170,
            poids_kg=fiche.get("poids_kg") or 70.0,
            apparence=fiche.get("apparence", ""),
            tags_visuels=", ".join(fiche.get("tags_visuels", [])),
            vue_face=vues.get("face", ""),
            vue_profile=vues.get("profile", ""),
            vue_back=vues.get("back", ""),
            couleurs_rgb=json.dumps(couleurs_rgb),
            chemin_blend=chemin_blend,
        )
        reponse = self.llm.invoke(messages)
        texte = reponse.content.strip()
        # Nettoie les balises markdown si l'LLM en a quand même mis
        texte = re.sub(r"^```python\s*", "", texte)
        texte = re.sub(r"^```\s*", "", texte)
        texte = re.sub(r"\s*```$", "", texte)
        return texte

    def _script_fallback(self, fiche: dict, vues: dict,
                         chemin_blend: str, couleurs_rgb: list) -> str:
        """Script Blender de secours généré statiquement sans LLM."""
        nom = fiche.get("nom", "entite").replace("'", "_").replace(" ", "_")
        taille_m = (fiche.get("taille_cm") or 170) / 100.0
        poids = fiche.get("poids_kg") or 70.0
        # Estimation de largeur/profondeur proportionnelle au poids et au type
        type_e = (fiche.get("type") or "").lower()
        if any(k in type_e for k in ("humain", "elf", "human", "créature")):
            largeur_m = round(taille_m * 0.25, 3)
            profondeur_m = round(taille_m * 0.15, 3)
        elif any(k in type_e for k in ("animal", "loup", "chien", "cheval")):
            largeur_m = round(taille_m * 0.40, 3)
            profondeur_m = round(taille_m * 0.80, 3)
        else:
            largeur_m = round(taille_m * 0.35, 3)
            profondeur_m = round(taille_m * 0.35, 3)

        # Génération des blocs de matériaux
        mat_lines = []
        for i, rgb in enumerate(couleurs_rgb):
            r, g, b = rgb[0], rgb[1], rgb[2]
            mat_lines.append(f"""
mat_{i} = bpy.data.materials.new(name="{nom}_mat_{i}")
mat_{i}.use_nodes = True
bsdf_{i} = mat_{i}.node_tree.nodes.get("Principled BSDF")
if bsdf_{i}:
    bsdf_{i}.inputs["Base Color"].default_value = ({r}, {g}, {b}, 1.0)
""")

        # Blocs d'images de référence
        ref_lines = []
        ref_configs = [
            ("face", vues.get("face", ""), (0, -taille_m * 1.5, taille_m / 2),
             (1.5708, 0, 0), "FRONT"),
            ("profile", vues.get("profile", ""), (taille_m * 1.5, 0, taille_m / 2),
             (1.5708, 0, -1.5708), "RIGHT"),
            ("back", vues.get("back", ""), (0, taille_m * 1.5, taille_m / 2),
             (1.5708, 0, 3.1416), "BACK"),
        ]
        for nom_vue, chemin_vue, loc, rot, side in ref_configs:
            if chemin_vue and os.path.exists(chemin_vue):
                safe_path = chemin_vue.replace("\\", "/")
                ref_lines.append(f"""
# Vue {nom_vue}
empty_{nom_vue} = bpy.data.objects.new("{nom}_{nom_vue}_ref", None)
empty_{nom_vue}.empty_display_type = "IMAGE"
img_{nom_vue} = bpy.data.images.load("{safe_path}", check_existing=True)
empty_{nom_vue}.data = img_{nom_vue}
empty_{nom_vue}.empty_image_side = "{side}"
empty_{nom_vue}.location = {loc}
empty_{nom_vue}.rotation_euler = {rot}
empty_{nom_vue}.scale = ({taille_m}, {taille_m}, {taille_m})
bpy.context.collection.objects.link(empty_{nom_vue})
""")

        script = f"""import bpy
import os

# ── Nettoyage de la scène ─────────────────────────────────────────────────────
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
for block in bpy.data.meshes:
    bpy.data.meshes.remove(block)

# ── Échelle : 1 Blender Unit = 1 mètre ───────────────────────────────────────
# Entité : {fiche.get('nom', 'entite')} | Type : {fiche.get('type', '')}
# Taille réelle : {fiche.get('taille_cm', 170)} cm
# Poids estimé : {fiche.get('poids_kg', 70)} kg

TAILLE_M = {taille_m}
LARGEUR_M = {largeur_m}
PROFONDEUR_M = {profondeur_m}

# ── Mesh de base (cuboïde aux dimensions réelles) ─────────────────────────────
bpy.ops.mesh.primitive_cube_add(
    size=1,
    location=(0, 0, TAILLE_M / 2)
)
mesh_base = bpy.context.active_object
mesh_base.name = "{nom}_base"
mesh_base.scale = (LARGEUR_M / 2, PROFONDEUR_M / 2, TAILLE_M / 2)
bpy.ops.object.transform_apply(scale=True)

# ── Matériaux Principled BSDF ─────────────────────────────────────────────────
{''.join(mat_lines)}

# Application du premier matériau sur le mesh de base
if bpy.data.materials.get("{nom}_mat_0"):
    mesh_base.data.materials.append(bpy.data.materials["{nom}_mat_0"])

# ── Images de référence orthographiques ──────────────────────────────────────
{''.join(ref_lines) if ref_lines else '# (aucune vue de référence fournie)'}

# ── Éclairage et caméra de base ───────────────────────────────────────────────
bpy.ops.object.light_add(type="SUN", location=(5, -5, 10))
bpy.ops.object.camera_add(location=(0, -3, TAILLE_M * 0.75))
bpy.context.scene.camera = bpy.context.active_object

# ── Sauvegarde du .blend ──────────────────────────────────────────────────────
blend_path = r"{chemin_blend}"
os.makedirs(os.path.dirname(blend_path), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[Modélisateur Blender] Sauvegardé → {{blend_path}}")
"""
        return script

    def generer(self, fiche: dict, vues: dict, dossier_3d: str,
                utiliser_llm: bool = True) -> ResultatModelisation3D:
        """Génère le script Blender, l'exécute si possible, et retourne le résultat.

        Args:
            fiche        : dict de la FicheEntite
            vues         : dict {'face': chemin, 'profile': chemin, 'back': chemin}
            dossier_3d   : dossier de sortie pour le script et le .blend
            utiliser_llm : si True, le script est généré par l'agent LLM (plus riche)
        """
        os.makedirs(dossier_3d, exist_ok=True)
        nom_safe = re.sub(r"[^\w\-]", "_", fiche.get("nom", "entite"))
        chemin_script = os.path.join(dossier_3d, f"{nom_safe}_blender.py")
        chemin_blend = os.path.join(dossier_3d, f"{nom_safe}.blend")

        taille_cm = int(fiche.get("taille_cm") or 170)
        poids_kg = float(fiche.get("poids_kg") or 70.0)
        couleurs_rgb = _extraire_couleurs_rgb(fiche.get("apparence", ""))

        # Génération du script
        try:
            if utiliser_llm:
                script = self._generer_script(fiche, vues, chemin_blend, couleurs_rgb)
            else:
                script = self._script_fallback(fiche, vues, chemin_blend, couleurs_rgb)
        except Exception as e:
            # Fallback si le LLM échoue
            print(f"[Modélisateur Blender] LLM échec ({e}), utilisation du script statique")
            script = self._script_fallback(fiche, vues, chemin_blend, couleurs_rgb)

        # Écriture du script
        with open(chemin_script, "w", encoding="utf-8") as f:
            f.write(script)

        # ── Validation de sécurité avant toute exécution ─────────────────────
        valide, raison_rejet = _valider_script_blender(script)
        if not valide:
            # Script invalide : on le conserve pour inspection mais on n'exécute pas
            print(f"[Modélisateur Blender] Script rejeté par validation : {raison_rejet}")
            print("[Modélisateur Blender] Bascule sur le script statique (fallback)...")
            script = self._script_fallback(fiche, vues, chemin_blend, couleurs_rgb)
            with open(chemin_script, "w", encoding="utf-8") as f:
                f.write(script)
            valide, raison_rejet = _valider_script_blender(script)
            if not valide:
                # Le fallback statique doit toujours être valide ; si non, on s'arrête
                return ResultatModelisation3D(
                    chemin_script=chemin_script,
                    chemin_blend="",
                    dossier_3d=dossier_3d,
                    taille_cm=taille_cm,
                    poids_kg=poids_kg,
                    couleurs=couleurs_rgb,
                    vues_reference=vues,
                    blender_disponible=False,
                    blender_version="",
                    erreur=f"Script invalide (même le fallback) : {raison_rejet}",
                )

        # ── Détection et exécution de Blender ────────────────────────────────
        # _detecter_blender() retourne la commande qui a répondu ; on l'utilise
        # pour l'exécution, garantissant cohérence détection/exécution.
        blender_ok, blender_version, blender_cmd = _detecter_blender()
        chemin_blend_final = ""
        erreur = ""

        if blender_ok:
            try:
                result = subprocess.run(
                    [blender_cmd, "--background", "--python", chemin_script],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0 and os.path.isfile(chemin_blend):
                    chemin_blend_final = chemin_blend
                    print(f"[Modélisateur Blender] .blend généré → {chemin_blend}")
                else:
                    # On conserve les 30 dernières lignes de stderr pour le debug
                    stderr_lignes = (result.stderr or "").splitlines()
                    stderr_extrait = "\n".join(stderr_lignes[-30:])
                    erreur = stderr_extrait or "Blender a échoué (returncode non nul)"
                    print(f"[Modélisateur Blender] Blender a échoué : {erreur[:200]}")
            except subprocess.TimeoutExpired:
                erreur = "Blender a dépassé le délai (120s)"
                print(f"[Modélisateur Blender] {erreur}")
            except Exception as e:
                erreur = str(e)
        else:
            print("[Modélisateur Blender] Blender non trouvé. Script enregistré pour usage manuel.")
            # Ajoute un README d'instructions
            readme = os.path.join(dossier_3d, "COMMENT_UTILISER.md")
            with open(readme, "w", encoding="utf-8") as f:
                f.write(f"""# Modèle 3D — {fiche.get('nom', 'entite')}

## Script généré
`{os.path.basename(chemin_script)}`

## Pour créer le .blend

1. Installez **Blender** (https://www.blender.org/download/) version 4.x
2. Ouvrez un terminal dans ce dossier
3. Exécutez :

```bash
blender --background --python {os.path.basename(chemin_script)}
```

Cela créera `{os.path.basename(chemin_blend)}` avec :
- Le cuboïde aux dimensions réelles ({taille_cm} cm de haut)
- Les images de référence face/profil/dos positionnées
- Les matériaux de base avec les couleurs extraites de la fiche

## Ouvrir dans Blender
Double-cliquez sur `{os.path.basename(chemin_blend)}` une fois généré.
""")

        return ResultatModelisation3D(
            chemin_script=chemin_script,
            chemin_blend=chemin_blend_final,
            dossier_3d=dossier_3d,
            taille_cm=taille_cm,
            poids_kg=poids_kg,
            couleurs=couleurs_rgb,
            vues_reference=vues,
            blender_disponible=blender_ok,
            blender_version=blender_version,
            erreur=erreur,
        )
