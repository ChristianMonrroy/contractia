"""Conexión SQLite y creación de tablas para el bot de Telegram."""

import sqlite3
from pathlib import Path

from contractia.config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "contractia.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Crea las tablas si no existen. Llamar al iniciar el bot."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
                telegram_id   INTEGER PRIMARY KEY,
                email         TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                rol           TEXT    NOT NULL DEFAULT 'basico',
                activo        INTEGER NOT NULL DEFAULT 1,
                fecha_registro TEXT   NOT NULL
            );

            CREATE TABLE IF NOT EXISTS codigos_verificacion (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                codigo      TEXT    NOT NULL,
                expira_en   REAL    NOT NULL,
                usado       INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS uso_diario (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                fecha       TEXT    NOT NULL,
                auditorias  INTEGER NOT NULL DEFAULT 0,
                preguntas   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(telegram_id, fecha)
            );

            CREATE TABLE IF NOT EXISTS logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                accion      TEXT,
                detalle     TEXT,
                timestamp   TEXT
            );
        """)
