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
from contractia.core.graph import GrafoCancelledError, construir_grafo_conocimiento, obtener_contexto_grafo, _PROMPT_EXTRACCION
from contractia.core.graph_cache import cache_key, cargar_grafo, guardar_grafo
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.segmenter import separar_en_secciones
from contractia.llm.provider import build_llm
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import registrar_pregunta
from contractia.telegram.sessions import (
    clear_cancel,
    get_grafo,
    get_mapa_textos,
    get_retriever,
    is_cancelled,
    set_vector_store,
)

_PROMPT = (
    "Eres un asistente legal especializado en contratos de concesión. "
    "Responde la pregunta basándote ÚNICAMENTE en el contexto del contrato proporcionado. "
    "Si la respuesta no está en el contexto, dilo claramente.\n\n"
    "REGLA DE CITACIÓN (obligatoria): Al responder, cita siempre las cláusulas o "
    "secciones exactas donde encontraste la información, usando el número de cláusula "
    "(ej. 'cláusula 6.11.a', 'numeral 8.2', 'Anexo III') y el nombre del capítulo o "
    "anexo correspondiente indicado en [Fuente: ...]. "
    "Si la información proviene de varias cláusulas, menciona todas.\n\n"
    "CONTEXTO DEL CONTRATO:\n{contexto}\n\n"
    "{bloque_grafo}"
    "PREGUNTA: {pregunta}\n\n"
    "RESPUESTA:"
)

# LLM cacheado por nombre de modelo
_llm_cache: dict = {}


def _dividir_mensaje(texto: str, limite: int = 4096) -> list[str]:
    """Divide un texto largo en partes respetando saltos de línea."""
    if len(texto) <= limite:
        return [texto]
    partes = []
    while texto:
        if len(texto) <= limite:
            partes.append(texto)
            break
        # Buscar el último salto de línea dentro del límite
        corte = texto.rfind("\n", 0, limite)
        if corte <= 0:
            # Sin salto de línea; cortar por último espacio
            corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")
    return partes


def get_llm(modelo: str = "gemini-2.5-pro"):
    if modelo not in _llm_cache:
        _llm_cache[modelo] = build_llm(model_override=modelo)
    return _llm_cache[modelo]


async def indexar_contrato(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ruta_archivo: str,
    graph_enabled: bool = False,
    modelo: str = "gemini-2.5-pro",
) -> bool:
    """
    Extrae el texto del contrato, genera embeddings y guarda el retriever en sesión.
    Si graph_enabled=True, construye además el grafo de conocimiento GraphRAG.
    Retorna True si el indexado fue exitoso.
    """
    user_id = update.effective_user.id
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_{user_id}_query_"))
    clear_cancel(user_id)

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

        secciones = await asyncio.get_event_loop().run_in_executor(
            None, lambda: separar_en_secciones(texto)
        )
        vector_store = await asyncio.get_event_loop().run_in_executor(
            None, lambda: crear_vector_store(texto, secciones)
        )
        retriever = crear_retriever(vector_store, k=RAG_TOP_K)

        grafo = None
        mapa_textos = None

        if graph_enabled:
            mapa_textos = {
                s.get("numero", ""): s
                for s in secciones
                if s.get("numero")
            }

            # Buscar grafo en cache (GCS)
            _cache_key = cache_key(texto, _PROMPT_EXTRACCION.template)
            cached = await asyncio.get_event_loop().run_in_executor(
                None, lambda: cargar_grafo(_cache_key)
            )

            if cached:
                grafo, cached_mapa = cached
                if cached_mapa:
                    mapa_textos = cached_mapa
                await update.message.reply_text(
                    "🕸️ Grafo de relaciones cargado desde cache.\n"
                    f"{grafo.number_of_nodes()} nodos, {grafo.number_of_edges()} relaciones",
                )
            else:
                n_secs = len(secciones)
                await update.message.reply_text(
                    f"🕸️ Construyendo grafo de relaciones entre cláusulas "
                    f"({n_secs} secciones)...\n"
                    f"Esto puede tardar ~{n_secs} minutos. Usa /cancel para detener.",
                )
                llm = get_llm(modelo)
                loop = asyncio.get_event_loop()
                chat_id = update.effective_chat.id

                def _progress(i, total, titulo, n_trip):
                    if i % 5 == 0 or i == total:
                        msg = f"🕸️ Grafo [{i}/{total}] {titulo} — {n_trip} relaciones"
                        asyncio.run_coroutine_threadsafe(
                            context.bot.send_message(chat_id=chat_id, text=msg),
                            loop,
                        )

                def _check_cancel():
                    return is_cancelled(user_id)

                grafo = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: construir_grafo_conocimiento(
                        secciones, llm, on_progress=_progress, cancel_check=_check_cancel,
                    )
                )

                # Guardar en cache para futuros usos
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: guardar_grafo(_cache_key, grafo, mapa_textos)
                )

        set_vector_store(user_id, vector_store, retriever, grafo=grafo, mapa_textos=mapa_textos, texto=texto, secciones=secciones)

        modo = "RAG + GraphRAG" if graph_enabled else "RAG"
        await update.message.reply_text(
            f"✅ Contrato indexado correctamente ({modo}).\n"
            "Ahora puedes escribir tus preguntas.\n"
            "Usa /menu para volver al menú principal.",
        )
        return True

    except GrafoCancelledError:
        await update.message.reply_text("⛔ Construcción del grafo cancelada. Usa /menu para comenzar de nuevo.")
        return False
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al indexar el contrato:\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
        )
        return False
    finally:
        clear_cancel(user_id)
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

    modelo = context.user_data.get("modelo", "gemini-2.5-pro")
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
        llm = get_llm(modelo)

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

        registrar_pregunta(user_id)
        _log(user_id, "pregunta", pregunta[:200], duracion=duracion, canal="bot")

        # Telegram limita a 4096 chars por mensaje; dividir si es necesario
        texto_completo = f"💬 {texto}"
        if len(texto_completo) <= 4096:
            await update.message.reply_text(texto_completo)
        else:
            partes = _dividir_mensaje(texto_completo, 4096)
            for parte in partes:
                await update.message.reply_text(parte)

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
