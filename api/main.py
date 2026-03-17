"""
ContractIA — Aplicación principal FastAPI.

Expone:
  - API REST para la web (auth, contracts, admin)
  - Webhook de Telegram (reemplaza el modo polling)
  - Health check
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from api.routers.admin_router import router as admin_router
from api.routers.auth_router import router as auth_router
from api.routers.contracts_router import router as contracts_router, start_queue_worker
from contractia.config import TELEGRAM_ADMIN_ID, TELEGRAM_TOKEN
from contractia.queue.audit_queue import AuditJob, enqueue_audit
from contractia.telegram.db.database import init_db, get_auditorias_en_cola, actualizar_auditoria
from contractia.telegram.handler import (
    cmd_admin,
    cmd_cancel,
    cmd_login,
    cmd_logout,
    cmd_menu,
    cmd_start,
    cmd_status,
    handle_callback,
    handle_document,
    handle_text,
)

logger = logging.getLogger(__name__)

WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")  # ej: https://api.contractia.pe

# Instancia global del bot de Telegram
_tg_app: Application = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y cierre de la app."""
    global _tg_app

    # Base de datos
    init_db()
    logger.info("✅ Base de datos inicializada.")

    # Reconstitución de la cola al arrancar (por si Cloud Run reinició con trabajos pendientes)
    try:
        jobs_pendientes = get_auditorias_en_cola()
        if jobs_pendientes:
            logger.info(f"🔄 Reconstituyendo {len(jobs_pendientes)} trabajo(s) pendiente(s) en cola...")
        for job_data in jobs_pendientes:
            actualizar_auditoria(
                job_data["audit_id"],
                status="queued",
                progress_msg="En cola (reconstitución tras reinicio)",
                progress_pct=0,
            )
            job = AuditJob(
                audit_id=job_data["audit_id"],
                user_id=job_data["user_id"],
                filename=job_data.get("filename") or "",
                email=job_data.get("email") or "",
                graph_enabled=bool(job_data.get("graph_enabled")),
                is_admin=job_data.get("rol") == "admin",
                modelo=job_data.get("modelo_usado") or "gemini-2.5-pro",
                gcs_uri=job_data.get("gcs_uri"),
            )
            await enqueue_audit(job)
    except Exception as e:
        logger.warning(f"⚠️ Error en reconstitución de cola: {e}")

    # Worker de cola de auditorías
    _queue_worker_task = start_queue_worker()
    logger.info("✅ Worker de cola de auditorías iniciado.")

    # Bot de Telegram
    _tg_app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registrar handlers (igual que bot.py en modo polling)
    _tg_app.add_handler(CommandHandler("start",  cmd_start))
    _tg_app.add_handler(CommandHandler("login",  cmd_login))
    _tg_app.add_handler(CommandHandler("menu",   cmd_menu))
    _tg_app.add_handler(CommandHandler("logout", cmd_logout))
    _tg_app.add_handler(CommandHandler("status", cmd_status))
    _tg_app.add_handler(CommandHandler("admin",  cmd_admin))
    _tg_app.add_handler(CommandHandler("cancel", cmd_cancel))
    _tg_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    _tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    _tg_app.add_handler(CallbackQueryHandler(handle_callback))

    await _tg_app.initialize()
    await _tg_app.start()

    if WEBHOOK_URL:
        try:
            await _tg_app.bot.set_webhook(
                url=f"{WEBHOOK_URL}/telegram/webhook",
                allowed_updates=["message", "callback_query"],
            )
            logger.info(f"✅ Webhook de Telegram configurado: {WEBHOOK_URL}/telegram/webhook")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo registrar el webhook ({e}). El bot no recibirá mensajes hasta que el dominio esté activo.")
    else:
        logger.warning("⚠️ WEBHOOK_URL no configurada. El bot no recibirá mensajes.")

    yield

    # Shutdown
    _queue_worker_task.cancel()
    await _tg_app.stop()
    await _tg_app.shutdown()
    logger.info("Bot detenido.")


app = FastAPI(
    title="ContractIA API",
    version="7.0.2",
    description="Sistema de auditoría inteligente de contratos",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://contractia.pe", "https://www.contractia.pe", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(contracts_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "7.0.2"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Recibe updates de Telegram y los procesa con el bot."""
    if _tg_app is None:
        return {"ok": False}
    data = await request.json()
    update = Update.de_json(data, _tg_app.bot)
    asyncio.create_task(_tg_app.process_update(update))
    return {"ok": True}
