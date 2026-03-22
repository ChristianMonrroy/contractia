"""
Fábrica de agentes: crea Jurista, Auditor, Cronista y Scout (Agentic RAG).
"""

from typing import Tuple

from contractia.agents.base import AgenteEspecialista
from contractia.agents.prompts import PROMPT_AUDITOR, PROMPT_CRONISTA, PROMPT_JURISTA


def crear_agentes(llm) -> Tuple[AgenteEspecialista, AgenteEspecialista, AgenteEspecialista]:
    """Crea los tres agentes especialistas — texto + parse_json (idéntico a notebook vs18)."""
    jurista  = AgenteEspecialista(llm, PROMPT_JURISTA)
    auditor  = AgenteEspecialista(llm, PROMPT_AUDITOR)
    cronista = AgenteEspecialista(llm, PROMPT_CRONISTA)
    return jurista, auditor, cronista


def crear_scout(llm, retriever, vector_store):
    """
    Crea el Agente Scout para Agentic RAG (v9.0.0).

    Solo se llama cuando AGENTIC_RAG_ENABLED=true. El Scout usa bind_tools
    (incompatible con with_structured_output) y su salida es un string de contexto.

    Args:
        llm: LLM provider con soporte de tool calling (Gemini 2.5 Pro).
        retriever: Retriever activo de la sesión (Hybrid RAG + Cohere).
        vector_store: FAISS vector store para búsqueda exacta de cláusulas.
    """
    from contractia.agents.scout import AgenteScout
    return AgenteScout(llm=llm, retriever=retriever, vector_store=vector_store)
