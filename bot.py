"""
ContractIA Bot — Punto de entrada del bot de Telegram.

Uso:
    python bot.py

Requiere en .env:
    TELEGRAM_TOKEN     = token obtenido de @BotFather
    TELEGRAM_ADMIN_ID  = tu user_id de Telegram (@userinfobot)
    EMAIL_SENDER       = tu_correo@gmail.com
    EMAIL_PASSWORD     = App Password de Gmail (no la contraseña de cuenta)
"""

import logging
import traceback

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from contractia.config import TELEGRAM_TOKEN
from contractia.telegram.db.database import init_db
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

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN no configurado. Agrégalo al archivo .env y vuelve a intentar."
        )

    # Inicializar base de datos
    init_db()
    logger.info("Base de datos inicializada correctamente.")

    # Construir la aplicación
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ── Comandos ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("login",  cmd_login))
    app.add_handler(CommandHandler("menu",   cmd_menu))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # ── Documentos (PDF / DOCX) ───────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # ── Mensajes de texto ─────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # ── Botones inline ────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Error handler (muestra excepciones en consola) ────────────────────────
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Excepción en handler:", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                f"⚠️ Error interno:\n`{type(context.error).__name__}: {str(context.error)[:200]}`",
                parse_mode="Markdown",
            )

    app.add_error_handler(error_handler)

    logger.info("Bot ContractIA iniciado. Presiona Ctrl+C para detener.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
