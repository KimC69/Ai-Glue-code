"""
08_ingenieur_son.py — Agent 08 : Ingénieur du Son (bande originale)
Rôle : Composer la bande son du film sous forme d'un fichier Csound (.csd)
prêt à être rendu en audio SANS ouvrir d'interface graphique
(csound bande_son.csd -o bande_son.wav).

Pourquoi Csound : c'est un logiciel de musique 100 % pilotable par script et
totalement headless. Un seul fichier texte décrit à la fois les instruments
(synthèse) ET la partition (les notes) — aucun échantillon ni banque de sons
externe n'est nécessaire, donc le rendu est reproductible partout.

Expose la classe IngenieurSon avec la méthode composer_bande_son().
"""

import os
from langchain_core.exceptions import OutputParserException
from agent_base import BaseAgent
from shared_state import SoundEngineerOutput


SYSTEM_PROMPT = """Tu es l'Ingénieur du Son et compositeur d'un studio de cinéma virtuel.
Tu composes la bande originale du film sous forme d'un fichier Csound (.csd)
COMPLET, autonome et directement rendu en audio en ligne de commande :
    csound bande_son.csd -o bande_son.wav

Règles absolues :
- Le fichier commence par <CsoundSynthesizer> et se termine par </CsoundSynthesizer>.
- Il contient les trois blocs : <CsOptions>, <CsInstruments>, <CsScore>.
- Dans <CsOptions>, active le rendu fichier : -o bande_son.wav -W
- Dans <CsInstruments>, définis l'en-tête (sr = 44100, ksmps = 32, nchnls = 2,
  0dbfs = 1) puis un ou plusieurs instr (synthèse additive/soustractive, enveloppes
  linen/adsr, oscil/oscili, reverb pour l'ambiance).
- Dans <CsScore>, écris une VRAIE partition : plusieurs notes (i ...), avec des
  hauteurs et durées cohérentes, pour une pièce de 20 à 60 secondes.
- N'utilise AUCun fichier externe (pas de GEN01/soundin/banque de sons) : tout
  est synthétisé, pour que le rendu marche sur n'importe quelle machine.
- Commente les sections importantes en français.
- Adapte l'ambiance musicale (tonalité, tempo, instrumentation, dynamique) au
  genre, au ton et aux scènes clés du film.

Tu dois répondre UNIQUEMENT avec le JSON demandé — aucun texte avant ou après.
"""

USER_PROMPT = """Vision artistique : {vision_globale}

Style visuel (Agent 04) : {visual_style}

Scènes clés : {key_scenes}

Genre : {genre} | Ton : {tone}

Compose la bande originale du film. Génère exactement :
- mood_musical : description de l'ambiance sonore visée — tonalité, tempo,
  instrumentation, émotion recherchée et lien avec les scènes clés (3-4 phrases)
- csound_script : le fichier Csound (.csd) complet et rendu-able tel quel
- filename : nom du fichier à créer (ex: bande_son.csd)

{format_instructions}"""


class IngenieurSon(BaseAgent):
    """
    Agent 08 — Ingénieur du Son (bande originale).

    Lit la vision, le style visuel et les scènes clés dans WorldState, compose
    une bande son sous forme d'un fichier Csound (.csd) autonome et le
    sauvegarde dans output/.

    Usage :
        son = IngenieurSon()
        resultat = son.composer_bande_son(
            vision_globale="Un film sous-marin contemplatif...",
            visual_style="Bleu profond, particules lumineuses...",
            key_scenes="Ouverture : descente dans l'abîme...",
            genre="Science-fiction contemplative",
            tone="Sombre, poétique",
        )
        # resultat["mood_musical"], resultat["csound_script"], resultat["saved_path"]
    """

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.5):
        # gpt-4o par défaut : composer une partition Csound valide bénéficie
        # d'un modèle plus solide (comme la génération de code Blender/Unreal).
        super().__init__(
            model=model,
            temperature=temperature,
            output_schema=SoundEngineerOutput,
            agent_id="Agent 08",
        )
        self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)

    def composer_bande_son(
        self,
        vision_globale: str,
        visual_style: str,
        key_scenes: str,
        genre: str,
        tone: str,
    ) -> dict:
        """
        Compose et sauvegarde la bande son du film (fichier Csound .csd).

        Args:
            vision_globale : Vision artistique (sortie Agent 01)
            visual_style   : Style visuel décrit par l'Agent 04
            key_scenes     : Scènes clés (sortie Agent 02)
            genre          : Genre du film (sortie Agent 01)
            tone           : Ton du film (sortie Agent 01)

        Returns:
            {
              "mood_musical":  str,   # description de l'ambiance sonore
              "csound_script": str,   # fichier Csound (.csd) complet
              "saved_path":    str,   # chemin du fichier .csd sauvegardé
            }

        Raises:
            RuntimeError : Si le LLM échoue à produire une réponse valide
        """
        chain = self.prompt | self.llm | self.parser

        try:
            response: SoundEngineerOutput = chain.invoke({
                "vision_globale": vision_globale,
                "visual_style":   visual_style,
                "key_scenes":     key_scenes,
                "genre":          genre,
                "tone":           tone,
            })
        except (OutputParserException, Exception) as e:
            raise RuntimeError(f"[Agent 08] Échec de la composition sonore : {e}") from e

        # Nom de fichier fixe (défini en interne, jamais fourni par le LLM) :
        # aucun risque de traversée de répertoire.
        saved_path = self._sauvegarder("bande_son.csd", response.csound_script)

        self._last_mood_musical  = response.mood_musical
        self._last_csound_script = response.csound_script
        self._last_saved_path    = saved_path

        return {
            "mood_musical":  response.mood_musical,
            "csound_script": response.csound_script,
            "saved_path":    saved_path,
        }

    def _sauvegarder(self, filename: str, code: str) -> str:
        """Sauvegarde le fichier Csound dans agents/output/.
        Le nom de fichier est fixe (défini en interne, jamais fourni par le LLM)."""
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return filepath

    def afficher_rapport(self) -> str:
        """Retourne un résumé formaté de la dernière composition."""
        return (
            f"AMBIANCE MUSICALE :\n{getattr(self, '_last_mood_musical', '—')}\n\n"
            f"BANDE SON (Csound) sauvegardée → {getattr(self, '_last_saved_path', '—')}\n"
            f"(Aperçu — 10 premières lignes) :\n"
            + "\n".join(getattr(self, "_last_csound_script", "").splitlines()[:10])
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    son = IngenieurSon()
    son.composer_bande_son(
        vision_globale="Un film sous-marin bioluminescent, poétique et contemplatif.",
        visual_style="Bleu profond, particules lumineuses, éclairage doux.",
        key_scenes="Ouverture : lente descente dans l'abîme. Climax : rencontre lumineuse.",
        genre="Science-fiction contemplative",
        tone="Sombre, poétique, métaphysique",
    )
    print(son.afficher_rapport())
