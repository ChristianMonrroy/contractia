"""
Estado de sesión en memoria por usuario.

Guarda:
  - autenticación y timestamp de login
  - vector store y retriever del contrato activo del usuario
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from contractia.config import SESSION_TIMEOUT_HOURS

# {telegram_id: {campo: valor}}
_sessions: dict[int, dict] = {}


# ── Autenticación ─────────────────────────────────────────────────────────────

def login_session(user_id: int) -> None:
    _upsert(user_id, {"autenticado": True, "login_time": datetime.now()})


def logout_session(user_id: int) -> None:
    _sessions.pop(user_id, None)


def is_authenticated(user_id: int) -> bool:
    session = _sessions.get(user_id, {})
    if not session.get("autenticado"):
        return False
    login_time: Optional[datetime] = session.get("login_time")
    if login_time and datetime.now() - login_time > timedelta(hours=SESSION_TIMEOUT_HOURS):
        logout_session(user_id)
        return False
    return True


# ── Contrato / RAG ────────────────────────────────────────────────────────────

def set_vector_store(user_id: int, vector_store: Any, retriever: Any) -> None:
    _upsert(user_id, {"vector_store": vector_store, "retriever": retriever})


def get_retriever(user_id: int) -> Optional[Any]:
    return _sessions.get(user_id, {}).get("retriever")


def clear_contract(user_id: int) -> None:
    session = _sessions.get(user_id, {})
    session.pop("vector_store", None)
    session.pop("retriever", None)


# ── Internos ──────────────────────────────────────────────────────────────────

def _upsert(user_id: int, data: dict) -> None:
    if user_id not in _sessions:
        _sessions[user_id] = {}
    _sessions[user_id].update(data)
