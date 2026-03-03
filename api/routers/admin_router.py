"""Endpoints de administración."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_admin
from contractia.telegram.db.database import get_actividad, get_resumen_actividad
from contractia.telegram.db.usuarios import (
    activar_usuario,
    cambiar_rol,
    listar_usuarios,
    suspender_usuario,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class RolRequest(BaseModel):
    telegram_id: int
    rol: str  # basico | auditor | admin


@router.get("/usuarios")
def list_users(admin: dict = Depends(require_admin)):
    """Lista todos los usuarios registrados."""
    rows = listar_usuarios()
    return [dict(r) for r in rows]


@router.patch("/usuarios/rol")
def update_rol(body: RolRequest, admin: dict = Depends(require_admin)):
    """Cambia el rol de un usuario."""
    roles_validos = ("pendiente", "basico", "auditor", "admin")
    if body.rol not in roles_validos:
        raise HTTPException(400, f"Rol inválido. Usa: {roles_validos}")
    cambiar_rol(body.telegram_id, body.rol)
    return {"detail": f"Rol actualizado a {body.rol}"}


@router.patch("/usuarios/{telegram_id}/suspender")
def suspend_user(telegram_id: int, admin: dict = Depends(require_admin)):
    suspender_usuario(telegram_id)
    return {"detail": "Usuario suspendido"}


@router.patch("/usuarios/{telegram_id}/activar")
def activate_user(telegram_id: int, admin: dict = Depends(require_admin)):
    activar_usuario(telegram_id)
    return {"detail": "Usuario activado"}


@router.get("/actividad/resumen")
def get_resumen(admin: dict = Depends(require_admin)):
    """Métricas agregadas: totales, duraciones promedio y top usuarios."""
    return get_resumen_actividad()


@router.get("/actividad")
def get_actividad_logs(
    telegram_id: Optional[int] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    accion: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """Lista el historial de actividad con filtros opcionales."""
    return get_actividad(
        telegram_id=telegram_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        accion=accion,
    )
