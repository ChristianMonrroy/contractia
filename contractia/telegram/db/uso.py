"""Rate limiting diario por usuario y rol."""

from datetime import date

from .database import get_conn

# Límites por rol: {rol: {accion: max_por_dia}}
LIMITES: dict = {
    "basico":  {"auditorias": 0,   "preguntas": 10},
    "auditor": {"auditorias": 3,   "preguntas": 30},
    "admin":   {"auditorias": 999, "preguntas": 999},
}


def _hoy() -> str:
    return date.today().isoformat()


def _get_uso(telegram_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT auditorias, preguntas FROM uso_diario WHERE telegram_id=? AND fecha=?",
            (telegram_id, _hoy()),
        ).fetchone()
    return dict(row) if row else {"auditorias": 0, "preguntas": 0}


def puede_auditar(telegram_id: int, rol: str) -> bool:
    limite = LIMITES.get(rol, {}).get("auditorias", 0)
    if limite == 0:
        return False
    return _get_uso(telegram_id)["auditorias"] < limite


def puede_preguntar(telegram_id: int, rol: str) -> bool:
    limite = LIMITES.get(rol, {}).get("preguntas", 0)
    return _get_uso(telegram_id)["preguntas"] < limite


def registrar_auditoria(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO uso_diario (telegram_id, fecha, auditorias, preguntas) VALUES (?, ?, 1, 0) "
            "ON CONFLICT(telegram_id, fecha) DO UPDATE SET auditorias = auditorias + 1",
            (telegram_id, _hoy()),
        )


def registrar_pregunta(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO uso_diario (telegram_id, fecha, auditorias, preguntas) VALUES (?, ?, 0, 1) "
            "ON CONFLICT(telegram_id, fecha) DO UPDATE SET preguntas = preguntas + 1",
            (telegram_id, _hoy()),
        )


def get_uso_hoy(telegram_id: int, rol: str) -> dict:
    uso = _get_uso(telegram_id)
    limites = LIMITES.get(rol, {"auditorias": 0, "preguntas": 0})
    return {
        "auditorias":        uso["auditorias"],
        "auditorias_limite": limites["auditorias"],
        "preguntas":         uso["preguntas"],
        "preguntas_limite":  limites["preguntas"],
    }
