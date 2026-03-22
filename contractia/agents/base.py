"""
Clase base para agentes especialistas y parsing robusto de JSON.
"""

import json
import re
from typing import Any, Optional, Type

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel


def _reparar_json_truncado(texto: str) -> Any:
    """
    Repara un array JSON truncado por max_output_tokens.
    Ejemplo: '[{"a":1}, {"b":2}, {"c":3' → [{"a":1}, {"b":2}]
    Retorna la lista de objetos completos o None si no es reparable.
    """
    texto = texto.strip()
    if not texto.startswith("["):
        return None
    ultimo_cierre = texto.rfind("}")
    if ultimo_cierre < 0:
        return None
    candidato = texto[:ultimo_cierre + 1].rstrip(",").rstrip() + "]"
    candidato = re.sub(r",\s*]", "]", candidato)
    try:
        resultado = json.loads(candidato)
        if isinstance(resultado, list):
            return resultado
    except json.JSONDecodeError:
        pass
    return None


def parse_json_seguro(texto_llm: str) -> Any:
    """
    Parsea JSON con recuperación de truncados.

    Idéntico al notebook para JSON completo, pero con recuperación
    adicional para secciones largas donde max_output_tokens corta
    la respuesta a mitad del JSON (ej. Cap IX Garantías, 25+ tripletas).
    """
    if not texto_llm:
        return {}

    texto = texto_llm.strip()

    # Eliminar bloque de razonamiento <razonamiento>...</razonamiento>
    texto = re.sub(r"<razonamiento>.*?</razonamiento>", "", texto, flags=re.DOTALL).strip()

    # Limpiar markdown (incluye caso sin cierre ``` por truncamiento)
    if "```" in texto:
        match = re.search(r"```(?:json)?(.*?)```", texto, re.DOTALL | re.IGNORECASE)
        if match:
            texto = match.group(1).strip()
        else:
            match = re.search(r"```(?:json)?(.*)", texto, re.DOTALL)
            if match:
                texto = match.group(1).strip()

    if "sin inconsistencias" in texto.lower() or "no se encontraron errores" in texto.lower():
        return {}

    texto = re.sub(r"//.*", "", texto)
    texto = re.sub(r",\s*([\]}])", r"\1", texto)

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        try:
            match = re.search(r"(\{.*\}|\[.*\])", texto, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        # Reparar JSON truncado: array cortado sin ] de cierre
        resultado = _reparar_json_truncado(texto)
        if resultado is not None:
            return resultado
        return {}


class AgenteEspecialista:
    """
    Agente que ejecuta un prompt contra un LLM y devuelve la salida parseada.

    Si se proporciona `output_schema`, usa with_structured_output para garantizar
    el schema Pydantic sin regex. Si no, usa parse_json_seguro como fallback.
    """

    def __init__(
        self,
        llm,
        role_prompt: PromptTemplate,
        output_schema: Optional[Type[BaseModel]] = None,
    ):
        self.llm = llm
        self.prompt = role_prompt
        self.output_schema = output_schema

        # Claude via Vertex AI (ChatAnthropicVertex) no es totalmente compatible
        # con with_structured_output en todas las versiones de langchain_google_vertexai.
        # Para Claude se usa el pipeline de texto plano + parse_json_seguro;
        # los prompts ya incluyen instrucciones JSON explícitas.
        _model_name = str(getattr(llm, "model_name", "") or "")
        _is_claude = _model_name.startswith("claude-")

        if output_schema is not None and not _is_claude:
            llm_structured = llm.with_structured_output(output_schema)
            self.chain = self.prompt | llm_structured
        else:
            self.chain = self.prompt | self.llm | StrOutputParser()

    def ejecutar(self, inputs: dict) -> Any:
        result = self.chain.invoke(inputs)
        if isinstance(result, str):
            # Respuesta de texto (Claude o cadena sin structured_output)
            return parse_json_seguro(result)
        if self.output_schema is not None:
            # Objeto Pydantic de with_structured_output → dict
            return result.model_dump() if hasattr(result, "model_dump") else result
        return parse_json_seguro(str(result))
