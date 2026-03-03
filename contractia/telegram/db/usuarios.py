"""CRUD de usuarios con bcrypt para contraseñas."""

import sqlite3
from datetime import datetime
from typing import Optional

import bcrypt

from .database import get_conn


# ── Escritura ─────────────────────────────────────────────────────────────────

def crear_usuario(telegram_id: int, email: str, password: str, rol: str = "basico") -> bool:
    hash_ = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO usuarios (telegram_id, email, password_hash, rol, fecha_registro) "
                "VALUES (%s, %s, %s, %s, %s)",
                (telegram_id, email, hash_, rol, datetime.now().isoformat()),
            )
        return True
    except Exception:
        return False


def actualizar_password(email: str, nueva_password: str) -> bool:
    hash_ = bcrypt.hashpw(nueva_password.encode(), bcrypt.gensalt()).decode()
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET password_hash=%s WHERE email=%s",
            (hash_, email),
        )
    return True


def cambiar_rol(telegram_id: int, nuevo_rol: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE usuarios SET rol=%s WHERE telegram_id=%s", (nuevo_rol, telegram_id))


def suspender_usuario(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE usuarios SET activo=0 WHERE telegram_id=%s", (telegram_id,))


def activar_usuario(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE usuarios SET activo=1 WHERE telegram_id=%s", (telegram_id,))


# ── Lectura ───────────────────────────────────────────────────────────────────

def get_usuario(telegram_id: int) -> Optional[sqlite3.Row]:
    import sqlite3
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM usuarios WHERE telegram_id=%s", (telegram_id,)
        ).fetchone()


def existe_telegram_id(telegram_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM usuarios WHERE telegram_id=%s", (telegram_id,)
        ).fetchone() is not None


def existe_email(email: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM usuarios WHERE email=%s", (email,)
        ).fetchone() is not None


def listar_usuarios() -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT telegram_id AS id, email, rol, activo, "
            "fecha_registro AS creado_en "
            "FROM usuarios ORDER BY fecha_registro DESC"
        ).fetchall()


# ── Autenticación ─────────────────────────────────────────────────────────────

def verificar_password(telegram_id: int, password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM usuarios WHERE telegram_id=%s AND activo=1",
            (telegram_id,),
        ).fetchone()
    if not row:
        return False
    return bcrypt.checkpw(password.encode(), row["password_hash"].encode())
