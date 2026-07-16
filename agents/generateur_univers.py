"""
generateur_univers.py — Point d'entrée CLI du Studio IA - Générateur d'Univers.

Nouveau workflow, indépendant du pipeline cinéma (agents 01-08), qui génère :
- une fiche d'identité JSON (humain, animal, insecte, objet, plante) ;
- un croquis technique via Stable Diffusion ;
- une découpe 3D face/profil/dos.

Tout est cloisonné par projet sous output/projects/[nom]/.
"""

import argparse
import sys
import os

# Assure que agents/ est dans le path pour les imports absolus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from univers.config import config_defaut
from univers.projet_manager import lister_projets
from univers.orchestrateur_univers import OrchestrateurUnivers, ErreurWorkflowUnivers


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Studio IA - Générateur d'Univers : création de fiches et croquis par projet.")
    parser.add_argument("--projet", default="", help="Nom du projet (créé s'il n'existe pas)")
    parser.add_argument("--nom", default="", help="Nom de l'entité à générer")
    parser.add_argument("--categorie", default="",
                        choices=["characters", "objects", "flora"],
                        help="Catégorie de l'entité")
    parser.add_argument("--type", default="",
                        help="Type précis : Humain, Animal, Insecte, Objet, Plante, etc.")
    parser.add_argument("--description", default="",
                        help="Description brute de l'entité")
    parser.add_argument("--no-sd", action="store_true",
                        help="Génère uniquement la fiche JSON, pas l'image")
    parser.add_argument("--no-decoupe", action="store_true",
                        help="Génère le croquis mais pas la découpe 3D")
    parser.add_argument("--no-civitai", action="store_true",
                        help="Ne télécharge pas de modèle Civitai")
    parser.add_argument("--no-3d", action="store_true",
                        help="Ne génère pas le script/modèle Blender 3D")
    parser.add_argument("--model", default="",
                        help="Modèle OpenAI (défaut : gpt-4o-mini)")
    parser.add_argument("--lister-projets", action="store_true",
                        help="Liste les projets existants puis quitte")
    parser.add_argument("--scenario", action="store_true",
                        help="Mode scénario : génère toutes les entités d'un fichier de scénario")
    parser.add_argument("--fichier-scenario", default="",
                        help="Chemin du fichier de scénario (.md ou .txt)")

    args = parser.parse_args(argv)

    if args.lister_projets:
        for p in lister_projets():
            print(f"  • {p['nom']} ({p['slug']}) — créé le {p['cree_le']}")
        return

    cfg = config_defaut()
    if args.model:
        cfg.model_openai = args.model

    orchestrateur = OrchestrateurUnivers(cfg)

    # ── Mode scénario ─────────────────────────────────────────────────────────
    if args.scenario:
        if not args.projet.strip():
            parser.error("--projet est obligatoire en mode --scenario")
        if not args.fichier_scenario.strip():
            parser.error("--fichier-scenario est obligatoire en mode --scenario")
        if not os.path.exists(args.fichier_scenario):
            print(f"[Erreur] Fichier scénario introuvable : {args.fichier_scenario}")
            sys.exit(1)

        try:
            bilan = orchestrateur.executer_scenario(
                nom_projet=args.projet,
                chemin_scenario=args.fichier_scenario,
                generer_sd=not args.no_sd,
                generer_decoupe=not args.no_decoupe,
                telecharger_civitai=not args.no_civitai,
                generer_3d=not args.no_3d,
            )
        except ErreurWorkflowUnivers as e:
            print(f"[Erreur] {e}")
            sys.exit(1)

        print("\n" + "=" * 55)
        print("  🌌 SCÉNARIO TERMINÉ")
        print("=" * 55)
        print(f"  Projet       : {bilan['projet']['nom']}")
        print(f"  Scénario     : {bilan['resume_scenario']}")
        print(f"  Entités      : {bilan['total']}")
        print(f"  Succès       : {bilan['succes']}")
        print(f"  Échecs       : {bilan['echecs']}")
        print()
        for e in bilan["entites"]:
            fiche = e["resultat"].get("fiche")
            status = "✅" if fiche else "❌"
            print(f"  {status} {e['nom']} ({e['categorie']} / {e['type']})")
        print(f"\n  Durée totale : {bilan.get('duree_s', 0)}s")
        print("=" * 55 + "\n")
        return

    # ── Mode entité unique ───────────────────────────────────────────────────
    manquants = []
    for arg, label in (("projet", "--projet"), ("nom", "--nom"),
                       ("categorie", "--categorie"), ("type", "--type"),
                       ("description", "--description")):
        if not getattr(args, arg, "").strip():
            manquants.append(label)
    if manquants:
        parser.error("Arguments obligatoires manquants : " + ", ".join(manquants))

    try:
        bilan = orchestrateur.executer(
            nom_projet=args.projet,
            nom_entite=args.nom,
            categorie=args.categorie,
            type_entite=args.type,
            description=args.description,
            generer_sd=not args.no_sd,
            generer_decoupe=not args.no_decoupe,
            telecharger_civitai=not args.no_civitai,
            generer_3d=not args.no_3d,
        )
    except ErreurWorkflowUnivers as e:
        print(f"[Erreur] {e}")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  🌌 GÉNÉRATION D'UNIVERS TERMINÉE")
    print("=" * 55)
    if bilan.get("fiche"):
        print(f"  Fiche JSON  : {bilan['fiche']['chemin']}")
    modele = bilan.get("modele") or {}
    if modele.get("success"):
        print(f"  Modèle SD   : {modele['chemin_local']}")
    croquis = bilan.get("croquis") or {}
    if croquis.get("success"):
        print(f"  Croquis     : {croquis['chemin']}")
    decoupes = bilan.get("decoupes") or {}
    if decoupes.get("success"):
        vues = decoupes.get("vues", {})
        print(f"  Découpes 3D : {', '.join(vues.keys())}")
        for nom, chemin in vues.items():
            print(f"    - {nom}: {chemin}")
    modele_3d = bilan.get("modele_3d") or {}
    if modele_3d.get("success"):
        print(f"  Script Blender : {modele_3d.get('chemin_script', '')}")
        if modele_3d.get("chemin_blend"):
            print(f"  Modèle .blend  : {modele_3d.get('chemin_blend')}")
        elif modele_3d.get("blender_disponible"):
            print(f"  Blender (erreur): {modele_3d.get('erreur', '')[:80]}")
        else:
            print("  ℹ Blender non trouvé — ouvrez le script .py dans Blender")
    print(f"  Durée totale : {bilan.get('duree_s', 0)}s")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
