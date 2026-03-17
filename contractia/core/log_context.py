"""Contexto de logging para auditorías.

Proporciona una función log() que:
  1. Siempre escribe en stdout (visible en Cloud Run logs).
  2. Si hay un callback registrado vía ContextVar, también lo invoca.

El ContextVar se propaga automáticamente a los threads creados por
asyncio.run_in_executor, por lo que un callback registrado en el event
loop principal es visible en todos los hilos de una auditoría.
"""

import contextvars
from typing import Callable, Optional

_audit_log_cb: contextvars.ContextVar[Optional[Callable[[str], None]]] = (
    contextvars.ContextVar("audit_log_cb", default=None)
)


def set_log_callback(cb: Optional[Callable[[str], None]]) -> None:
    """Registra el callback de logging para la auditoría actual."""
    _audit_log_cb.set(cb)


def log(msg: str) -> None:
    """Emite un mensaje de diagnóstico.

    Siempre imprime en stdout (Cloud Run logs).
    Si hay un callback registrado, también lo invoca sin propagar excepciones.
    """
    print(msg, flush=True)
    cb = _audit_log_cb.get()
    if cb is not None:
        try:
            cb(msg)
        except Exception:
            pass
