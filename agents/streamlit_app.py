"""
streamlit_app.py — Interface du Studio IA - Générateur d'Univers.

Permet de :
- sélectionner ou créer un projet (menu déroulant en haut) ;
- configurer les API (Stable Diffusion, Civitai, OpenAI) ;
- générer une fiche + croquis + découpes 3D par entité ;
- explorer la bible du projet (fiches JSON, croquis, découpes).

Lancement :
    cd agents/
    streamlit run streamlit_app.py --server.port 5000
"""

import json
import os
import sys

# Assure que agents/ est dans le path pour les imports absolus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from univers.config import ConfigUnivers, config_defaut
from univers.projet_manager import (
    creer_ou_ouvrir, lister_projets, lister_fiches, lister_croquis,
    lire_fiche, chemin_modeles, CATEGORIES
)
from univers.orchestrateur_univers import OrchestrateurUnivers, ErreurWorkflowUnivers
from univers.projet_manager import chemin_3d


# ── Configuration de la page ───────────────────────────────────────────────
st.set_page_config(
    page_title="Studio IA - Générateur d'Univers",
    page_icon="🌌",
    layout="wide",
)

st.title("🌌 Studio IA - Générateur d'Univers")
st.caption("Fiches JSON + croquis techniques + découpes 3D, cloisonnés par projet.")


# ── Session state : configuration et projet actif ───────────────────────────
def _init_state():
    if "cfg" not in st.session_state:
        st.session_state.cfg = config_defaut()
    if "projet" not in st.session_state:
        st.session_state.projet = None


_init_state()


# ── Barre supérieure : sélectionner ou créer un projet ───────────────────
with st.container():
    col1, col2 = st.columns([2, 1])
    with col1:
        projets = lister_projets()
        noms_projets = [p["nom"] for p in projets]
        option_creation = "➕ Créer un nouveau projet..."

        selection = st.selectbox(
            "📁 Projet actif",
            options=[option_creation] + noms_projets,
            index=0,
            help="Choisissez un projet existant ou créez-en un nouveau.",
        )

    with col2:
        nouveau_nom = st.text_input(
            "Nom du nouveau projet",
            value="",
            placeholder="ex: Film_A, Jeu_B",
        )

    if selection == option_creation:
        if nouveau_nom.strip():
            try:
                st.session_state.projet = creer_ou_ouvrir(nouveau_nom.strip())
                st.success(f"Projet créé : {st.session_state.projet['nom']}")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur création projet : {e}")
        elif not projets:
            st.info("Créez un projet pour commencer.")
    else:
        # Retrouve le projet par nom
        for p in projets:
            if p["nom"] == selection:
                st.session_state.projet = p
                break


projet = st.session_state.projet
if projet:
    st.markdown(f"**Projet actif :** `{projet['nom']}` — `{projet['slug']}`")
else:
    st.stop()


# ── Onglets principaux ────────────────────────────────────────────────────
tab_generer, tab_config, tab_explorer = st.tabs(
    ["✨ Générer une entité", "⚙️ Configuration", "🔍 Explorateur de projet"]
)


# ── Onglet : Générer ────────────────────────────────────────────────────────
with tab_generer:
    st.header("Générer")
    mode = st.radio("Mode", ["Une entité", "Depuis un scénario"], horizontal=True)

    col_options1, col_options2 = st.columns(2)
    with col_options1:
        activer_sd = st.checkbox("Générer le croquis via Stable Diffusion", value=True)
        activer_civitai = st.checkbox("Télécharger un modèle Civitai adapté", value=True)
    with col_options2:
        activer_decoupe = st.checkbox("Découper le croquis en vues 3D", value=True)
        activer_3d = st.checkbox("Générer le modèle Blender 3D", value=True,
                                 help="Génère un script Python Blender (.py) et le .blend si Blender est installé.")
        model_override = st.text_input("Modèle OpenAI (optionnel)",
                                       value=st.session_state.cfg.model_openai)

    if mode == "Une entité":
        with st.form("form_generation"):
            col_nom, col_cat, col_type = st.columns(3)
            with col_nom:
                nom_entite = st.text_input("Nom de l'entité", value="Kael Vorn")
            with col_cat:
                categorie = st.selectbox("Catégorie", CATEGORIES)
            with col_type:
                type_entite = st.text_input("Type", value="Humain",
                                            placeholder="Humain, Animal, Insecte, Objet, Plante...")

            description = st.text_area(
                "Description brute",
                value="Un ancien chasseur de primes, cheveux blancs, cicatrice sous l'œil gauche, manteau en cuir.",
                height=120,
            )

            submitted = st.form_submit_button("🚀 Lancer la génération", use_container_width=True)

        if submitted:
            if not nom_entite.strip() or not description.strip():
                st.error("Le nom et la description sont obligatoires.")
            else:
                cfg = st.session_state.cfg
                if model_override.strip():
                    cfg.model_openai = model_override.strip()

                orchestrateur = OrchestrateurUnivers(cfg)
                with st.spinner("Génération en cours... Cela peut prendre plusieurs minutes."):
                    try:
                        bilan = orchestrateur.executer(
                            nom_projet=projet["nom"],
                            nom_entite=nom_entite.strip(),
                            categorie=categorie,
                            type_entite=type_entite.strip(),
                            description=description.strip(),
                            generer_sd=activer_sd,
                            generer_decoupe=activer_decoupe,
                            telecharger_civitai=activer_civitai,
                            generer_3d=activer_3d,
                        )
                    except ErreurWorkflowUnivers as e:
                        st.error(f"Erreur workflow : {e}")
                        st.stop()

                st.success(f"Génération terminée en {bilan.get('duree_s', 0)}s")

                if bilan.get("fiche"):
                    with st.expander("📄 Fiche JSON générée"):
                        st.json(bilan["fiche"]["contenu"])

                if bilan.get("modele", {}).get("success"):
                    st.info(f"Modèle Civitai : `{bilan['modele']['nom_checkpoint']}`")

                if bilan.get("croquis", {}).get("success"):
                    chemin_img = bilan["croquis"]["chemin"]
                    st.image(chemin_img, caption=f"Croquis : {nom_entite}", use_container_width=True)

                if bilan.get("decoupes", {}).get("success"):
                    st.subheader("Découpes 3D")
                    vues = bilan["decoupes"].get("vues", {})
                    cols = st.columns(len(vues))
                    for col, (nom, chemin) in zip(cols, vues.items()):
                        col.image(chemin, caption=nom.capitalize(), use_container_width=True)

                if not bilan.get("croquis", {}).get("success") and activer_sd:
                    st.warning(bilan.get("croquis", {}).get("error", "Échec de la génération d'image."))

                m3d = bilan.get("modele_3d") or {}
                if m3d.get("success"):
                    st.subheader("🧊 Modèle Blender 3D")
                    if m3d.get("chemin_blend"):
                        st.success(f"✅ .blend généré → `{m3d['chemin_blend']}`")
                    elif m3d.get("blender_disponible"):
                        st.warning(f"Blender a échoué : {m3d.get('erreur', '')[:200]}")
                    else:
                        st.info(
                            f"Script prêt → `{m3d['chemin_script']}`\n\n"
                            "Blender n'est pas installé. Exécutez le script dans Blender "
                            "ou depuis un terminal :\n"
                            f"```bash\nblender --background --python {os.path.basename(m3d['chemin_script'])}\n```"
                        )
                    with st.expander("Détails de la modélisation"):
                        col_a, col_b = st.columns(2)
                        col_a.metric("Taille", f"{m3d.get('taille_cm', '?')} cm")
                        col_b.metric("Poids", f"{m3d.get('poids_kg', '?')} kg")
                        if m3d.get("couleurs"):
                            st.markdown("**Couleurs extraites (RGB 0-1)**")
                            for rgb in m3d["couleurs"]:
                                r, g, b = [int(c * 255) for c in rgb]
                                st.markdown(
                                    f'<span style="display:inline-block;width:20px;height:20px;'
                                    f'background:rgb({r},{g},{b});border-radius:3px;'
                                    f'margin-right:8px;vertical-align:middle;border:1px solid #ccc"></span>'
                                    f'rgb({r}, {g}, {b})',
                                    unsafe_allow_html=True
                                )

    else:  # Mode scénario
        with st.form("form_scenario"):
            chemin_scenario = st.text_input(
                "Chemin du fichier scénario",
                value=os.path.join(projet["chemin"], "scenario.md"),
                placeholder="output/projects/MonFilm/scenario.md",
            )
            texte_scenario = st.text_area(
                "Ou collez le scénario ici (remplace le fichier si rempli)",
                value="",
                height=200,
                placeholder="# Mon scénario\n\n## Personnages\n- Kael : ...\n",
            )
            submitted_scenario = st.form_submit_button("🎬 Lancer le scénario", use_container_width=True)

        if submitted_scenario:
            cfg = st.session_state.cfg
            if model_override.strip():
                cfg.model_openai = model_override.strip()

            if not chemin_scenario.strip():
                st.error("Le chemin du scénario est obligatoire.")
                st.stop()

            # Si l'utilisateur a collé un texte, on l'écrit dans un fichier temporaire
            chemin_effectif = chemin_scenario.strip()
            if texte_scenario.strip():
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as f:
                    f.write(texte_scenario.strip())
                    chemin_effectif = f.name

            if not os.path.exists(chemin_effectif):
                st.error(f"Fichier scénario introuvable : {chemin_effectif}")
                st.stop()

            orchestrateur = OrchestrateurUnivers(cfg)
            with st.spinner("Analyse du scénario et génération de toutes les entités... Cela peut prendre plusieurs minutes."):
                try:
                    bilan = orchestrateur.executer_scenario(
                        nom_projet=projet["nom"],
                        chemin_scenario=chemin_effectif,
                        generer_sd=activer_sd,
                        generer_decoupe=activer_decoupe,
                        telecharger_civitai=activer_civitai,
                        generer_3d=activer_3d,
                    )
                except ErreurWorkflowUnivers as e:
                    st.error(f"Erreur workflow : {e}")
                    st.stop()

            st.success(f"Scénario terminé : {bilan['succes']}/{bilan['total']} entités générées en {bilan.get('duree_s', 0)}s")
            st.markdown(f"**Style univers :** {bilan.get('style_univers', 'non précisé')}")

            for e in bilan["entites"]:
                fiche = e["resultat"].get("fiche")
                status = "✅" if fiche else "❌"
                with st.expander(f"{status} {e['nom']} ({e['categorie']} / {e['type']})"):
                    st.markdown(f"**Importance :** {e['raison']}")
                    if fiche:
                        st.json(fiche['contenu'])
                    else:
                        st.error(e['resultat'].get('error', 'Échec'))


# ── Onglet : Configuration ──────────────────────────────────────────────────
with tab_config:
    st.header("Configuration des API")
    st.markdown("Les valeurs sont surchargées par les variables d'environnement au démarrage.")

    cfg = st.session_state.cfg
    with st.form("form_config"):
        st.subheader("Stable Diffusion")
        backend = st.selectbox("Backend", ["auto", "comfyui", "automatic1111", "forge"],
                               index=["auto", "comfyui", "automatic1111", "forge"].index(cfg.sd_backend))
        sd_url = st.text_input("URL ComfyUI", value=cfg.sd_url)
        sd_url_alt = st.text_input("URL A1111/Forge", value=cfg.sd_url_alt)

        st.subheader("Civitai")
        civitai_url = st.text_input("URL API Civitai", value=cfg.civitai_url)
        civitai_key = st.text_input("Clé API Civitai (optionnelle)", value=cfg.civitai_api_key, type="password")

        st.subheader("OpenAI")
        model_openai = st.text_input("Modèle OpenAI", value=cfg.model_openai)

        st.subheader("Paramètres de génération")
        col_w, col_h, col_steps, col_cfg = st.columns(4)
        with col_w:
            width = st.number_input("Largeur", min_value=256, max_value=2048, value=cfg.width, step=64)
        with col_h:
            height = st.number_input("Hauteur", min_value=256, max_value=2048, value=cfg.height, step=64)
        with col_steps:
            steps = st.number_input("Steps", min_value=1, max_value=100, value=cfg.steps, step=1)
        with col_cfg:
            cfg_scale = st.number_input("CFG Scale", min_value=1.0, max_value=20.0, value=cfg.cfg_scale, step=0.5)

        sampler = st.selectbox(
            "Sampler",
            ["DPM++ 2M Karras", "Euler a", "Euler", "DPM++ SDE Karras"],
            index=["DPM++ 2M Karras", "Euler a", "Euler", "DPM++ SDE Karras"].index(cfg.sampler_name),
        )

        seed = st.number_input("Seed (-1 = aléatoire)", min_value=-1, max_value=2**32, value=cfg.seed, step=1)

        save_config = st.form_submit_button("💾 Enregistrer la configuration")

    if save_config:
        cfg.sd_backend = backend
        cfg.sd_url = sd_url
        cfg.sd_url_alt = sd_url_alt
        cfg.civitai_url = civitai_url
        cfg.civitai_api_key = civitai_key
        cfg.model_openai = model_openai
        cfg.width = int(width)
        cfg.height = int(height)
        cfg.steps = int(steps)
        cfg.cfg_scale = cfg_scale
        cfg.sampler_name = sampler
        cfg.seed = int(seed)
        st.session_state.cfg = cfg
        st.success("Configuration mise à jour en mémoire (non persistée par défaut).")


# ── Onglet : Explorateur ───────────────────────────────────────────────────
with tab_explorer:
    st.header("Bible du projet")

    for categorie in CATEGORIES:
        st.subheader(categorie.capitalize())
        fiches = lister_fiches(projet, categorie)
        croquis = lister_croquis(projet, categorie)

        if not fiches and not croquis:
            st.caption("Aucun contenu pour cette catégorie.")
            continue

        # Affiche chaque fiche avec son croquis et ses découpes associés
        for fiche_nom in fiches:
            nom_base = fiche_nom[:-5]  # retire .json
            with st.expander(f"📄 {nom_base}"):
                fiche = lire_fiche(projet, categorie, nom_base)
                col_text, col_img = st.columns([1, 1])
                with col_text:
                    st.json(fiche)
                with col_img:
                    # Croquis principal
                    chemin_croquis = None
                    for ext in [".png", ".jpg", ".jpeg"]:
                        candidat = os.path.join(
                            projet["chemin"], "sketches", categorie, f"{nom_base}{ext}")
                        if os.path.exists(candidat):
                            chemin_croquis = candidat
                            break
                    if chemin_croquis:
                        st.image(chemin_croquis, caption="Croquis principal", use_container_width=True)

                        # Découpes
                        dossier_decoupes = os.path.join(
                            projet["chemin"], "sketches", categorie, "decoupes")
                        decoupes = []
                        for nom_vue in ["face", "profile", "back"]:
                            chemin_vue = os.path.join(dossier_decoupes, f"{nom_base}_{nom_vue}.png")
                            if os.path.exists(chemin_vue):
                                decoupes.append((nom_vue, chemin_vue))
                        if decoupes:
                            st.markdown("**Découpes 3D**")
                            cols = st.columns(len(decoupes))
                            for col, (nom, chemin) in zip(cols, decoupes):
                                col.image(chemin, caption=nom.capitalize(), use_container_width=True)

                        # ── Bouton Générer modèle Blender 3D ──────────────
                        dossier_blender = chemin_3d(projet, categorie, nom_base)
                        import re as _re
                        nom_safe = _re.sub(r"[^\w\-]", "_", nom_base)
                        blend_existant = os.path.join(dossier_blender, f"{nom_safe}.blend")
                        script_existant = os.path.join(dossier_blender, f"{nom_safe}_blender.py")

                        st.markdown("---")
                        st.markdown("**🧊 Modèle Blender 3D**")
                        if os.path.isfile(blend_existant):
                            st.success(f"✅ `.blend` disponible → `{blend_existant}`")
                        elif os.path.isfile(script_existant):
                            st.info(f"Script prêt → `{script_existant}` (Blender nécessaire pour créer le .blend)")
                        else:
                            btn_key = f"btn_3d_{categorie}_{nom_base}"
                            if st.button("⚙️ Générer le modèle Blender 3D", key=btn_key):
                                vues_dispo = {
                                    nom_v: os.path.join(
                                        projet["chemin"], "sketches", categorie,
                                        "decoupes", f"{nom_base}_{nom_v}.png")
                                    for nom_v in ["face", "profile", "back"]
                                    if os.path.isfile(os.path.join(
                                        projet["chemin"], "sketches", categorie,
                                        "decoupes", f"{nom_base}_{nom_v}.png"))
                                }
                                cfg_gen = st.session_state.cfg
                                from univers.agents.modelisateur_blender import ModelisateurBlender
                                modelisateur = ModelisateurBlender(model=cfg_gen.model_openai)
                                with st.spinner(f"Génération du script Blender pour {nom_base}..."):
                                    r3d = modelisateur.generer(
                                        fiche=fiche,
                                        vues=vues_dispo,
                                        dossier_3d=dossier_blender,
                                    )
                                if r3d.chemin_blend:
                                    st.success(f"✅ .blend généré → `{r3d.chemin_blend}`")
                                else:
                                    st.info(f"Script généré → `{r3d.chemin_script}`")
                                    if not r3d.blender_disponible:
                                        st.caption("Blender non trouvé. Exécutez le script manuellement.")
                                st.rerun()
                    else:
                        st.caption("Aucun croquis généré pour cette fiche.")

    st.divider()
    st.subheader("Modèles téléchargés")
    dossier_modeles = chemin_modeles(projet)
    if os.path.isdir(dossier_modeles):
        modeles = [f for f in os.listdir(dossier_modeles) if f.endswith(".safetensors")]
        if modeles:
            for m in modeles:
                st.markdown(f"- `{m}`")
        else:
            st.caption("Aucun modèle dans ce projet.")
    else:
        st.caption("Aucun modèle dans ce projet.")
