"""
Fábrica de agentes: crea Jurista, Auditor y Cronista.
"""

from typing import Tuple

from contractia.agents.base import AgenteEspecialista
from contractia.agents.prompts import PROMPT_AUDITOR, PROMPT_CRONISTA, PROMPT_JURISTA
from contractia.agents.schemas import SalidaAuditor, SalidaCronista, SalidaJurista


def crear_agentes(llm) -> Tuple[AgenteEspecialista, AgenteEspecialista, AgenteEspecialista]:
    """Crea los tres agentes especialistas con salida estructurada garantizada."""
    jurista  = AgenteEspecialista(llm, PROMPT_JURISTA,  output_schema=SalidaJurista)
    auditor  = AgenteEspecialista(llm, PROMPT_AUDITOR,  output_schema=SalidaAuditor)
    cronista = AgenteEspecialista(llm, PROMPT_CRONISTA, output_schema=SalidaCronista)
    return jurista, auditor, cronista
