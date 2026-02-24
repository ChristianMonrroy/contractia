"""
Flujo de auditoría completa para el bot de Telegram.

Descarga el archivo del usuario, ejecuta el pipeline multi-agente
y devuelve el informe como documento adjunto.
"""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.report import render_auditoria_markdown
from contractia.llm.provider import build_llm
from contractia.orchestrator import ejecutar_auditoria_contrato
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import registrar_auditoria

# Solo se permite una auditoría a la vez en todo el sistema
_auditoria_lock = asyncio.Semaphore(1)


async def ejecutar_auditoria(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ruta_archivo: str,
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

    async with _auditoria_lock:
        try:
            # Copiar archivo a carpeta temporal
            shutil.copy2(ruta_archivo, tmp_dir)

            await update.message.reply_text("📄 Extrayendo texto del contrato...")
            _, texto = await asyncio.get_event_loop().run_in_executor(
                None, lambda: procesar_documentos_carpeta(tmp_dir)
            )

            if not texto:
                await update.message.reply_text("❌ No pude extraer texto del archivo. Verifica que no esté protegido.")
                return

            await update.message.reply_text(
                "🔍 Analizando el contrato con los agentes de IA...\n"
                "_(Esto puede tardar varios minutos según el tamaño del contrato)_",
                parse_mode="Markdown",
            )

            llm = await asyncio.get_event_loop().run_in_executor(None, build_llm)
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(texto, llm)
            )

            md = render_auditoria_markdown(resultado)
            registrar_auditoria(user_id)
            _log(user_id, "auditoria", Path(ruta_archivo).name)

            # Guardar informe y enviarlo como archivo adjunto
            informe_path = tmp_dir / "informe_auditoria.md"
            informe_path.write_text(md, encoding="utf-8")

            n_hallazgos = sum(len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", []))
            n_secciones = len(resultado.get("resultados_auditoria", []))

            await update.message.reply_text("✅ Auditoría completada. Enviando informe...")

            with open(informe_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename="informe_auditoria_contrato.md",
                    caption=(
                        f"📋 *Informe de Auditoría ContractIA*\n"
                        f"• Secciones con hallazgos: {n_secciones}\n"
                        f"• Total de hallazgos: {n_hallazgos}"
                    ),
                    parse_mode="Markdown",
                )

        except Exception as e:
            await update.message.reply_text(
                f"❌ Error durante la auditoría:\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _log(telegram_id: int, accion: str, detalle: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (telegram_id, accion, detalle, timestamp) VALUES (?, ?, ?, ?)",
            (telegram_id, accion, detalle, datetime.now().isoformat()),
        )
