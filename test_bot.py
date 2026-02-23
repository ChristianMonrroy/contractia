"""Test mínimo para verificar que el polling funciona."""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from contractia.config import TELEGRAM_TOKEN

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[TEST] Mensaje recibido de: {update.effective_user.id}", flush=True)
    await update.message.reply_text("✅ Bot funcionando correctamente.")

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
print("Bot de prueba iniciado...")
app.run_polling(drop_pending_updates=True)
