"""
Fábrica de agentes: crea Jurista, Auditor y Cronista.
"""

from typing import Tuple

from contractia.agents.base import AgenteEspecialista
from contractia.agents.prompts import PROMPT_AUDITOR, PROMPT_CRONISTA, PROMPT_JURISTA


def crear_agentes(llm) -> Tuple[AgenteEspecialista, AgenteEspecialista, AgenteEspecialista]:
    """Crea los tres agentes especialistas."""
    jurista  = AgenteEspecialista(llm, PROMPT_JURISTA)
    auditor  = AgenteEspecialista(llm, PROMPT_AUDITOR)
    cronista = AgenteEspecialista(llm, PROMPT_CRONISTA)
    return jurista, auditor, cronista
