"""Conexión PostgreSQL y creación de tablas para el bot de Telegram.

El wrapper _PGConn mantiene la misma interfaz que sqlite3 para minimizar
cambios en el resto del código (solo se necesita ? → %s en los queries).
"""

import os

import psycopg2
import psycopg2.extras

DATABASE_URL: str = os.getenv("DATABASE_URL", "")


class _PGConn:
    """Wrapper que hace que psycopg2 se comporte como sqlite3.Connection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


def get_conn() -> _PGConn:
    conn = psycopg2.connect(DATABASE_URL)
    return _PGConn(conn)


def init_db() -> None:
    """Crea las tablas si no existen. Llamar al iniciar el bot y la API."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                telegram_id   BIGINT PRIMARY KEY,
                email         TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                rol           TEXT    NOT NULL DEFAULT 'basico',
                activo        INTEGER NOT NULL DEFAULT 1,
                fecha_registro TEXT   NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS codigos_verificacion (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                codigo      TEXT    NOT NULL,
                expira_en   DOUBLE PRECISION NOT NULL,
                usado       INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uso_diario (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                fecha       TEXT    NOT NULL,
                auditorias  INTEGER NOT NULL DEFAULT 0,
                preguntas   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(telegram_id, fecha)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                accion      TEXT,
                detalle     TEXT,
                timestamp   TEXT
            )
        """)
