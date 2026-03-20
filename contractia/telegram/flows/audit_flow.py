"""
Flujo de auditoría completa para el bot de Telegram.

Descarga el archivo del usuario, ejecuta el pipeline multi-agente
y devuelve el informe como documento adjunto.
"""

import asyncio
import shutil
import tempfile
import time
import uuid
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
from contractia.telegram.correo.pdf_report import generar_pdf_auditoria
from contractia.telegram.correo.pdf_report_tecnico import generar_pdf_tecnico
from contractia.telegram.correo.sender import enviar_email
from contractia.telegram.correo.templates import email_auditoria_lista
from contractia.telegram.db.database import (
    agregar_log_auditoria,
    actualizar_auditoria,
    crear_auditoria,
    get_conn,
)
from contractia.telegram.db.uso import registrar_auditoria
from contractia.telegram.db.usuarios import get_usuario

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
        print(f"[AUDIT_FLOW] graph_enabled={graph_enabled}, force_rebuild={force_rebuild_graph}, texto_len={len(texto)}", flush=True)
        if graph_enabled and not force_rebuild_graph:
            _cache_key = cache_key(texto, _PROMPT_EXTRACCION.template)
            print(f"[AUDIT_FLOW] cache_key={_cache_key}", flush=True)
            cached = await asyncio.get_event_loop().run_in_executor(
                None, lambda: cargar_grafo(_cache_key)
            )
            print(f"[AUDIT_FLOW] cached={cached is not None}", flush=True)
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

    # Registrar auditoría en DB
    audit_id = str(uuid.uuid4())
    filename = Path(ruta_archivo).name
    try:
        crear_auditoria(
            audit_id=audit_id, user_id=user_id, filename=filename,
            graph_enabled=graph_enabled, status="in_progress",
            modelo_usado=modelo,
        )
    except Exception as e:
        print(f"[AUDIT_FLOW] No se pudo registrar auditoría en DB: {e}", flush=True)

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
            agregar_log_auditoria(audit_id, f"Iniciando auditoría ({modo}) con {nombre_modelo}")

            llm = await asyncio.get_event_loop().run_in_executor(
                None, lambda: build_llm(model_override=modelo)
            )
            _use_cache = graph_enabled and not force_rebuild_graph
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(
                    texto, llm, graph_enabled=graph_enabled, modelo=modelo,
                    user_id=user_id, filename=filename,
                    use_cached_graph=_use_cache, audit_id=audit_id,
                )
            )
            duracion = round(time.time() - start, 1)

            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            registrar_auditoria(user_id)
            _log(user_id, "auditoria", filename,
                 duracion=duracion, canal="bot", n_hallazgos=n_hallazgos)

            n_secciones = len(resultado.get("resultados_auditoria", []))

            # Actualizar auditoría como completada en DB
            actualizar_auditoria(
                audit_id, status="done", informe=md,
                n_hallazgos=n_hallazgos, n_secciones=n_secciones,
                progress_msg="Completado", progress_pct=100,
                modelo_usado=modelo,
            )
            agregar_log_auditoria(audit_id, f"=== Completado === {n_hallazgos} hallazgos | {n_secciones} secciones | {duracion}s")

            # Guardar informe y enviarlo como archivo adjunto
            informe_path = tmp_dir / "informe_auditoria.md"
            informe_path.write_text(md, encoding="utf-8")

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

            # Generar y enviar informe técnico PDF
            metadata_tecnica = resultado.get("metadata_tecnica")
            grafo = resultado.get("grafo")
            imagen_grafo_png = resultado.get("imagen_grafo_png")
            pdf_tecnico_bytes = None
            if metadata_tecnica:
                try:
                    if metadata_tecnica is not None:
                        metadata_tecnica["modelo_usado"] = modelo
                    pdf_tecnico_bytes = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: generar_pdf_tecnico(
                            metadata_tecnica=metadata_tecnica,
                            grafo=grafo,
                            imagen_grafo_png=imagen_grafo_png,
                            filename_contrato=filename,
                            modelo=modelo,
                        )
                    )
                    tecnico_path = tmp_dir / "informe_tecnico.pdf"
                    tecnico_path.write_bytes(pdf_tecnico_bytes)
                    with open(tecnico_path, "rb") as f:
                        await update.message.reply_document(
                            document=f,
                            filename=filename.rsplit(".", 1)[0] + "_tecnico.pdf" if "." in filename else "informe_tecnico.pdf",
                            caption="🔬 Informe Técnico (GraphRAG + Metadata estructural)",
                        )
                except Exception as te:
                    print(f"[BOT-TECNICO] No se pudo generar informe técnico: {te}", flush=True)

            # Enviar email con ambos PDFs adjuntos
            await _enviar_email_informe(user_id, filename, md, n_hallazgos, n_secciones, modelo, pdf_tecnico_bytes)

        except PromptInjectionDetectedError:
            actualizar_auditoria(
                audit_id, status="error",
                error_detail="Prompt injection detectado",
                progress_msg="Bloqueado por seguridad",
            )
            await update.message.reply_text(
                "🚨 *ALERTA DE SEGURIDAD*\n\n"
                "Se ha detectado contenido sospechoso en el documento que podría "
                "comprometer el análisis de IA\\. La auditoría ha sido cancelada "
                "por seguridad\\.\n\n"
                "El administrador ha sido notificado\\.",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            actualizar_auditoria(
                audit_id, status="error",
                error_detail=str(e)[:500],
                progress_msg="Error",
            )
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
    filename = Path(ruta_archivo).name

    # Registrar auditoría en DB
    audit_id = str(uuid.uuid4())
    try:
        crear_auditoria(
            audit_id=audit_id, user_id=user_id, filename=filename,
            graph_enabled=graph_enabled, status="in_progress",
            modelo_usado=modelo,
        )
    except Exception as e:
        print(f"[AUDIT_FLOW] No se pudo registrar auditoría en DB: {e}", flush=True)

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
            agregar_log_auditoria(audit_id, f"Iniciando auditoría ({modo}) con {nombre_modelo}")

            llm = await asyncio.get_event_loop().run_in_executor(
                None, lambda: build_llm(model_override=modelo)
            )
            _use_cache = graph_enabled and not force_rebuild_graph
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(
                    texto, llm, graph_enabled=graph_enabled, modelo=modelo,
                    user_id=user_id, filename=filename,
                    use_cached_graph=_use_cache, audit_id=audit_id,
                )
            )
            duracion = round(time.time() - start, 1)

            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            registrar_auditoria(user_id)
            _log(user_id, "auditoria", filename,
                 duracion=duracion, canal="bot", n_hallazgos=n_hallazgos)

            n_secciones = len(resultado.get("resultados_auditoria", []))

            # Actualizar auditoría como completada en DB
            actualizar_auditoria(
                audit_id, status="done", informe=md,
                n_hallazgos=n_hallazgos, n_secciones=n_secciones,
                progress_msg="Completado", progress_pct=100,
                modelo_usado=modelo,
            )
            agregar_log_auditoria(audit_id, f"=== Completado === {n_hallazgos} hallazgos | {n_secciones} secciones | {duracion}s")

            informe_path = tmp_dir_path / "informe_auditoria.md"
            informe_path.write_text(md, encoding="utf-8")

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

            # Generar y enviar informe técnico PDF
            metadata_tecnica = resultado.get("metadata_tecnica")
            grafo = resultado.get("grafo")
            imagen_grafo_png = resultado.get("imagen_grafo_png")
            pdf_tecnico_bytes = None
            if metadata_tecnica:
                try:
                    if metadata_tecnica is not None:
                        metadata_tecnica["modelo_usado"] = modelo
                    pdf_tecnico_bytes = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: generar_pdf_tecnico(
                            metadata_tecnica=metadata_tecnica,
                            grafo=grafo,
                            imagen_grafo_png=imagen_grafo_png,
                            filename_contrato=filename,
                            modelo=modelo,
                        )
                    )
                    tecnico_path = tmp_dir_path / "informe_tecnico.pdf"
                    tecnico_path.write_bytes(pdf_tecnico_bytes)
                    with open(tecnico_path, "rb") as f:
                        await message.reply_document(
                            document=f,
                            filename=filename.rsplit(".", 1)[0] + "_tecnico.pdf" if "." in filename else "informe_tecnico.pdf",
                            caption="🔬 Informe Técnico (GraphRAG + Metadata estructural)",
                        )
                except Exception as te:
                    print(f"[BOT-TECNICO] No se pudo generar informe técnico: {te}", flush=True)

            # Enviar email con ambos PDFs adjuntos
            await _enviar_email_informe(user_id, filename, md, n_hallazgos, n_secciones, modelo, pdf_tecnico_bytes)

        except PromptInjectionDetectedError:
            actualizar_auditoria(
                audit_id, status="error",
                error_detail="Prompt injection detectado",
                progress_msg="Bloqueado por seguridad",
            )
            await message.reply_text(
                "🚨 ALERTA DE SEGURIDAD\n\n"
                "Se ha detectado contenido sospechoso en el documento. "
                "La auditoría ha sido cancelada por seguridad.\n\n"
                "El administrador ha sido notificado.",
            )
        except Exception as e:
            actualizar_auditoria(
                audit_id, status="error",
                error_detail=str(e)[:500],
                progress_msg="Error",
            )
            await message.reply_text(
                f"❌ Error durante la auditoría:\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
        finally:
            shutil.rmtree(tmp_dir_path, ignore_errors=True)


async def _enviar_email_informe(
    telegram_id: int,
    filename: str,
    md: str,
    n_hallazgos: int,
    n_secciones: int,
    modelo: str,
    pdf_tecnico_bytes: bytes = None,
) -> None:
    """Envía email con el informe PDF + técnico al usuario del bot."""
    try:
        usuario = await asyncio.get_event_loop().run_in_executor(
            None, lambda: get_usuario(telegram_id)
        )
        if not usuario or not usuario.get("email"):
            print(f"[EMAIL-BOT] Usuario {telegram_id} sin email registrado, omitiendo envío.", flush=True)
            return

        email_dest = usuario["email"]
        asunto, html, texto_plain = email_auditoria_lista(filename, n_hallazgos, n_secciones, modelo=modelo)

        pdf_bytes = None
        adjunto_nombre = filename.rsplit(".", 1)[0] + "_informe.pdf" if "." in filename else "informe_auditoria.pdf"
        try:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(
                None, lambda: generar_pdf_auditoria(md, filename, modelo=modelo)
            )
        except Exception as pdf_err:
            print(f"[EMAIL-BOT] No se pudo generar PDF: {pdf_err}", flush=True)

        adjunto_tecnico_nombre = filename.rsplit(".", 1)[0] + "_tecnico.pdf" if "." in filename else "informe_tecnico.pdf"

        await asyncio.get_event_loop().run_in_executor(
            None, lambda: enviar_email(
                email_dest, asunto, html, texto_plain,
                adjunto_pdf=pdf_bytes,
                adjunto_nombre=adjunto_nombre,
                adjunto_pdf_tecnico=pdf_tecnico_bytes,
                adjunto_nombre_tecnico=adjunto_tecnico_nombre,
            )
        )
        print(f"[EMAIL-BOT] Email enviado a {email_dest} (con técnico: {pdf_tecnico_bytes is not None})", flush=True)
    except Exception as e:
        print(f"[EMAIL-BOT] Error al enviar email: {e}", flush=True)


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
