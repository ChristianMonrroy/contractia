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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auditorias (
                audit_id     TEXT PRIMARY KEY,
                user_id      BIGINT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'processing',
                informe      TEXT,
                n_hallazgos  INTEGER,
                n_secciones  INTEGER,
                error_detail TEXT,
                progress_msg TEXT,
                filename     TEXT,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                updated_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Migraciones idempotentes para instancias ya existentes
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS duracion_segundos FLOAT")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS canal TEXT DEFAULT 'bot'")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS n_hallazgos INTEGER")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS tipo_rag TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS progress_msg TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS filename TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS progress_pct INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS graph_enabled BOOLEAN DEFAULT FALSE")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS texto_contrato TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS technical_report_url TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS metadata_tecnica TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS graph_data TEXT")
        conn.execute("ALTER TABLE auditorias ADD COLUMN IF NOT EXISTS modelo_usado TEXT DEFAULT 'gemini-2.5-pro'")
        conn.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS modelo_usado TEXT")


def get_texto_auditoria(audit_id: str) -> Optional[str]:
    """Devuelve el texto extraído de un contrato auditado, o None si no está disponible."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT texto_contrato FROM auditorias WHERE audit_id = %s",
            (audit_id,),
        ).fetchone()
    return row["texto_contrato"] if row else None


def hay_auditoria_en_progreso(max_minutos: int = 20) -> bool:
    """True si hay una auditoría con status='processing' iniciada en los últimos max_minutos."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM auditorias "
            "WHERE status = 'processing' "
            "AND created_at > NOW() - INTERVAL '%s minutes'",
            (max_minutos,),
        ).fetchone()
    return (row["cnt"] if row else 0) > 0


def get_auditoria_en_progreso(max_minutos: int = 20) -> Optional[dict]:
    """Devuelve los detalles de la auditoría en curso (si existe), incluyendo email del usuario."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT a.audit_id, a.user_id, a.filename, a.graph_enabled, "
            "a.progress_msg, a.progress_pct, a.created_at, u.email "
            "FROM auditorias a "
            "LEFT JOIN usuarios u ON u.telegram_id = a.user_id "
            "WHERE a.status = 'processing' "
            "AND a.created_at > NOW() - INTERVAL '%s minutes' "
            "ORDER BY a.created_at DESC LIMIT 1",
            (max_minutos,),
        ).fetchone()
    return dict(row) if row else None


def crear_auditoria(audit_id: str, user_id: int, filename: str = "", graph_enabled: bool = False) -> None:
    """Registra una nueva auditoría con estado 'processing'."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO auditorias (audit_id, user_id, status, filename, progress_msg, progress_pct, graph_enabled) "
            "VALUES (%s, %s, 'processing', %s, 'Iniciando...', 0, %s)",
            (audit_id, user_id, filename, graph_enabled),
        )


def get_auditoria(audit_id: str) -> Optional[dict]:
    """Devuelve el estado y resultado de una auditoría por su ID."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, informe, n_hallazgos, n_secciones, "
            "error_detail, progress_msg, progress_pct, filename, graph_enabled, "
            "technical_report_url, metadata_tecnica, graph_data, modelo_usado "
            "FROM auditorias WHERE audit_id = %s",
            (audit_id,),
        ).fetchone()
    return dict(row) if row else None


def get_auditorias_usuario(user_id: int, limit: int = 20) -> list:
    """Devuelve el historial de auditorías de un usuario, más recientes primero."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT audit_id, status, filename, n_hallazgos, n_secciones, "
            "progress_msg, progress_pct, error_detail, graph_enabled, "
            "technical_report_url, metadata_tecnica, modelo_usado, created_at, updated_at "
            "FROM auditorias WHERE user_id = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def actualizar_auditoria(audit_id: str, **kwargs) -> None:
    """Actualiza campos de una auditoría (status, informe, n_hallazgos, etc.)."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [audit_id]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE auditorias SET {set_clause}, updated_at = NOW() WHERE audit_id = %s",
            values,
        )


def get_todas_auditorias(limit: int = 100) -> list:
    """Devuelve todas las auditorías de todos los usuarios, más recientes primero."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT a.audit_id, a.status, a.filename, a.n_hallazgos, a.n_secciones, "
            "a.progress_msg, a.progress_pct, a.error_detail, a.graph_enabled, "
            "a.modelo_usado, a.created_at, a.updated_at, "
            "u.email, u.rol "
            "FROM auditorias a "
            "LEFT JOIN usuarios u ON u.telegram_id = a.user_id "
            "ORDER BY a.created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


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
            l.tipo_rag,
            l.modelo_usado,
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
