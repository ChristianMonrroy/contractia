"""
Agente Scout: pre-fase agéntica para Agentic RAG (v9.0.0).

Corre ANTES de Jurista/Auditor/Cronista. Usa tool calling (bind_tools de LangChain)
para decidir dinámicamente qué contexto adicional recuperar del contrato mediante
un ReAct loop manual.

NOTA IMPORTANTE: bind_tools y with_structured_output son incompatibles en LangChain.
El Scout es una clase separada a AgenteEspecialista; su salida es un string de
contexto, no un objeto Pydantic.

Si AGENTIC_RAG_ENABLED=false (default), el Scout nunca se instancia y el pipeline
funciona exactamente igual que v8.8.0 (RAG estático).
"""

import logging
from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from contractia.config import SCOUT_MAX_ITER, SCOUT_MAX_TOKENS

logger = logging.getLogger(__name__)

_SCOUT_SYSTEM = """Eres un Agente Scout especializado en recuperar contexto legal adicional \
de contratos peruanos antes de que los auditores analicen una sección.

Tu tarea:
1. Lee la sección de contrato proporcionada.
2. Identifica qué información adicional necesitas para auditarla correctamente:
   - Otras cláusulas referenciadas explícitamente (usa obtener_clausula)
   - Conceptos o términos que requieren contexto de otras secciones (usa buscar_en_contrato)
3. Haz hasta {max_iter} consultas a las herramientas disponibles.
4. Cuando tengas suficiente contexto (o no necesites más), responde: "SCOUT_LISTO"

Si la sección es autosuficiente, responde directamente: "SCOUT_LISTO"
"""


def _crear_tools(retriever, vector_store):
    """
    Crea las tools del Scout cerrando sobre retriever y vector_store.
    Se generan aquí para tener closures independientes por instancia de Scout.
    """
    from contractia.rag.pipeline import buscar_clausula, recuperar_contexto

    @tool
    def buscar_en_contrato(consulta: str) -> str:
        """Busca fragmentos relevantes del contrato dado una consulta en lenguaje natural.
        Usa Hybrid RAG (BM25 + FAISS + Cohere reranker si disponible).
        Útil para encontrar contexto semántico relacionado con la sección actual.

        Args:
            consulta: Descripción del contexto que necesitas encontrar.
                      Ejemplo: "penalidades por incumplimiento de plazo de entrega"

        Returns:
            Fragmentos relevantes del contrato, o vacío si no se encuentra nada.
        """
        try:
            return recuperar_contexto(retriever, consulta, max_tokens=SCOUT_MAX_TOKENS // 2)
        except Exception as e:
            logger.warning(f"Scout buscar_en_contrato falló: {e}")
            return ""

    @tool
    def obtener_clausula(numero: str) -> str:
        """Recupera el texto de una cláusula específica por su número.
        Útil cuando la sección actual hace referencia explícita a otra cláusula.

        Args:
            numero: Número de la cláusula a recuperar.
                    Ejemplos: "3.2", "8", "15.1.a", "Anexo B"

        Returns:
            Texto de la cláusula encontrada, o vacío si no existe.
        """
        if vector_store is None:
            return ""
        try:
            return buscar_clausula(vector_store, numero)
        except Exception as e:
            logger.warning(f"Scout obtener_clausula falló: {e}")
            return ""

    return [buscar_en_contrato, obtener_clausula]


class AgenteScout:
    """
    Agente pre-fase con tool calling para Agentic RAG.

    Implementa un ReAct loop manual porque bind_tools es incompatible
    con with_structured_output en LangChain.

    Args:
        llm: LLM provider (VertexAI Gemini). Debe soportar tool calling.
        retriever: Retriever activo de la sesión (Hybrid RAG + Cohere).
        vector_store: FAISS vector store (para buscar cláusulas exactas).
        max_iter: Máximo de iteraciones LLM+tools (default: SCOUT_MAX_ITER).
    """

    def __init__(self, llm, retriever, vector_store, max_iter: int = SCOUT_MAX_ITER):
        self.max_iter = max_iter
        self.tools = _crear_tools(retriever, vector_store)
        self.tools_by_name = {t.name: t for t in self.tools}
        self.llm_with_tools = llm.bind_tools(self.tools)

    def ejecutar(self, texto_seccion: str) -> str:
        """
        Ejecuta el loop agéntico del Scout sobre una sección del contrato.

        Args:
            texto_seccion: Texto de la sección a auditar (se trunca a 4000 chars).

        Returns:
            String de contexto enriquecido para concatenar al texto de los agentes.
            Retorna "" si no se encontró contexto adicional útil.
            Nunca lanza excepción (degradación silenciosa a RAG estático).
        """
        try:
            return self._loop(texto_seccion)
        except Exception as e:
            logger.warning(f"AgenteScout falló completamente — usando RAG estático: {e}")
            return ""

    def _loop(self, texto_seccion: str) -> str:
        """ReAct loop manual con historial de mensajes."""
        system = SystemMessage(content=_SCOUT_SYSTEM.format(max_iter=self.max_iter))
        human = HumanMessage(content=f"Sección a auditar:\n\n{texto_seccion[:4000]}")
        messages = [system, human]
        acumulado: List[str] = []

        for iteracion in range(self.max_iter):
            response: AIMessage = self.llm_with_tools.invoke(messages)
            messages.append(response)

            # Caso A: LLM no pide más tools → terminó
            if not response.tool_calls:
                break

            # Caso B: LLM pide tools → ejecutar y agregar ToolMessages
            for tc in response.tool_calls:
                fn = self.tools_by_name.get(tc["name"])
                if fn is None:
                    resultado = f"Tool '{tc['name']}' no encontrada."
                else:
                    try:
                        resultado = fn.invoke(tc["args"])
                    except Exception as e:
                        resultado = f"Error ejecutando {tc['name']}: {e}"

                if resultado:
                    label = f"[{tc['name']}({tc['args']})]"
                    acumulado.append(f"{label}\n{resultado}")

                messages.append(
                    ToolMessage(content=str(resultado), tool_call_id=tc["id"])
                )

            logger.debug(f"Scout iteración {iteracion + 1}/{self.max_iter} completada.")

        if not acumulado:
            return ""

        return "\n\n---\n\n".join(acumulado)
