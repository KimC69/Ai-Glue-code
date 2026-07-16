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
    parser.add_argument("--model", default="",
                        help="Modèle OpenAI (défaut : gpt-4o-mini)")
    parser.add_argument("--lister-projets", action="store_true",
                        help="Liste les projets existants puis quitte")

    args = parser.parse_args(argv)

    if args.lister_projets:
        for p in lister_projets():
            print(f"  • {p['nom']} ({p['slug']}) — créé le {p['cree_le']}")
        return

    # Validation des arguments obligatoires pour la génération
    manquants = []
    for arg, label in (("projet", "--projet"), ("nom", "--nom"),
                       ("categorie", "--categorie"), ("type", "--type"),
                       ("description", "--description")):
        if not getattr(args, arg, "").strip():
            manquants.append(label)
    if manquants:
        parser.error("Arguments obligatoires manquants : " + ", ".join(manquants))

    cfg = config_defaut()
    if args.model:
        cfg.model_openai = args.model

    orchestrateur = OrchestrateurUnivers(cfg)
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
    print(f"  Durée totale : {bilan.get('duree_s', 0)}s")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
