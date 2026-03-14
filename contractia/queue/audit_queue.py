"""
Cola global de auditorías.

Expone:
  - AuditJob: datos de un trabajo de auditoría.
  - _audit_queue: asyncio.Queue global compartida por toda la app.
  - enqueue_audit(job): encola un trabajo.
  - get_audit_queue(): accede a la cola.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class AuditJob:
    audit_id: str
    user_id: int
    filename: str
    email: str
    graph_enabled: bool
    is_admin: bool
    modelo: str
    gcs_uri: Optional[str] = None        # Ruta GCS del archivo (si AUDIT_QUEUE_BUCKET está configurado)
    local_tmp_dir: Optional[str] = None  # Ruta /tmp local (fallback sin GCS)


_audit_queue: asyncio.Queue = asyncio.Queue()


async def enqueue_audit(job: AuditJob) -> None:
    """Agrega un trabajo a la cola de auditorías."""
    await _audit_queue.put(job)


def get_audit_queue() -> asyncio.Queue:
    """Retorna la cola global de auditorías."""
    return _audit_queue
