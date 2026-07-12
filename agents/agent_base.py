"""
agent_base.py — Classe de base partagée par tous les agents du studio.
Factorise la vérification de la clé API, la création du LLM et du parser
Pydantic, ainsi que la gestion des erreurs communes.
"""

import os
from typing import Type
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser


class BaseAgent:
    """
    Classe de base pour tous les agents du studio.

    Gère :
    - la vérification de la clé OpenAI (lève RuntimeError si manquante)
    - l'initialisation du LLM
    - la création du parser Pydantic avec auto-correction
    - la construction du prompt

    Usage dans une sous-classe :
        class MonAgent(BaseAgent):
            def __init__(self, model="gpt-4o-mini", temperature=0.7):
                super().__init__(model, temperature, MonOutputSchema)
                self.prompt = self._build_prompt(SYSTEM_PROMPT, USER_PROMPT)
    """

    def __init__(
        self,
        model: str,
        temperature: float,
        output_schema: Type[BaseModel],
        agent_id: str = "Agent",
    ):
        # Deux accès possibles à OpenAI, dans cet ordre de priorité :
        #  1. Une clé PERSONNELLE (OPENAI_API_KEY) — dès qu'elle est définie,
        #     elle l'emporte : il suffit de l'ajouter pour passer à son propre
        #     compte, sans toucher au code.
        #  2. L'accès GÉRÉ PAR REPLIT (intégration OpenAI) — proxy compatible
        #     OpenAI, aucune clé à fournir, facturé sur les crédits Replit. Il
        #     expose une URL de base + une clé technique dans l'environnement.
        cle_perso = os.getenv("OPENAI_API_KEY")
        base_url_replit = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL")
        cle_replit = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY")

        if cle_perso:
            api_key, base_url = cle_perso, None
        elif base_url_replit and cle_replit:
            api_key, base_url = cle_replit, base_url_replit
        else:
            raise RuntimeError(
                f"[{agent_id}] Aucun accès OpenAI configuré. Deux options : "
                "l'accès géré par Replit (intégration OpenAI, aucune clé à "
                "fournir) ou votre propre clé dans OPENAI_API_KEY "
                "(voir .env.example)."
            )

        self.agent_id = agent_id
        self.model = model
        self.temperature = temperature
        self.output_schema = output_schema

        kwargs = {"model": model, "temperature": temperature, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.llm = ChatOpenAI(**kwargs)

        base_parser = PydanticOutputParser(pydantic_object=output_schema)
        self.parser = OutputFixingParser.from_llm(parser=base_parser, llm=self.llm)
        self.base_parser = base_parser

    def _build_prompt(self, system_prompt: str, user_prompt: str) -> ChatPromptTemplate:
        """Construit le ChatPromptTemplate avec les instructions de format."""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", user_prompt),
        ]).partial(format_instructions=self.base_parser.get_format_instructions())
