"""Endpoints de contratos: subida, auditoría y consultas RAG."""

import asyncio
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel

from api.auth import get_current_user
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.report import render_auditoria_markdown
from contractia.llm.provider import build_llm
from contractia.orchestrator import ejecutar_auditoria_contrato
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto
from contractia.telegram.correo.sender import enviar_email
from contractia.telegram.correo.templates import email_auditoria_lista
from contractia.telegram.db.database import (
    crear_auditoria, get_auditoria, actualizar_auditoria, hay_auditoria_en_progreso,
    get_auditorias_usuario, get_conn,
)
from contractia.telegram.db.uso import puede_auditar, puede_preguntar, registrar_auditoria, registrar_pregunta
from contractia.telegram.db.usuarios import get_usuario

router = APIRouter(prefix="/contracts", tags=["contracts"])

# Semáforo global — igual que en el bot
from contractia.telegram.flows.audit_flow import _auditoria_lock

# Los retrievers siguen en memoria (son temporales por sesión, no necesitan persistencia)
_retrievers: dict = {}


class QueryRequest(BaseModel):
    pregunta: str
    session_id: str


@router.post("/upload")
async def upload_contract(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Sube un contrato y lo indexa para consultas RAG. Devuelve session_id."""
    ext = Path(file.filename or "contrato").suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(400, "Solo se aceptan archivos PDF o DOCX.")

    if file.size and file.size > 20 * 1024 * 1024:
        raise HTTPException(400, "El archivo supera el límite de 20 MB.")

    user_id = int(user["sub"])
    usuario = get_usuario(user_id)
    if not usuario:
        raise HTTPException(403, "Usuario no encontrado.")

    if not puede_preguntar(user_id, usuario["rol"]):
        raise HTTPException(429, "Límite diario de consultas alcanzado.")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_web_{user_id}_"))
    tmp_file = tmp_dir / f"contrato{ext}"
    tmp_file.write_bytes(await file.read())

    try:
        _, texto = await asyncio.get_event_loop().run_in_executor(
            None, lambda: procesar_documentos_carpeta(tmp_dir)
        )
        if not texto:
            raise HTTPException(422, "No se pudo extraer texto del archivo.")

        vector_store = await asyncio.get_event_loop().run_in_executor(
            None, lambda: crear_vector_store(texto)
        )
        retriever = crear_retriever(vector_store)
        session_id = str(uuid.uuid4())
        _retrievers[session_id] = retriever

        return {"session_id": session_id, "filename": file.filename}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/query")
async def query_contract(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
):
    """Responde una pregunta RAG sobre el contrato cargado en session_id."""
    retriever = _retrievers.get(body.session_id)
    if not retriever:
        raise HTTPException(404, "Sesión no encontrada. Sube el contrato primero.")

    user_id = int(user["sub"])
    usuario = get_usuario(user_id)
    if not puede_preguntar(user_id, usuario["rol"]):
        raise HTTPException(429, "Límite diario de consultas alcanzado.")

    _PROMPT = (
        "Eres un asistente legal especializado en contratos. "
        "Responde basándote ÚNICAMENTE en el contexto del contrato.\n\n"
        "CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}\n\nRESPUESTA:"
    )

    contexto = await asyncio.get_event_loop().run_in_executor(
        None, lambda: recuperar_contexto(retriever, body.pregunta, max_tokens=3000)
    )
    if not contexto:
        return {"respuesta": "No encontré información relevante sobre eso en el contrato."}

    llm = await asyncio.get_event_loop().run_in_executor(None, build_llm)
    prompt = _PROMPT.format(contexto=contexto, pregunta=body.pregunta)
    start = time.time()
    respuesta = await asyncio.get_event_loop().run_in_executor(None, lambda: llm.invoke(prompt))
    duracion = round(time.time() - start, 1)
    texto = respuesta.content if hasattr(respuesta, "content") else str(respuesta)

    registrar_pregunta(user_id)
    _log_web(user_id, "pregunta", body.pregunta[:200], duracion=duracion)
    return {"respuesta": texto}


@router.post("/audit")
async def start_audit(
    file: UploadFile = File(...),
    graph_enabled: bool = Form(False),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: dict = Depends(get_current_user),
):
    """Lanza una auditoría completa en background. Devuelve audit_id."""
    user_id = int(user["sub"])
    usuario = get_usuario(user_id)
    if not usuario:
        raise HTTPException(403, "Usuario no encontrado.")

    if usuario["rol"] not in ("auditor", "admin"):
        raise HTTPException(403, "Tu nivel no incluye auditorías completas.")

    if not puede_auditar(user_id, usuario["rol"]):
        raise HTTPException(429, "Límite diario de auditorías alcanzado.")

    if hay_auditoria_en_progreso(max_minutos=20):
        raise HTTPException(503, "Hay una auditoría en proceso. Intenta en unos minutos.")

    ext = Path(file.filename or "contrato").suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(400, "Solo se aceptan PDF o DOCX.")

    filename = file.filename or f"contrato{ext}"
    audit_id = str(uuid.uuid4())
    crear_auditoria(audit_id, user_id, filename=filename)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_audit_{user_id}_"))
    tmp_file = tmp_dir / f"contrato{ext}"
    tmp_file.write_bytes(await file.read())

    background_tasks.add_task(_run_audit, audit_id, user_id, tmp_dir, filename, usuario["email"], graph_enabled)
    return {"audit_id": audit_id, "status": "processing"}


@router.get("/audits")
def list_audits(user: dict = Depends(get_current_user)):
    """Lista el historial de auditorías del usuario autenticado."""
    user_id = int(user["sub"])
    return get_auditorias_usuario(user_id)


@router.get("/audit/{audit_id}")
def get_audit_result(audit_id: str, user: dict = Depends(get_current_user)):
    """Consulta el estado y resultado de una auditoría (lee desde DB)."""
    result = get_auditoria(audit_id)
    if not result:
        raise HTTPException(404, "Auditoría no encontrada.")
    return result


@router.patch("/audit/{audit_id}/cancelar")
def cancel_audit(audit_id: str, user: dict = Depends(get_current_user)):
    """Cancela una auditoría atascada marcándola como error en la DB."""
    result = get_auditoria(audit_id)
    if not result:
        raise HTTPException(404, "Auditoría no encontrada.")
    if result["status"] != "processing":
        raise HTTPException(400, "Solo se pueden cancelar auditorías en proceso.")
    actualizar_auditoria(
        audit_id,
        status="error",
        error_detail="Cancelada por el usuario.",
        progress_msg="Cancelada",
    )
    return {"ok": True}


async def _run_audit(audit_id: str, user_id: int, tmp_dir: Path, filename: str, email: str, graph_enabled: bool = False):
    import shutil
    async with _auditoria_lock:
        try:
            actualizar_auditoria(audit_id, progress_msg="Extrayendo texto del documento...", progress_pct=10)
            _, texto = await asyncio.get_event_loop().run_in_executor(
                None, lambda: procesar_documentos_carpeta(tmp_dir)
            )
            if not texto:
                actualizar_auditoria(audit_id, status="error", error_detail="No se pudo extraer texto.")
                return

            modo = "RAG + GraphRAG" if graph_enabled else "RAG"
            actualizar_auditoria(audit_id, progress_msg=f"Construyendo base de conocimiento ({modo})...", progress_pct=30)
            llm = await asyncio.get_event_loop().run_in_executor(None, build_llm)

            actualizar_auditoria(audit_id, progress_msg="Auditando secciones con 3 agentes IA...", progress_pct=55)
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(texto, llm, graph_enabled=graph_enabled)
            )
            duracion = round(time.time() - start, 1)

            actualizar_auditoria(audit_id, progress_msg="Generando informe final...", progress_pct=90)
            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            n_secciones = len(resultado.get("resultados_auditoria", []))
            registrar_auditoria(user_id)
            _log_web(user_id, "auditoria", filename, duracion=duracion, n_hallazgos=n_hallazgos)
            actualizar_auditoria(
                audit_id,
                status="done",
                informe=md,
                n_hallazgos=n_hallazgos,
                n_secciones=n_secciones,
                progress_msg="Completado",
                progress_pct=100,
            )
            # Notificar por email
            try:
                asunto, html, texto_plain = email_auditoria_lista(filename, n_hallazgos, n_secciones)
                enviar_email(email, asunto, html, texto_plain)
            except Exception as mail_err:
                print(f"[EMAIL] No se pudo enviar notificación a {email}: {mail_err}")
        except Exception as e:
            import traceback
            detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
            print(f"[AUDIT ERROR] {audit_id}: {detail}")
            actualizar_auditoria(audit_id, status="error", error_detail=str(e)[:500], progress_msg="Error")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _log_web(
    telegram_id: int,
    accion: str,
    detalle: str,
    duracion: float = None,
    n_hallazgos: int = None,
) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO logs (telegram_id, accion, detalle, timestamp, "
                "duracion_segundos, canal, n_hallazgos) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (telegram_id, accion, detalle, datetime.now().isoformat(),
                 duracion, "web", n_hallazgos),
            )
    except Exception:
        pass  # No interrumpir el flujo principal si el log falla
