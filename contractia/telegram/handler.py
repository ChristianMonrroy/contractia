"""
Router principal del bot ContractIA.

Implementa una máquina de estados almacenada en context.user_data["estado"].
No usa ConversationHandler para tener control total del flujo multi-paso.

Estados:
    INICIO               → usuario sin sesión activa
    REGISTRO_EMAIL       → esperando el email del nuevo usuario
    REGISTRO_CODIGO      → esperando el código OTP de verificación
    LOGIN_PASSWORD       → esperando contraseña
    MENU                 → usuario autenticado, en el menú principal
    SELECCIONANDO_GRAFO  → eligió modo, esperando si activa GraphRAG (Sí/No)
    SELECCIONANDO_MODELO → eligió GraphRAG, esperando selección de modelo IA
    ESPERANDO_ARCHIVO    → eligió modo + GraphRAG + modelo, debe subir el PDF/DOCX
    MODO_PREGUNTAS       → contrato indexado, loop de preguntas
    ADMIN_ROL_ID         → admin ingresando el telegram_id a modificar
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from contractia.config import TELEGRAM_ADMIN_ID
from contractia.telegram.auth.crypto import generar_codigo_verificacion, generar_password
from contractia.telegram.correo.sender import enviar_email
from contractia.telegram.correo.templates import email_bienvenida, email_verificacion
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.uso import (
    LIMITES,
    get_uso_hoy,
    puede_auditar,
    puede_preguntar,
)
from contractia.telegram.db.usuarios import (
    activar_usuario,
    cambiar_rol,
    crear_usuario,
    existe_email,
    existe_telegram_id,
    get_usuario,
    listar_usuarios,
    suspender_usuario,
    verificar_password,
)
from contractia.telegram.flows.audit_flow import ejecutar_auditoria
from contractia.telegram.flows.query_flow import indexar_contrato, responder_pregunta
from contractia.telegram.sessions import (
    clear_contract,
    get_retriever,
    is_authenticated,
    login_session,
    logout_session,
)

# ── Constantes de estado ──────────────────────────────────────────────────────
INICIO = "inicio"
REGISTRO_EMAIL = "registro_email"
REGISTRO_CODIGO = "registro_codigo"
LOGIN_PASSWORD = "login_password"
MENU = "menu"
SELECCIONANDO_GRAFO = "seleccionando_grafo"
SELECCIONANDO_MODELO = "seleccionando_modelo"
ESPERANDO_ARCHIVO = "esperando_archivo"
MODO_PREGUNTAS = "modo_preguntas"
ADMIN_ROL_ID = "admin_rol_id"


# ── Helpers de estado ─────────────────────────────────────────────────────────

def _estado(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("estado", INICIO)


def _set_estado(context: ContextTypes.DEFAULT_TYPE, estado: str) -> None:
    context.user_data["estado"] = estado


# ── COMANDOS ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    print(f"[DEBUG] /start recibido de user_id={user_id}", flush=True)

    if is_authenticated(user_id):
        await _mostrar_menu(update, context)
        return

    if existe_telegram_id(user_id):
        _set_estado(context, LOGIN_PASSWORD)
        await update.message.reply_text(
            "Bienvenido de nuevo a *ContractIA*.\nIngresa tu contraseña:",
            parse_mode="Markdown",
        )
        return

    _set_estado(context, REGISTRO_EMAIL)
    await update.message.reply_text(
        "Bienvenido a *ContractIA* — Sistema de Auditoría Contractual con IA.\n\n"
        "Para acceder necesitas registrarte.\n"
        "Ingresa tu correo electrónico:",
        parse_mode="Markdown",
    )


async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if is_authenticated(user_id):
        await _mostrar_menu(update, context)
        return

    if not existe_telegram_id(user_id):
        await update.message.reply_text("No tienes cuenta. Usa /start para registrarte.")
        return

    _set_estado(context, LOGIN_PASSWORD)
    await update.message.reply_text("Ingresa tu contraseña:")


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return
    clear_contract(update.effective_user.id)
    await _mostrar_menu(update, context)


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logout_session(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("Sesión cerrada. Usa /login para volver a entrar.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return
    user_id = update.effective_user.id
    usuario = get_usuario(user_id)
    uso = get_uso_hoy(user_id, usuario["rol"])
    limite_aud = uso["auditorias_limite"] if uso["auditorias_limite"] < 999 else "∞"
    limite_preg = uso["preguntas_limite"] if uso["preguntas_limite"] < 999 else "∞"
    await update.message.reply_text(
        f"👤 *Tu cuenta*\n"
        f"• Email: {usuario['email']}\n"
        f"• Nivel: {usuario['rol'].capitalize()}\n\n"
        f"📊 *Uso de hoy*\n"
        f"• Auditorías: {uso['auditorias']}/{limite_aud}\n"
        f"• Preguntas:  {uso['preguntas']}/{limite_preg}",
        parse_mode="Markdown",
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return
    usuario = get_usuario(update.effective_user.id)
    if usuario["rol"] != "admin":
        await update.message.reply_text("No tienes permisos de administrador.")
        return
    await _mostrar_panel_admin(update)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _set_estado(context, INICIO)
    context.user_data.pop("registro_email", None)
    await update.message.reply_text("Operación cancelada. Usa /start para comenzar.")


# ── HANDLER DE TEXTO ──────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    estado = _estado(context)

    if estado == REGISTRO_EMAIL:
        await _handle_registro_email(update, context)
    elif estado == REGISTRO_CODIGO:
        await _handle_registro_codigo(update, context)
    elif estado == LOGIN_PASSWORD:
        await _handle_login(update, context)
    elif estado == MODO_PREGUNTAS:
        await _handle_pregunta(update, context)
    elif estado == ADMIN_ROL_ID:
        await _handle_admin_rol_id(update, context)
    else:
        if is_authenticated(update.effective_user.id):
            await update.message.reply_text("Usa /menu para ver las opciones disponibles.")
        else:
            await update.message.reply_text("Usa /start para comenzar.")


# ── HANDLER DE DOCUMENTOS ─────────────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return

    user_id = update.effective_user.id

    if _estado(context) != ESPERANDO_ARCHIVO:
        await update.message.reply_text(
            "No esperaba un archivo ahora. Usa /menu y elige una opción primero."
        )
        return

    usuario = get_usuario(user_id)
    rol = usuario["rol"]
    modo = context.user_data.get("modo_pendiente", "preguntas")
    graph_enabled = context.user_data.get("graph_enabled", False)
    modelo = context.user_data.get("modelo", "gemini-2.5-pro")

    # Verificar permisos y límites
    if modo == "auditoria":
        if rol == "basico":
            await update.message.reply_text(
                "Tu nivel *Básico* no incluye auditorías completas.\n"
                "Contacta al administrador para actualizar tu cuenta.",
                parse_mode="Markdown",
            )
            return
        if not puede_auditar(user_id, rol):
            limite = LIMITES[rol]["auditorias"]
            await update.message.reply_text(
                f"Alcanzaste el límite diario de auditorías ({limite}/{limite}). Vuelve mañana."
            )
            return
    else:
        if not puede_preguntar(user_id, rol):
            limite = LIMITES[rol]["preguntas"]
            await update.message.reply_text(
                f"Alcanzaste el límite diario de preguntas ({limite}/{limite}). Vuelve mañana."
            )
            return

    doc = update.message.document
    if not doc:
        await update.message.reply_text("Envía el archivo como documento adjunto (no como imagen).")
        return

    extension = Path(doc.file_name or "contrato").suffix.lower()
    if extension not in (".pdf", ".docx"):
        await update.message.reply_text("Solo acepto archivos PDF o DOCX.")
        return

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("El archivo supera el límite de 20 MB de Telegram.")
        return

    await update.message.reply_text(f"⬇️ Descargando {doc.file_name}...")

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=extension, prefix=f"contractia_{user_id}_"
    )
    tg_file = await doc.get_file()
    await tg_file.download_to_drive(tmp.name)
    tmp.close()

    try:
        if modo == "auditoria":
            _set_estado(context, MENU)
            await ejecutar_auditoria(update, context, tmp.name, graph_enabled=graph_enabled, modelo=modelo)
        else:
            exito = await indexar_contrato(update, context, tmp.name, graph_enabled=graph_enabled, modelo=modelo)
            if exito:
                _set_estado(context, MODO_PREGUNTAS)
            else:
                _set_estado(context, MENU)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ── HANDLER DE CALLBACKS (botones inline) ─────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_authenticated(user_id):
        await query.message.reply_text("Sesión expirada. Usa /login.")
        return

    usuario = get_usuario(user_id)
    rol = usuario["rol"]
    data = query.data

    if data in ("modo_preguntas", "modo_auditoria"):
        modo = "preguntas" if data == "modo_preguntas" else "auditoria"
        context.user_data["modo_pendiente"] = modo
        _set_estado(context, SELECCIONANDO_GRAFO)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🕸️ Sí, con GraphRAG", callback_data="graph_si"),
                InlineKeyboardButton("⚡ No, solo RAG",     callback_data="graph_no"),
            ]
        ])
        await query.message.reply_text(
            "🔧 *¿Activar análisis de relaciones entre cláusulas (GraphRAG)?*\n\n"
            "• *Con GraphRAG*: detecta dependencias entre cláusulas — más preciso, "
            "tarda ~30-40 min adicionales según el tamaño del contrato.\n"
            "• *Solo RAG*: búsqueda semántica estándar — más rápido.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    elif data in ("graph_si", "graph_no"):
        if _estado(context) != SELECCIONANDO_GRAFO:
            return
        context.user_data["graph_enabled"] = (data == "graph_si")
        _set_estado(context, SELECCIONANDO_MODELO)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔵 Gemini 2.5 Pro",         callback_data="modelo_25"),
                InlineKeyboardButton("🟢 Gemini 3.1 Pro Preview", callback_data="modelo_31"),
            ]
        ])
        await query.message.reply_text(
            "🤖 *¿Qué modelo de IA quieres usar?*\n\n"
            "• *Gemini 2.5 Pro*: modelo estable y probado.\n"
            "• *Gemini 3.1 Pro Preview*: modelo avanzado, más potente.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    elif data in ("modelo_25", "modelo_31"):
        if _estado(context) != SELECCIONANDO_MODELO:
            return
        context.user_data["modelo"] = "gemini-2.5-pro" if data == "modelo_25" else "gemini-3.1-pro-preview"
        _set_estado(context, ESPERANDO_ARCHIVO)
        await query.message.reply_text("📎 Envíame el contrato en PDF o DOCX:")

    elif data == "ver_status":
        uso = get_uso_hoy(user_id, rol)
        limite_aud = uso["auditorias_limite"] if uso["auditorias_limite"] < 999 else "∞"
        limite_preg = uso["preguntas_limite"] if uso["preguntas_limite"] < 999 else "∞"
        await query.message.reply_text(
            f"📊 *Uso de hoy* — Nivel: {rol.capitalize()}\n"
            f"• Auditorías: {uso['auditorias']}/{limite_aud}\n"
            f"• Preguntas:  {uso['preguntas']}/{limite_preg}",
            parse_mode="Markdown",
        )

    elif data == "admin_menu" and rol == "admin":
        await _mostrar_panel_admin_callback(query)

    elif data == "admin_listar" and rol == "admin":
        usuarios = listar_usuarios()
        if not usuarios:
            await query.message.reply_text("No hay usuarios registrados.")
            return
        lineas = ["*Usuarios registrados:*\n"]
        for u in usuarios:
            estado = "✅" if u["activo"] else "🔴"
            lineas.append(f"{estado} `{u['id']}` {u['email']} ({u['rol']})")
        texto = "\n".join(lineas)
        # Telegram limita mensajes a 4096 chars; truncar si hay muchos usuarios
        if len(texto) > 4000:
            texto = texto[:4000] + "\n…(lista truncada)"
        await query.message.reply_text(texto, parse_mode="Markdown")

    elif data == "admin_cambiar_rol" and rol == "admin":
        _set_estado(context, ADMIN_ROL_ID)
        await query.message.reply_text(
            "Ingresa el *Telegram ID* del usuario cuyo rol quieres cambiar:",
            parse_mode="Markdown",
        )

    elif data.startswith("admin_rol_") and rol == "admin":
        # Formato: admin_rol_{nuevo_rol}_{telegram_id}
        partes = data.split("_")
        nuevo_rol = partes[2]
        target_id = int(partes[3])
        cambiar_rol(target_id, nuevo_rol)
        await query.message.reply_text(
            f"✅ Rol actualizado a *{nuevo_rol.capitalize()}* para el usuario `{target_id}`.",
            parse_mode="Markdown",
        )
        _set_estado(context, MENU)

    elif data.startswith("admin_suspender_") and rol == "admin":
        target_id = int(data.split("_")[2])
        suspender_usuario(target_id)
        await query.message.reply_text(f"🔴 Usuario `{target_id}` suspendido.", parse_mode="Markdown")

    elif data.startswith("admin_activar_") and rol == "admin":
        target_id = int(data.split("_")[2])
        activar_usuario(target_id)
        await query.message.reply_text(f"✅ Usuario `{target_id}` activado.", parse_mode="Markdown")

    elif data.startswith("aprobar_") and rol == "admin":
        partes = data.split("_")
        accion = partes[1]          # basico | auditor | admin | rechazar
        target_id = int(partes[2])
        usuario_target = get_usuario(target_id)
        if not usuario_target:
            await query.message.reply_text("Usuario no encontrado.")
            return

        if accion == "rechazar":
            suspender_usuario(target_id)
            await query.message.edit_text(
                f"🚫 Solicitud de `{usuario_target['email']}` rechazada. Cuenta suspendida.",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        "❌ Tu solicitud de acceso a *ContractIA* fue rechazada.\n"
                        "Contacta al administrador si crees que es un error."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        else:
            nuevo_rol = accion  # basico | auditor | admin
            cambiar_rol(target_id, nuevo_rol)
            await query.message.edit_text(
                f"✅ *{usuario_target['email']}* aprobado con rol *{nuevo_rol.capitalize()}*.",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"✅ *¡Tu cuenta fue aprobada!*\n\n"
                        f"Nivel asignado: *{nuevo_rol.capitalize()}*\n\n"
                        f"Usa /login para ingresar con la contraseña que recibiste por email."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass


# ── FLUJOS DE REGISTRO ────────────────────────────────────────────────────────

async def _handle_registro_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    email = update.message.text.strip().lower()
    user_id = update.effective_user.id

    if "@" not in email or "." not in email.split("@")[-1]:
        await update.message.reply_text("Email inválido. Inténtalo de nuevo:")
        return

    if existe_email(email):
        await update.message.reply_text(
            "Ese email ya está registrado. Usa /login para iniciar sesión."
        )
        return

    codigo = generar_codigo_verificacion()
    expira = datetime.now().timestamp() + 600  # 10 minutos

    with get_conn() as conn:
        conn.execute("DELETE FROM codigos_verificacion WHERE telegram_id=%s", (user_id,))
        conn.execute(
            "INSERT INTO codigos_verificacion (telegram_id, codigo, expira_en) VALUES (%s, %s, %s)",
            (user_id, codigo, expira),
        )

    try:
        asunto, html, texto = email_verificacion(codigo)
        enviar_email(email, asunto, html, texto)
        context.user_data["registro_email"] = email
        _set_estado(context, REGISTRO_CODIGO)
        await update.message.reply_text(
            f"✅ Código enviado a *{email}*\nIngresa el código de 6 dígitos:",
            parse_mode="Markdown",
        )
    except Exception:
        await update.message.reply_text(
            "❌ No pude enviar el email. Verifica la dirección e inténtalo de nuevo:"
        )


async def _handle_registro_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    codigo_ingresado = update.message.text.strip()
    user_id = update.effective_user.id
    email = context.user_data.get("registro_email")

    if not email:
        _set_estado(context, REGISTRO_EMAIL)
        await update.message.reply_text("Sesión perdida. Ingresa tu email de nuevo:")
        return

    with get_conn() as conn:
        row = conn.execute(
            "SELECT codigo, expira_en FROM codigos_verificacion "
            "WHERE telegram_id=%s AND usado=0 ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    if not row:
        await update.message.reply_text("No hay código pendiente. Usa /start para comenzar de nuevo.")
        return

    if datetime.now().timestamp() > float(row["expira_en"]):
        await update.message.reply_text("El código expiró. Usa /start para solicitar uno nuevo.")
        _set_estado(context, INICIO)
        return

    if row["codigo"] != codigo_ingresado:
        await update.message.reply_text("Código incorrecto. Intenta de nuevo:")
        return

    with get_conn() as conn:
        conn.execute("UPDATE codigos_verificacion SET usado=1 WHERE telegram_id=%s", (user_id,))

    password = generar_password()
    es_admin = user_id == TELEGRAM_ADMIN_ID
    rol = "admin" if es_admin else "pendiente"
    crear_usuario(user_id, email, password, rol)

    try:
        asunto, html, texto = email_bienvenida(email, password, rol)
        enviar_email(email, asunto, html, texto)
    except Exception:
        pass  # La cuenta se crea igual aunque falle el email de bienvenida

    context.user_data.pop("registro_email", None)

    if es_admin:
        login_session(user_id)
        _set_estado(context, MENU)
        await update.message.reply_text(
            f"✅ *¡Cuenta de administrador creada!*\n\n"
            f"Tu contraseña fue enviada a *{email}*.",
            parse_mode="Markdown",
        )
        await _mostrar_menu(update, context)
    else:
        _set_estado(context, INICIO)
        await update.message.reply_text(
            f"✅ *¡Registro recibido!*\n\n"
            f"Tu solicitud está *pendiente de aprobación*.\n"
            f"Recibirás una notificación aquí mismo cuando el administrador active tu cuenta.\n\n"
            f"_Tu contraseña provisional fue enviada a {email} y estará lista cuando te aprueben._",
            parse_mode="Markdown",
        )
        await _notificar_admin_nuevo_usuario(context, user_id, email)


# ── FLUJO DE LOGIN ────────────────────────────────────────────────────────────

async def _handle_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    password = update.message.text.strip()
    user_id = update.effective_user.id

    # Borrar el mensaje con la contraseña por seguridad
    try:
        await update.message.delete()
    except Exception:
        pass

    if verificar_password(user_id, password):
        usuario = get_usuario(user_id)
        if usuario and usuario["rol"] == "pendiente":
            _set_estado(context, INICIO)
            await update.effective_chat.send_message(
                "⏳ Tu cuenta está *pendiente de aprobación*.\n"
                "Recibirás una notificación aquí cuando el administrador active tu acceso.",
                parse_mode="Markdown",
            )
            return
        login_session(user_id)
        _set_estado(context, MENU)
        await update.effective_chat.send_message("✅ Sesión iniciada correctamente.")
        await _mostrar_menu_chat(update, context)
    else:
        await update.effective_chat.send_message(
            "❌ Contraseña incorrecta. Intenta de nuevo o usa /start."
        )


# ── FLUJO DE PREGUNTAS ────────────────────────────────────────────────────────

async def _handle_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    usuario = get_usuario(user_id)

    if not puede_preguntar(user_id, usuario["rol"]):
        limite = LIMITES[usuario["rol"]]["preguntas"]
        await update.message.reply_text(
            f"Alcanzaste el límite diario de preguntas ({limite}/{limite}). Vuelve mañana."
        )
        return

    if not get_retriever(user_id):
        await update.message.reply_text("No hay contrato cargado. Usa /menu para subir uno.")
        _set_estado(context, MENU)
        return

    await responder_pregunta(update, context)


# ── FLUJO ADMIN ───────────────────────────────────────────────────────────────

async def _handle_admin_rol_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("ID inválido. Ingresa un número entero:")
        return

    usuario_target = get_usuario(target_id)
    if not usuario_target:
        await update.message.reply_text("Usuario no encontrado. Ingresa otro ID o usa /cancel:")
        return

    context.user_data["admin_target_id"] = target_id
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Básico",  callback_data=f"admin_rol_basico_{target_id}"),
            InlineKeyboardButton("🔍 Auditor", callback_data=f"admin_rol_auditor_{target_id}"),
            InlineKeyboardButton("⚙️ Admin",   callback_data=f"admin_rol_admin_{target_id}"),
        ],
        [
            InlineKeyboardButton("🔴 Suspender", callback_data=f"admin_suspender_{target_id}"),
            InlineKeyboardButton("✅ Activar",   callback_data=f"admin_activar_{target_id}"),
        ],
    ])
    await update.message.reply_text(
        f"Usuario: *{usuario_target['email']}*\n"
        f"Rol actual: *{usuario_target['rol']}*\n"
        f"Estado: {'Activo' if usuario_target['activo'] else 'Suspendido'}\n\n"
        "Selecciona la acción:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    _set_estado(context, MENU)


# ── NOTIFICACIÓN ADMIN ────────────────────────────────────────────────────────

async def _notificar_admin_nuevo_usuario(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, email: str
) -> None:
    """Envía al admin un mensaje con botones para aprobar/rechazar al nuevo usuario."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Básico",   callback_data=f"aprobar_basico_{user_id}"),
            InlineKeyboardButton("🔍 Auditor",  callback_data=f"aprobar_auditor_{user_id}"),
            InlineKeyboardButton("⚙️ Admin",    callback_data=f"aprobar_admin_{user_id}"),
        ],
        [
            InlineKeyboardButton("🚫 Rechazar", callback_data=f"aprobar_rechazar_{user_id}"),
        ],
    ])
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_ADMIN_ID,
            text=(
                f"🔔 *Nuevo usuario solicitando acceso*\n\n"
                f"• Email: `{email}`\n"
                f"• Telegram ID: `{user_id}`\n\n"
                f"¿Qué rol le asignas?"
            ),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        pass  # Si el admin no tiene chat abierto con el bot, falla silenciosamente


# ── MENÚ PRINCIPAL ────────────────────────────────────────────────────────────

async def _mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    usuario = get_usuario(user_id)
    nombre = update.effective_user.first_name
    rol = usuario["rol"] if usuario else "basico"

    botones = [
        [InlineKeyboardButton("💬 Hacer preguntas al contrato", callback_data="modo_preguntas")],
        [InlineKeyboardButton("📊 Ver mi estado", callback_data="ver_status")],
    ]
    if rol in ("auditor", "admin"):
        botones.insert(1, [InlineKeyboardButton("🔍 Auditoría completa", callback_data="modo_auditoria")])
    if rol == "admin":
        botones.append([InlineKeyboardButton("⚙️ Panel de administración", callback_data="admin_menu")])

    keyboard = InlineKeyboardMarkup(botones)
    _set_estado(context, MENU)

    await update.message.reply_text(
        f"Hola, *{nombre}*. ¿Qué quieres hacer?\n_Nivel: {rol.capitalize()}_",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _mostrar_menu_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Versión del menú que usa effective_chat (para después de borrar mensaje de login)."""
    user_id = update.effective_user.id
    usuario = get_usuario(user_id)
    nombre = update.effective_user.first_name
    rol = usuario["rol"] if usuario else "basico"

    botones = [
        [InlineKeyboardButton("💬 Hacer preguntas al contrato", callback_data="modo_preguntas")],
        [InlineKeyboardButton("📊 Ver mi estado", callback_data="ver_status")],
    ]
    if rol in ("auditor", "admin"):
        botones.insert(1, [InlineKeyboardButton("🔍 Auditoría completa", callback_data="modo_auditoria")])
    if rol == "admin":
        botones.append([InlineKeyboardButton("⚙️ Panel de administración", callback_data="admin_menu")])

    keyboard = InlineKeyboardMarkup(botones)
    _set_estado(context, MENU)

    await update.effective_chat.send_message(
        f"Hola, *{nombre}*. ¿Qué quieres hacer?\n_Nivel: {rol.capitalize()}_",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _mostrar_panel_admin(update: Update) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Listar usuarios",  callback_data="admin_listar")],
        [InlineKeyboardButton("🔄 Cambiar rol / Estado", callback_data="admin_cambiar_rol")],
    ])
    await update.message.reply_text(
        "⚙️ *Panel de Administración*", reply_markup=keyboard, parse_mode="Markdown"
    )


async def _mostrar_panel_admin_callback(query) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Listar usuarios",  callback_data="admin_listar")],
        [InlineKeyboardButton("🔄 Cambiar rol / Estado", callback_data="admin_cambiar_rol")],
    ])
    await query.message.reply_text(
        "⚙️ *Panel de Administración*", reply_markup=keyboard, parse_mode="Markdown"
    )


# ── HELPER DE AUTENTICACIÓN ───────────────────────────────────────────────────

async def _check_auth(update: Update) -> bool:
    """Verifica sesión activa. Envía mensaje y retorna False si no está autenticado."""
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        if existe_telegram_id(user_id):
            usuario = get_usuario(user_id)
            if usuario and usuario["rol"] == "pendiente":
                await update.message.reply_text(
                    "⏳ Tu cuenta está *pendiente de aprobación*.\n"
                    "Recibirás una notificación cuando el administrador active tu acceso.",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text("Sesión expirada. Usa /login para volver a entrar.")
        else:
            await update.message.reply_text("No tienes cuenta. Usa /start para registrarte.")
        return False
    return True
