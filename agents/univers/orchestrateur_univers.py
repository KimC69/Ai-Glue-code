"""
orchestrateur_univers.py — Orchestrateur dédié au Générateur d'Univers.

Exécute la chaîne d'agents spécialisés dans l'ordre :
1. Rédacteur de Fiche      → fiche JSON
2. Curateur Civitai        → modèle .safetensors dans le projet
3. Prompteur               → prompt SD de croquis
4. Dessinateur SD          → image PNG
5. Découpeur 3D            → vues face/profil/dos

Chaque étape est tracée et les résultats sont rangés dans la structure du projet.
"""

import json
import os
import time
from typing import Optional

from .config import ConfigUnivers
from .projet_manager import (
    creer_ou_ouvrir, sauver_fiche, chemin_croquis, chemin_modeles,
    CATEGORIES
)
from .agents.redacteur_fiche import RedacteurFiche
from .agents.curateur_civitai import CurateurCivitai
from .agents.prompteur import Prompteur
from .agents.dessinateur_sd import DessinateurSD
from .agents.decoupeur_3d import Decoupeur3D
from .agents.scenariste_univers import ScenaristeUnivers


class ErreurWorkflowUnivers(Exception):
    """Erreur bloquante dans le workflow du Générateur d'Univers."""


class OrchestrateurUnivers:
    """Orchestre la génération d'une fiche + croquis + découpes pour une entité."""

    def __init__(self, config: Optional[ConfigUnivers] = None):
        self.config = config or ConfigUnivers()
        self.etapes = []
        self.erreur = ""

    def _log(self, message: str):
        print(f"[Univers] {message}")
        self.etapes.append(message)

    def executer(self, nom_projet: str, nom_entite: str, categorie: str,
                 type_entite: str, description: str,
                 generer_sd: bool = True, generer_decoupe: bool = True,
                 telecharger_civitai: bool = True) -> dict:
        """Lance le workflow complet pour une entité.

        Retourne un dict avec les chemins et les résultats intermédiaires.
        """
        if categorie not in CATEGORIES:
            raise ErreurWorkflowUnivers(
                f"Catégorie invalide : {categorie}. Choix : {CATEGORIES}")

        debut_total = time.time()
        projet = creer_ou_ouvrir(nom_projet)
        self._log(f"Projet actif : {projet['nom']} ({projet['slug']})")

        bilan = {
            "projet": projet,
            "entite": nom_entite,
            "categorie": categorie,
            "type": type_entite,
            "fiche": None,
            "modele": None,
            "prompt": None,
            "croquis": None,
            "decoupes": None,
            "duree_s": 0,
            "etapes": [],
        }

        # ── Étape 1 : Rédacteur de Fiche ─────────────────────────────────────
        self._log("Étape 1/5 — Rédaction de la fiche d'identité...")
        redacteur = RedacteurFiche(model=self.config.model_openai)
        fiche = redacteur.rediger(nom_entite, categorie, type_entite, description)
        fiche_dict = fiche.model_dump()
        fiche_dict["meta"] = {
            "cree_le": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "source": "RedacteurFiche",
        }
        chemin_fiche = sauver_fiche(projet, categorie, nom_entite, fiche_dict)
        bilan["fiche"] = {"chemin": chemin_fiche, "contenu": fiche_dict}
        self._log(f"Fiche enregistrée → {chemin_fiche}")

        # ── Étape 2 : Curateur Civitai (optionnel) ─────────────────────────
        modele_chemin = ""
        modele_nom = ""
        if telecharger_civitai:
            self._log("Étape 2/5 — Recherche d'un modèle Civitai adapté...")
            curateur = CurateurCivitai(self.config, model=self.config.model_openai)
            resultat_civitai = curateur.trouver_et_telecharger(projet, fiche_dict)
            bilan["modele"] = resultat_civitai
            if resultat_civitai.get("success"):
                modele_chemin = resultat_civitai.get("chemin_local", "")
                modele_nom = resultat_civitai.get("nom_checkpoint", "")
                self._log(f"Modèle téléchargé → {modele_chemin}")
            else:
                self._log(f"Curateur Civitai : {resultat_civitai.get('error', 'échec')}")
        else:
            self._log("Étape 2/5 — Curateur Civitai désactivé.")

        # ── Étape 3 : Prompteur ─────────────────────────────────────────────
        self._log("Étape 3/5 — Traduction de la fiche en prompt de croquis...")
        prompteur = Prompteur(model=self.config.model_openai)
        prompt_sd = prompteur.traduire(fiche_dict)
        bilan["prompt"] = {
            "positive": prompt_sd.positive,
            "negative": prompt_sd.negative,
            "parametres": prompt_sd.parametres,
        }
        self._log("Prompt généré")

        # ── Étape 4 : Dessinateur SD ────────────────────────────────────────
        if generer_sd:
            self._log("Étape 4/5 — Génération du croquis avec Stable Diffusion...")
            chemin_img = chemin_croquis(projet, categorie, nom_entite)
            dessinateur = DessinateurSD(self.config, model=self.config.model_openai)
            resultat_sd = dessinateur.dessiner(
                prompt_positif=prompt_sd.positive,
                prompt_negatif=prompt_sd.negative,
                chemin_sortie=chemin_img,
                modele_checkpoint=modele_nom,
            )
            bilan["croquis"] = resultat_sd
            if resultat_sd.get("success"):
                self._log(f"Croquis généré → {resultat_sd.get('chemin')}")
            else:
                self._log(f"Dessinateur SD : {resultat_sd.get('error', 'échec')}")
                # La suite (découpe) n'a pas de sens sans image
                bilan["duree_s"] = round(time.time() - debut_total, 2)
                bilan["etapes"] = self.etapes
                return bilan
        else:
            self._log("Étape 4/5 — Génération d'image désactivée.")

        # ── Étape 5 : Découpeur 3D ───────────────────────────────────────────
        if generer_decoupe and bilan["croquis"] and bilan["croquis"].get("success"):
            self._log("Étape 5/5 — Découpe du croquis en vues orthographiques...")
            decoupeur = Decoupeur3D(model=self.config.model_openai)
            resultat_decoupe = decoupeur.decouper(
                chemin_image=bilan["croquis"]["chemin"],
                dossier_sortie=os.path.join(
                    projet["chemin"], "sketches", categorie, "decoupes"),
            )
            bilan["decoupes"] = resultat_decoupe
            if resultat_decoupe.get("success"):
                self._log(f"Découpes enregistrées : {', '.join(resultat_decoupe.get('vues', {}).keys())}")
            else:
                self._log(f"Découpeur 3D : {resultat_decoupe.get('error', 'échec')}")
        else:
            self._log("Étape 5/5 — Découpe 3D désactivée ou impossible.")

        bilan["duree_s"] = round(time.time() - debut_total, 2)
        bilan["etapes"] = self.etapes
        return bilan

    def generer_seulement_fiche(self, nom_projet: str, nom_entite: str,
                                categorie: str, type_entite: str,
                                description: str) -> dict:
        """Mode rapide : uniquement la fiche JSON, sans image."""
        return self.executer(
            nom_projet, nom_entite, categorie, type_entite, description,
            generer_sd=False, generer_decoupe=False, telecharger_civitai=False)

    def executer_scenario(self, nom_projet: str, chemin_scenario: str,
                          generer_sd: bool = True, generer_decoupe: bool = True,
                          telecharger_civitai: bool = True) -> dict:
        """Lance le workflow complet sur toutes les entités extraites d'un scénario.

        Retourne un bilan global avec la liste des entités traitées et les erreurs.
        """
        debut_total = time.time()
        projet = creer_ou_ouvrir(nom_projet)
        self._log(f"Projet actif : {projet['nom']} ({projet['slug']})")
        self._log(f"Analyse du scénario : {chemin_scenario}")

        scenariste = ScenaristeUnivers(model=self.config.model_openai)
        extraction = scenariste.analyser(chemin_scenario)

        self._log(f"Scénario analysé : {extraction.resume}")
        self._log(f"Entités détectées : {len(extraction.entites)}")

        bilan = {
            "projet": projet,
            "resume_scenario": extraction.resume,
            "style_univers": extraction.style_univers,
            "total": len(extraction.entites),
            "succes": 0,
            "echecs": 0,
            "entites": [],
            "duree_s": 0,
            "etapes": [],
        }

        for idx, entite in enumerate(extraction.entites, 1):
            self._log(f"\n[{idx}/{len(extraction.entites)}] {entite.nom} ({entite.categorie})")
            resultat = self.executer(
                nom_projet=nom_projet,
                nom_entite=entite.nom,
                categorie=entite.categorie,
                type_entite=entite.type,
                description=entite.description,
                generer_sd=generer_sd,
                generer_decoupe=generer_decoupe,
                telecharger_civitai=telecharger_civitai,
            )
            if resultat.get("fiche"):
                bilan["succes"] += 1
            else:
                bilan["echecs"] += 1
            bilan["entites"].append({
                "nom": entite.nom,
                "categorie": entite.categorie,
                "type": entite.type,
                "raison": entite.raison,
                "resultat": resultat,
            })

        bilan["duree_s"] = round(time.time() - debut_total, 2)
        bilan["etapes"] = self.etapes
        self._log(f"\nScénario terminé : {bilan['succes']}/{bilan['total']} entités générées")
        return bilan
