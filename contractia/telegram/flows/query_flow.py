"""
Flujo de consultas RAG para el bot de Telegram.

Indexa el contrato del usuario y responde preguntas libres.
Soporta GraphRAG opcional: si se activa al indexar, las respuestas
se enriquecen con relaciones entre cláusulas del grafo de conocimiento.
"""

import asyncio
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from contractia.config import RAG_TOP_K
from contractia.core.graph import construir_grafo_conocimiento, obtener_contexto_grafo
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.segmenter import separar_en_secciones
from contractia.llm.provider import build_llm
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import registrar_pregunta
from contractia.telegram.sessions import (
    get_grafo,
    get_mapa_textos,
    get_retriever,
    set_vector_store,
)

_PROMPT = (
    "Eres un asistente legal especializado en contratos de concesión. "
    "Responde la pregunta basándote ÚNICAMENTE en el contexto del contrato proporcionado. "
    "Si la respuesta no está en el contexto, dilo claramente.\n\n"
    "CONTEXTO DEL CONTRATO:\n{contexto}\n\n"
    "{bloque_grafo}"
    "PREGUNTA: {pregunta}\n\n"
    "RESPUESTA:"
)

# LLM compartido para toda la sesión del bot
_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


async def indexar_contrato(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ruta_archivo: str,
    graph_enabled: bool = False,
) -> bool:
    """
    Extrae el texto del contrato, genera embeddings y guarda el retriever en sesión.
    Si graph_enabled=True, construye además el grafo de conocimiento GraphRAG.
    Retorna True si el indexado fue exitoso.
    """
    user_id = update.effective_user.id
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_{user_id}_query_"))

    try:
        shutil.copy2(ruta_archivo, tmp_dir)

        await update.message.reply_text("📄 Extrayendo texto del contrato...")
        _, texto = await asyncio.get_event_loop().run_in_executor(
            None, lambda: procesar_documentos_carpeta(tmp_dir)
        )

        if not texto:
            await update.message.reply_text("❌ No pude extraer texto del archivo.")
            return False

        await update.message.reply_text("🔍 Generando embeddings... (puede tardar ~1 minuto)")

        vector_store = await asyncio.get_event_loop().run_in_executor(
            None, lambda: crear_vector_store(texto)
        )
        retriever = crear_retriever(vector_store, k=RAG_TOP_K)

        grafo = None
        mapa_textos = None

        if graph_enabled:
            await update.message.reply_text(
                "🕸️ Construyendo grafo de relaciones entre cláusulas...\n"
                "_(Esto agrega ~2-3 minutos adicionales)_",
                parse_mode="Markdown",
            )
            llm = get_llm()
            secciones = await asyncio.get_event_loop().run_in_executor(
                None, lambda: separar_en_secciones(texto)
            )
            mapa_textos = {
                s.get("numero", ""): s
                for s in secciones
                if s.get("numero")
            }
            grafo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: construir_grafo_conocimiento(secciones, llm)
            )

        set_vector_store(user_id, vector_store, retriever, grafo=grafo, mapa_textos=mapa_textos)

        modo = "RAG + GraphRAG" if graph_enabled else "RAG"
        await update.message.reply_text(
            f"✅ Contrato indexado correctamente \\({modo}\\)\\.\n"
            "Ahora puedes escribir tus preguntas\\.\n"
            "Usa /menu para volver al menú principal\\.",
            parse_mode="MarkdownV2",
        )
        return True

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al indexar el contrato:\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
        )
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def responder_pregunta(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Recupera contexto RAG (y GraphRAG si está activo) y genera respuesta con el LLM."""
    user_id = update.effective_user.id
    pregunta = update.message.text.strip()

    retriever = get_retriever(user_id)
    if not retriever:
        await update.message.reply_text(
            "❌ No hay contrato cargado. Usa /menu para subir uno."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        contexto = await asyncio.get_event_loop().run_in_executor(
            None, lambda: recuperar_contexto(retriever, pregunta, max_tokens=3000)
        )

        if not contexto:
            await update.message.reply_text(
                "⚠️ No encontré información relevante sobre eso en el contrato."
            )
            return

        # Enriquecer con GraphRAG si está disponible en sesión
        bloque_grafo = ""
        G = get_grafo(user_id)
        mapa_textos = get_mapa_textos(user_id)
        if G is not None and G.number_of_nodes() > 0:
            clausulas = re.findall(r"\d+(?:\.\d+)+", pregunta)
            ctx_grafo = obtener_contexto_grafo(clausulas or [], G, mapa_textos or {})
            if ctx_grafo and "No hay relaciones" not in ctx_grafo:
                bloque_grafo = f"RELACIONES DEL GRAFO:\n{ctx_grafo}\n\n"

        prompt = _PROMPT.format(
            contexto=contexto,
            bloque_grafo=bloque_grafo,
            pregunta=pregunta,
        )
        llm = get_llm()

        start = time.time()
        respuesta = await asyncio.get_event_loop().run_in_executor(
            None, lambda: llm.invoke(prompt)
        )
        duracion = round(time.time() - start, 1)

        content = respuesta.content if hasattr(respuesta, "content") else str(respuesta)
        if isinstance(content, list):
            texto = next((b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"), "")
        else:
            texto = content

        # Telegram tiene límite de 4096 caracteres por mensaje
        if len(texto) > 4000:
            texto = texto[:4000] + "\n\n_[...respuesta truncada por límite de Telegram]_"

        registrar_pregunta(user_id)
        _log(user_id, "pregunta", pregunta[:200], duracion=duracion, canal="bot")

        await update.message.reply_text(f"💬 {texto}")

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al generar la respuesta:\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


def _log(
    telegram_id: int,
    accion: str,
    detalle: str,
    duracion: float = None,
    canal: str = "bot",
    n_hallazgos: int = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (telegram_id, accion, detalle, timestamp, "
            "duracion_segundos, canal, n_hallazgos) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (telegram_id, accion, detalle, datetime.now().isoformat(),
             duracion, canal, n_hallazgos),
        )
