"""
Clase base para agentes especialistas y parsing robusto de JSON.
"""

import json
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate


def parse_json_seguro(texto_llm: str) -> Any:
    """
    Parsea JSON incluso si tiene errores comunes de LLM
    (comas extra, markdown, comentarios).
    """
    if not texto_llm:
        return {}

    texto = texto_llm.strip()

    # Limpiar markdown
    if "```" in texto:
        match = re.search(r"```(?:json)?(.*?)```", texto, re.DOTALL)
        if match:
            texto = match.group(1).strip()

    # Filtros de falso positivo
    if "sin inconsistencias" in texto.lower() or "no se encontraron errores" in texto.lower():
        return {}

    # Limpieza de sintaxis
    texto = re.sub(r"//.*", "", texto)  # Comentarios
    texto = re.sub(r",\s*([\]}])", r"\1", texto)  # Comas finales

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        try:
            match = re.search(r"(\{.*\}|\[.*\])", texto, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return {}


class AgenteEspecialista:
    """Agente que ejecuta un prompt contra un LLM y parsea la salida como JSON."""

    def __init__(self, llm, role_prompt: PromptTemplate):
        self.llm = llm
        self.prompt = role_prompt
        self.chain = self.prompt | self.llm | StrOutputParser()

    def ejecutar(self, inputs: dict) -> Any:
        try:
            raw_output = self.chain.invoke(inputs)
            return parse_json_seguro(raw_output)
        except Exception as e:
            print(f"⚠️ Error en ejecución de Agente: {e}")
            return {}
