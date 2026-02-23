"""
Flujo de consultas RAG para el bot de Telegram.

Indexa el contrato del usuario y responde preguntas libres.
"""

import asyncio
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from contractia.config import RAG_TOP_K
from contractia.core.loader import procesar_documentos_carpeta
from contractia.llm.provider import build_llm
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import registrar_pregunta
from contractia.telegram.sessions import get_retriever, set_vector_store

_PROMPT = (
    "Eres un asistente legal especializado en contratos de concesión. "
    "Responde la pregunta basándote ÚNICAMENTE en el contexto del contrato proporcionado. "
    "Si la respuesta no está en el contexto, dilo claramente.\n\n"
    "CONTEXTO DEL CONTRATO:\n{contexto}\n\n"
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
) -> bool:
    """
    Extrae el texto del contrato, genera embeddings y guarda el retriever en sesión.
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
        set_vector_store(user_id, vector_store, retriever)

        await update.message.reply_text(
            "✅ Contrato indexado correctamente.\n"
            "Ahora puedes escribir tus preguntas.\n"
            "Usa /menu para volver al menú principal."
        )
        return True

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al indexar el contrato:\n`{str(e)[:300]}`",
            parse_mode="Markdown",
        )
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def responder_pregunta(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Recupera contexto RAG y genera respuesta con el LLM."""
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

        prompt = _PROMPT.format(contexto=contexto, pregunta=pregunta)
        llm = get_llm()

        respuesta = await asyncio.get_event_loop().run_in_executor(
            None, lambda: llm.invoke(prompt)
        )

        texto = respuesta.content if hasattr(respuesta, "content") else str(respuesta)

        # Telegram tiene límite de 4096 caracteres por mensaje
        if len(texto) > 4000:
            texto = texto[:4000] + "\n\n_[...respuesta truncada por límite de Telegram]_"

        registrar_pregunta(user_id)
        _log(user_id, "pregunta", pregunta[:200])

        await update.message.reply_text(f"💬 {texto}", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al generar la respuesta:\n`{str(e)[:200]}`",
            parse_mode="Markdown",
        )


def _log(telegram_id: int, accion: str, detalle: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (telegram_id, accion, detalle, timestamp) VALUES (?, ?, ?, ?)",
            (telegram_id, accion, detalle, datetime.now().isoformat()),
        )
