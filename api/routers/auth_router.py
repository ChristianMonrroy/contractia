"""Endpoints de autenticación: registro, verificación OTP y login."""

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from api.auth import crear_token
from contractia.telegram.auth.crypto import generar_codigo_verificacion, generar_password
from contractia.telegram.correo.sender import enviar_email
from contractia.telegram.correo.templates import email_bienvenida, email_verificacion
from contractia.telegram.db.database import get_conn
from contractia.telegram.db.usuarios import (
    actualizar_password,
    crear_usuario,
    existe_email,
    get_usuario,
    verificar_password,
)
from contractia.config import TELEGRAM_ADMIN_ID, TELEGRAM_TOKEN

router = APIRouter(prefix="/auth", tags=["auth"])


def _notify_admin_nuevo_usuario(email: str) -> None:
    """Envía un mensaje de Telegram al admin cuando se registra un nuevo usuario web."""
    if not TELEGRAM_TOKEN or not TELEGRAM_ADMIN_ID:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_ADMIN_ID,
                "text": (
                    f"🔔 *Nuevo usuario registrado (web)*\n\n"
                    f"📧 Email: `{email}`\n"
                    f"🕐 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"⏳ Rol: pendiente de aprobación\n\n"
                    f"Entra al panel admin para aprobar: https://contractia.pe/admin"
                ),
                "parse_mode": "Markdown",
            },
            timeout=5,
        )
    except Exception:
        pass  # No interrumpir el flujo si falla la notificación


class RegisterRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    codigo: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    codigo: str
    nueva_password: str


@router.post("/register")
def register(body: RegisterRequest):
    """Envía código OTP al email para iniciar el registro."""
    email = body.email.lower()

    if existe_email(email):
        raise HTTPException(400, "Email ya registrado. Usa /auth/login.")

    codigo = generar_codigo_verificacion()
    expira = datetime.now().timestamp() + 600  # 10 minutos

    # Usamos telegram_id=0 para registros web (se asigna al verificar)
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM codigos_verificacion WHERE telegram_id=%s AND usado=0",
            (0,),
        )
        conn.execute(
            "INSERT INTO codigos_verificacion (telegram_id, codigo, expira_en) VALUES (%s, %s, %s)",
            (0, f"{email}:{codigo}", expira),
        )

    asunto, html, texto = email_verificacion(codigo)
    enviar_email(email, asunto, html, texto)
    return {"detail": f"Código enviado a {email}"}


@router.post("/verify")
def verify(body: VerifyRequest):
    """Verifica el OTP y crea la cuenta web."""
    email = body.email.lower()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, codigo, expira_en FROM codigos_verificacion "
            "WHERE usado=0 ORDER BY id DESC LIMIT 1",
        ).fetchone()

    if not row:
        raise HTTPException(400, "No hay código pendiente.")

    if datetime.now().timestamp() > float(row["expira_en"]):
        raise HTTPException(400, "El código expiró. Solicita uno nuevo.")

    stored_email, stored_codigo = row["codigo"].split(":", 1)
    if stored_email != email or stored_codigo != body.codigo:
        raise HTTPException(400, "Código incorrecto.")

    with get_conn() as conn:
        conn.execute("UPDATE codigos_verificacion SET usado=1 WHERE id=%s", (row["id"],))

    # telegram_id web: usamos hash negativo del email para no colisionar
    web_id = -abs(hash(email)) % (10**15)
    password = generar_password()
    rol = "pendiente"
    crear_usuario(web_id, email, password, rol)

    asunto, html, texto = email_bienvenida(email, password, rol)
    try:
        enviar_email(email, asunto, html, texto)
    except Exception:
        pass

    _notify_admin_nuevo_usuario(email)

    return {"detail": "Cuenta creada. Pendiente de aprobación por el administrador."}


@router.post("/login")
def login(body: LoginRequest):
    """Login con email y password. Devuelve JWT."""
    email = body.email.lower()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT telegram_id, password_hash, rol, activo FROM usuarios WHERE email=%s",
            (email,),
        ).fetchone()

    if not row:
        raise HTTPException(401, "Credenciales incorrectas.")

    if not row["activo"]:
        raise HTTPException(403, "Cuenta suspendida.")

    if row["rol"] == "pendiente":
        raise HTTPException(403, "Cuenta pendiente de aprobación.")

    import bcrypt
    if not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(401, "Credenciales incorrectas.")

    token = crear_token(row["telegram_id"], email, row["rol"])
    return {"access_token": token, "token_type": "bearer", "rol": row["rol"]}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    """Envía código OTP al email para resetear la contraseña."""
    email = body.email.lower()

    if not existe_email(email):
        # Respondemos igual para no revelar si el email existe
        return {"detail": f"Si el correo existe, recibirás un código en {email}"}

    codigo = generar_codigo_verificacion()
    expira = datetime.now().timestamp() + 600  # 10 minutos

    with get_conn() as conn:
        conn.execute(
            "DELETE FROM codigos_verificacion WHERE telegram_id=%s AND usado=0",
            (-1,),
        )
        conn.execute(
            "INSERT INTO codigos_verificacion (telegram_id, codigo, expira_en) VALUES (%s, %s, %s)",
            (-1, f"{email}:{codigo}", expira),
        )

    asunto = "Resetea tu contraseña — ContractIA"
    html = f"""
    <h2>Reseteo de contraseña</h2>
    <p>Tu código de verificación es:</p>
    <h1 style="letter-spacing:8px;color:#1e3a5f;">{codigo}</h1>
    <p>Válido por 10 minutos. Si no solicitaste esto, ignora este correo.</p>
    """
    texto = f"Tu código para resetear la contraseña de ContractIA es: {codigo}"
    enviar_email(email, asunto, html, texto)
    return {"detail": f"Si el correo existe, recibirás un código en {email}"}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    """Verifica OTP y actualiza la contraseña."""
    email = body.email.lower()

    if len(body.nueva_password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres.")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, codigo, expira_en FROM codigos_verificacion "
            "WHERE telegram_id=%s AND usado=0 ORDER BY id DESC LIMIT 1",
            (-1,),
        ).fetchone()

    if not row:
        raise HTTPException(400, "No hay código pendiente. Solicita uno nuevo.")

    if datetime.now().timestamp() > float(row["expira_en"]):
        raise HTTPException(400, "El código expiró. Solicita uno nuevo.")

    stored_email, stored_codigo = row["codigo"].split(":", 1)
    if stored_email != email or stored_codigo != body.codigo:
        raise HTTPException(400, "Código incorrecto.")

    with get_conn() as conn:
        conn.execute("UPDATE codigos_verificacion SET usado=1 WHERE id=%s", (row["id"],))

    actualizar_password(email, body.nueva_password)
    return {"detail": "Contraseña actualizada correctamente."}
