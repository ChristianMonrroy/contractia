"""
Flujo de auditoría completa para el bot de Telegram.

Descarga el archivo del usuario, ejecuta el pipeline multi-agente
y devuelve el informe como documento adjunto.
"""

import asyncio
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from contractia.core.graph import _PROMPT_EXTRACCION
from contractia.core.graph_cache import borrar_grafo, cache_key, cargar_grafo
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.report import render_auditoria_markdown
from contractia.llm.provider import build_llm
from contractia.orchestrator import PromptInjectionDetectedError, ejecutar_auditoria_contrato
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import registrar_auditoria

# Solo se permite una auditoría a la vez en todo el sistema
_auditoria_lock = asyncio.Semaphore(1)


async def ejecutar_auditoria(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ruta_archivo: str,
    graph_enabled: bool = False,
    modelo: str = "gemini-2.5-pro",
    force_rebuild_graph: bool = False,
) -> None:
    """Orquesta la auditoría completa y envía el informe al usuario."""
    if _auditoria_lock.locked():
        await update.message.reply_text(
            "⏳ Hay una auditoría en proceso en este momento.\n"
            "Por favor intenta de nuevo en unos minutos."
        )
        return

    user_id = update.effective_user.id
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_{user_id}_audit_"))
    _waiting_callback = False

    # Pre-check: extraer texto y verificar cache ANTES de adquirir el lock
    try:
        shutil.copy2(ruta_archivo, tmp_dir)

        await update.message.reply_text("📄 Extrayendo texto del contrato...")
        _, texto = await asyncio.get_event_loop().run_in_executor(
            None, lambda: procesar_documentos_carpeta(tmp_dir)
        )

        if not texto:
            await update.message.reply_text("❌ No pude extraer texto del archivo. Verifica que no esté protegido.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

        # Verificar si hay grafo cacheado y preguntar al usuario
        if graph_enabled and not force_rebuild_graph:
            _cache_key = cache_key(texto, _PROMPT_EXTRACCION.template)
            cached = await asyncio.get_event_loop().run_in_executor(
                None, lambda: cargar_grafo(_cache_key)
            )
            if cached:
                grafo_cached, _ = cached
                # Guardar datos para reanudar después del callback
                context.user_data["audit_pending"] = {
                    "ruta_archivo": ruta_archivo,
                    "graph_enabled": graph_enabled,
                    "modelo": modelo,
                    "texto": texto,
                    "tmp_dir": str(tmp_dir),
                }
                await update.message.reply_text(
                    f"🕸️ Se encontró un grafo existente para este contrato.\n"
                    f"{grafo_cached.number_of_nodes()} nodos, {grafo_cached.number_of_edges()} relaciones.\n\n"
                    "Deseas reutilizarlo o reconstruirlo desde cero?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("♻️ Reutilizar", callback_data="audit_cache_reuse"),
                            InlineKeyboardButton("🔄 Reconstruir", callback_data="audit_cache_rebuild"),
                        ]
                    ]),
                )
                return  # No borrar tmp_dir — se usará en el callback
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al preparar la auditoría:\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    async with _auditoria_lock:
        try:
            # Si force_rebuild_graph, borrar cache primero
            if graph_enabled and force_rebuild_graph:
                _cache_key = cache_key(texto, _PROMPT_EXTRACCION.template)
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: borrar_grafo(_cache_key)
                )

            modo = "RAG + GraphRAG" if graph_enabled else "RAG"
            nombre_modelo = "Gemini 3.1 Pro Preview" if modelo == "gemini-3.1-pro-preview" else "Gemini 2.5 Pro"
            await update.message.reply_text(
                f"🔍 Analizando el contrato con los agentes de IA ({modo})...\n"
                f"Modelo: {nombre_modelo}\n"
                "Esto puede tardar varios minutos segun el tamano del contrato.",
            )

            llm = await asyncio.get_event_loop().run_in_executor(
                None, lambda: build_llm(model_override=modelo)
            )
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(
                    texto, llm, graph_enabled=graph_enabled, modelo=modelo,
                    user_id=user_id, filename=Path(ruta_archivo).name,
                )
            )
            duracion = round(time.time() - start, 1)

            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            registrar_auditoria(user_id)
            _log(user_id, "auditoria", Path(ruta_archivo).name,
                 duracion=duracion, canal="bot", n_hallazgos=n_hallazgos)

            # Guardar informe y enviarlo como archivo adjunto
            informe_path = tmp_dir / "informe_auditoria.md"
            informe_path.write_text(md, encoding="utf-8")

            n_secciones = len(resultado.get("resultados_auditoria", []))

            await update.message.reply_text("✅ Auditoría completada. Enviando informe...")

            with open(informe_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename="informe_auditoria_contrato.md",
                    caption=(
                        f"📋 *Informe de Auditoría ContractIA*\n"
                        f"• Modo: {modo}\n"
                        f"• Modelo: {nombre_modelo}\n"
                        f"• Secciones con hallazgos: {n_secciones}\n"
                        f"• Total de hallazgos: {n_hallazgos}"
                    ),
                    parse_mode="Markdown",
                )

        except PromptInjectionDetectedError:
            await update.message.reply_text(
                "🚨 *ALERTA DE SEGURIDAD*\n\n"
                "Se ha detectado contenido sospechoso en el documento que podría "
                "comprometer el análisis de IA\\. La auditoría ha sido cancelada "
                "por seguridad\\.\n\n"
                "El administrador ha sido notificado\\.",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error durante la auditoría:\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


async def ejecutar_auditoria_desde_texto(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    texto: str,
    ruta_archivo: str,
    tmp_dir: str,
    graph_enabled: bool = False,
    modelo: str = "gemini-2.5-pro",
    force_rebuild_graph: bool = False,
) -> None:
    """Continúa una auditoría con texto ya extraído (tras decisión de cache)."""
    user_id = message.chat.id
    tmp_dir_path = Path(tmp_dir)

    if force_rebuild_graph:
        _ck = cache_key(texto, _PROMPT_EXTRACCION.template)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: borrar_grafo(_ck)
        )

    async with _auditoria_lock:
        try:
            modo = "RAG + GraphRAG" if graph_enabled else "RAG"
            nombre_modelo = "Gemini 3.1 Pro Preview" if modelo == "gemini-3.1-pro-preview" else "Gemini 2.5 Pro"
            await message.reply_text(
                f"🔍 Analizando el contrato con los agentes de IA ({modo})...\n"
                f"Modelo: {nombre_modelo}\n"
                "Esto puede tardar varios minutos segun el tamano del contrato.",
            )

            llm = await asyncio.get_event_loop().run_in_executor(
                None, lambda: build_llm(model_override=modelo)
            )
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(
                    texto, llm, graph_enabled=graph_enabled, modelo=modelo,
                    user_id=user_id, filename=Path(ruta_archivo).name,
                )
            )
            duracion = round(time.time() - start, 1)

            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            registrar_auditoria(user_id)
            _log(user_id, "auditoria", Path(ruta_archivo).name,
                 duracion=duracion, canal="bot", n_hallazgos=n_hallazgos)

            informe_path = tmp_dir_path / "informe_auditoria.md"
            informe_path.write_text(md, encoding="utf-8")
            n_secciones = len(resultado.get("resultados_auditoria", []))

            await message.reply_text("✅ Auditoría completada. Enviando informe...")
            with open(informe_path, "rb") as f:
                await message.reply_document(
                    document=f,
                    filename="informe_auditoria_contrato.md",
                    caption=(
                        f"📋 *Informe de Auditoría ContractIA*\n"
                        f"• Modo: {modo}\n"
                        f"• Modelo: {nombre_modelo}\n"
                        f"• Secciones con hallazgos: {n_secciones}\n"
                        f"• Total de hallazgos: {n_hallazgos}"
                    ),
                    parse_mode="Markdown",
                )

        except PromptInjectionDetectedError:
            await message.reply_text(
                "🚨 ALERTA DE SEGURIDAD\n\n"
                "Se ha detectado contenido sospechoso en el documento. "
                "La auditoría ha sido cancelada por seguridad.\n\n"
                "El administrador ha sido notificado.",
            )
        except Exception as e:
            await message.reply_text(
                f"❌ Error durante la auditoría:\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
        finally:
            shutil.rmtree(tmp_dir_path, ignore_errors=True)


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
