"""Conexión PostgreSQL y creación de tablas para el bot de Telegram.

El wrapper _PGConn mantiene la misma interfaz que sqlite3 para minimizar
cambios en el resto del código (solo se necesita ? → %s en los queries).
"""

import os
from typing import Optional

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
                id                SERIAL PRIMARY KEY,
                telegram_id       BIGINT,
                accion            TEXT,
                detalle           TEXT,
                timestamp         TEXT,
                duracion_segundos FLOAT,
                canal             TEXT DEFAULT 'bot',
                n_hallazgos       INTEGER
            )
        """)
        # Migraciones idempotentes para instancias ya existentes
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS duracion_segundos FLOAT")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS canal TEXT DEFAULT 'bot'")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS n_hallazgos INTEGER")


def get_actividad(
    telegram_id: Optional[int] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    accion: Optional[str] = None,
    limit: int = 200,
) -> list:
    """
    Retorna logs de actividad filtrados, con email del usuario (JOIN usuarios).

    Args:
        telegram_id: Filtrar por usuario específico.
        fecha_inicio: Fecha mínima en formato 'YYYY-MM-DD'.
        fecha_fin:    Fecha máxima en formato 'YYYY-MM-DD'.
        accion:       'auditoria' o 'pregunta'.
        limit:        Máximo de filas a devolver.
    """
    conditions = []
    params = []

    if telegram_id is not None:
        conditions.append("l.telegram_id = %s")
        params.append(telegram_id)
    if fecha_inicio:
        conditions.append("l.timestamp >= %s")
        params.append(fecha_inicio)
    if fecha_fin:
        conditions.append("l.timestamp <= %s")
        params.append(fecha_fin + "T23:59:59")
    if accion:
        conditions.append("l.accion = %s")
        params.append(accion)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT
            l.id,
            l.telegram_id,
            u.email,
            u.rol,
            l.accion,
            l.canal,
            l.detalle,
            l.duracion_segundos,
            l.n_hallazgos,
            l.timestamp
        FROM logs l
        LEFT JOIN usuarios u ON l.telegram_id = u.telegram_id
        {where}
        ORDER BY l.timestamp DESC
        LIMIT %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_resumen_actividad() -> dict:
    """
    Agrega métricas globales de actividad:
    - Totales por tipo de acción
    - Duraciones promedio
    - Top 5 usuarios más activos
    """
    with get_conn() as conn:
        # Totales y promedios por acción
        rows_totales = conn.execute("""
            SELECT
                accion,
                COUNT(*) AS total,
                ROUND(AVG(duracion_segundos)::numeric, 1) AS duracion_promedio
            FROM logs
            WHERE accion IN ('auditoria', 'pregunta')
            GROUP BY accion
        """).fetchall()

        # Top 5 usuarios más activos
        rows_top = conn.execute("""
            SELECT
                u.email,
                COUNT(*) AS total
            FROM logs l
            JOIN usuarios u ON l.telegram_id = u.telegram_id
            WHERE l.accion IN ('auditoria', 'pregunta')
            GROUP BY u.email
            ORDER BY total DESC
            LIMIT 5
        """).fetchall()

    resumen = {
        "total_auditorias": 0,
        "total_preguntas": 0,
        "duracion_promedio_auditoria": None,
        "duracion_promedio_pregunta": None,
        "top_usuarios": [dict(r) for r in rows_top],
    }
    for row in rows_totales:
        r = dict(row)
        if r["accion"] == "auditoria":
            resumen["total_auditorias"] = r["total"]
            resumen["duracion_promedio_auditoria"] = float(r["duracion_promedio"] or 0)
        elif r["accion"] == "pregunta":
            resumen["total_preguntas"] = r["total"]
            resumen["duracion_promedio_pregunta"] = float(r["duracion_promedio"] or 0)

    return resumen
