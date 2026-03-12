"""Endpoints de contratos: subida, auditoría y consultas RAG."""

import asyncio
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from api.auth import get_current_user
from contractia.core.graph import construir_grafo_conocimiento, obtener_contexto_grafo
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.report import render_auditoria_markdown
from contractia.core.segmenter import construir_mapa_clausula_a_seccion, separar_en_secciones
from contractia.llm.provider import build_llm
from contractia.orchestrator import ejecutar_auditoria_contrato
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto
from contractia.telegram.correo.pdf_report import generar_pdf_auditoria
from contractia.telegram.correo.pdf_report_tecnico import generar_pdf_tecnico
from contractia.telegram.correo.sender import enviar_email
from contractia.telegram.correo.templates import email_auditoria_lista
from contractia.telegram.db.database import (
    crear_auditoria, get_auditoria, actualizar_auditoria, hay_auditoria_en_progreso,
    get_auditorias_usuario, get_texto_auditoria, get_conn,
)
from contractia.telegram.db.uso import puede_auditar, puede_preguntar, registrar_auditoria, registrar_pregunta
from contractia.telegram.db.usuarios import get_usuario

router = APIRouter(prefix="/contracts", tags=["contracts"])

# Semáforo global — igual que en el bot
from contractia.telegram.flows.audit_flow import _auditoria_lock

# Los retrievers, grafos y mapas de sección se almacenan por session_id (temporales, en memoria)
_retrievers: dict = {}
_graphs: dict = {}
_mapa_textos: dict = {}


class QueryRequest(BaseModel):
    pregunta: str
    session_id: str


class FromAuditRequest(BaseModel):
    audit_id: str


@router.post("/upload")
async def upload_contract(
    file: UploadFile = File(...),
    graph_enabled: bool = Form(False),
    user: dict = Depends(get_current_user),
):
    """Sube un contrato y lo indexa para consultas RAG (y opcionalmente GraphRAG)."""
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

        secciones = await asyncio.get_event_loop().run_in_executor(
            None, lambda: separar_en_secciones(texto)
        )
        vector_store = await asyncio.get_event_loop().run_in_executor(
            None, lambda: crear_vector_store(texto, secciones)
        )
        retriever = crear_retriever(vector_store)
        session_id = str(uuid.uuid4())
        _retrievers[session_id] = retriever

        # GraphRAG: construir grafo de conocimiento si el usuario lo solicitó
        if graph_enabled:
            try:
                llm_g = await asyncio.get_event_loop().run_in_executor(None, build_llm)
                grafo = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: construir_grafo_conocimiento(secciones, llm_g)
                )
                _graphs[session_id] = grafo
                _mapa_textos[session_id] = construir_mapa_clausula_a_seccion(secciones)
                print(f"[UPLOAD] GraphRAG listo para sesión {session_id[:8]}.")
            except Exception as e:
                print(f"[UPLOAD] GraphRAG no disponible: {e}")

        return {"session_id": session_id, "filename": file.filename, "graph_enabled": graph_enabled}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/session/from-audit")
async def session_from_audit(
    body: FromAuditRequest,
    user: dict = Depends(get_current_user),
):
    """Re-indexa un contrato auditado previamente para usarlo en consultas RAG."""
    user_id = int(user["sub"])

    # Verificar que la auditoría existe y pertenece al usuario
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, status, filename, graph_enabled FROM auditorias WHERE audit_id = %s",
            (body.audit_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Auditoría no encontrada.")
    if dict(row)["user_id"] != user_id and user.get("rol") != "admin":
        raise HTTPException(403, "No tienes acceso a esta auditoría.")
    if dict(row)["status"] != "done":
        raise HTTPException(400, "La auditoría aún no está completada.")

    texto = get_texto_auditoria(body.audit_id)
    if not texto:
        raise HTTPException(
            400,
            "Esta auditoría no tiene texto guardado. Re-sube el contrato para consultarlo.",
        )

    usuario = get_usuario(user_id)
    if not puede_preguntar(user_id, usuario["rol"]):
        raise HTTPException(429, "Límite diario de consultas alcanzado.")

    graph_enabled = bool(dict(row)["graph_enabled"])

    # Construir vector store RAG con secciones para fuentes legibles
    secciones = await asyncio.get_event_loop().run_in_executor(
        None, lambda: separar_en_secciones(texto)
    )
    vector_store = await asyncio.get_event_loop().run_in_executor(
        None, lambda: crear_vector_store(texto, secciones)
    )
    retriever = crear_retriever(vector_store)
    session_id = str(uuid.uuid4())
    _retrievers[session_id] = retriever

    # Reconstruir GraphRAG si la auditoría original lo usó
    if graph_enabled:
        try:
            llm_g = await asyncio.get_event_loop().run_in_executor(None, build_llm)
            grafo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: construir_grafo_conocimiento(secciones, llm_g)
            )
            _graphs[session_id] = grafo
            _mapa_textos[session_id] = construir_mapa_clausula_a_seccion(secciones)
            print(f"[FROM-AUDIT] GraphRAG listo para sesión {session_id[:8]}.")
        except Exception as e:
            print(f"[FROM-AUDIT] GraphRAG no disponible: {e}")

    return {
        "session_id": session_id,
        "filename": dict(row).get("filename") or "contrato",
        "graph_enabled": graph_enabled,
    }


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
        "REGLA DE CITACIÓN (obligatoria): Al responder, cita siempre las cláusulas o "
        "secciones exactas donde encontraste la información, usando el número de cláusula "
        "(ej. 'cláusula 6.11.a', 'numeral 8.2', 'Anexo III') y el nombre del capítulo o "
        "anexo correspondiente indicado en [Fuente: ...]. "
        "Si la información proviene de varias cláusulas, menciona todas.\n\n"
        "CONTEXTO:\n{contexto}\n"
        "{seccion_grafo}"
        "\nPREGUNTA: {pregunta}\n\nRESPUESTA:"
    )

    contexto = await asyncio.get_event_loop().run_in_executor(
        None, lambda: recuperar_contexto(retriever, body.pregunta, max_tokens=3000)
    )
    if not contexto:
        return {"respuesta": "No encontré información relevante sobre eso en el contrato."}

    # GraphRAG: enriquecer con contexto del grafo si la sesión lo tiene
    seccion_grafo = ""
    if body.session_id in _graphs:
        try:
            clausulas = list(set(re.findall(r"\b(\d+(?:\.\d+)*)\b", body.pregunta)))
            if clausulas:
                ctx_g = obtener_contexto_grafo(
                    clausulas, _graphs[body.session_id], _mapa_textos.get(body.session_id, {})
                )
                if ctx_g and "No hay relaciones" not in ctx_g:
                    seccion_grafo = f"\nRELACIONES ENTRE CLÁUSULAS (grafo):\n{ctx_g}\n"
        except Exception as e:
            print(f"[QUERY] Error GraphRAG: {e}")

    llm = await asyncio.get_event_loop().run_in_executor(None, build_llm)
    prompt = _PROMPT.format(contexto=contexto, seccion_grafo=seccion_grafo, pregunta=body.pregunta)
    start = time.time()
    respuesta = await asyncio.get_event_loop().run_in_executor(None, lambda: llm.invoke(prompt))
    duracion = round(time.time() - start, 1)
    content = respuesta.content if hasattr(respuesta, "content") else str(respuesta)
    if isinstance(content, list):
        texto = next((b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"), "")
    else:
        texto = content

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

    if file.size and file.size > 30 * 1024 * 1024:
        raise HTTPException(400, "El archivo supera el límite de 30 MB.")

    filename = file.filename or f"contrato{ext}"
    audit_id = str(uuid.uuid4())
    crear_auditoria(audit_id, user_id, filename=filename, graph_enabled=graph_enabled)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"contractia_audit_{user_id}_"))
    tmp_file = tmp_dir / f"contrato{ext}"
    tmp_file.write_bytes(await file.read())

    background_tasks.add_task(
        _run_audit, audit_id, user_id, tmp_dir, filename, usuario["email"],
        graph_enabled, usuario["rol"] == "admin",
    )
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


@router.get("/audit/{audit_id}/pdf")
def download_audit_pdf(audit_id: str, user: dict = Depends(get_current_user)):
    """Genera y devuelve el informe de auditoría en PDF para descarga."""
    result = get_auditoria(audit_id)
    if not result:
        raise HTTPException(404, "Auditoría no encontrada.")
    if result["status"] != "done" or not result.get("informe"):
        raise HTTPException(400, "El informe aún no está disponible.")

    filename = result.get("filename") or "contrato"
    try:
        pdf_bytes = generar_pdf_auditoria(result["informe"], filename)
    except Exception as e:
        import traceback
        print(f"[PDF] Error generando PDF para {audit_id}: {traceback.format_exc()}")
        raise HTTPException(500, f"Error al generar PDF: {type(e).__name__}: {str(e)[:300]}")
    nombre = filename.rsplit(".", 1)[0] + "_informe.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/audit/{audit_id}/pdf-tecnico")
def download_technical_pdf(audit_id: str, user: dict = Depends(get_current_user)):
    """Genera y devuelve el informe técnico (admin) en PDF para descarga."""
    if user.get("rol") != "admin":
        raise HTTPException(403, "Solo administradores pueden descargar el informe técnico.")

    import json
    import networkx as nx
    from contractia.core.graph import generar_imagen_grafo

    result = get_auditoria(audit_id)
    if not result:
        raise HTTPException(404, "Auditoría no encontrada.")
    if result["status"] != "done":
        raise HTTPException(400, "El informe aún no está disponible.")

    mt_json = result.get("metadata_tecnica")
    if not mt_json:
        raise HTTPException(404, "No hay datos técnicos para esta auditoría (¿fue realizada por un admin?).")

    try:
        metadata_tecnica = json.loads(mt_json)
    except Exception:
        raise HTTPException(500, "Error deserializando metadata técnica.")

    # Reconstruir grafo si está disponible
    grafo = None
    imagen_grafo_png = None
    gd_json = result.get("graph_data")
    if gd_json:
        try:
            grafo = nx.node_link_graph(json.loads(gd_json))
            imagen_grafo_png = generar_imagen_grafo(grafo)
        except Exception as ge:
            print(f"[PDF-TECNICO] Error reconstruyendo grafo: {ge}")

    filename = result.get("filename") or "contrato"
    try:
        pdf_bytes = generar_pdf_tecnico(
            metadata_tecnica=metadata_tecnica,
            grafo=grafo,
            imagen_grafo_png=imagen_grafo_png,
            filename_contrato=filename,
        )
    except Exception as e:
        raise HTTPException(500, f"Error al generar PDF técnico: {type(e).__name__}: {str(e)[:300]}")

    nombre = filename.rsplit(".", 1)[0] + "_tecnico.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


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


def _make_progress_callback(audit_id: str):
    """Devuelve un callback que actualiza el progreso en DB.

    Retorna True si la auditoría fue cancelada externamente (el loop debe detenerse).
    """
    def callback(pct: int, msg: str) -> bool:
        try:
            actualizar_auditoria(audit_id, progress_pct=pct, progress_msg=msg)
            state = get_auditoria(audit_id)
            return bool(state and state.get("status") != "processing")
        except Exception:
            return False
    return callback


async def _keepalive(stop: asyncio.Event, interval: int = 30) -> None:
    """Ping a /health cada `interval` segundos para evitar que Cloud Run escale a cero.

    Usa la URL pública del servicio (CLOUD_RUN_URL) para que el tráfico pase por
    el proxy de Cloud Run y sea contabilizado por el autoscaler. En local, usa localhost.
    """
    import httpx
    from contractia.config import CLOUD_RUN_URL
    base = CLOUD_RUN_URL.rstrip("/") if CLOUD_RUN_URL else "http://localhost:8080"
    url = f"{base}/health"
    while not stop.is_set():
        try:
            async with httpx.AsyncClient() as client:
                await client.get(url, timeout=5)
        except Exception:
            pass
        await asyncio.sleep(interval)


async def _run_audit(audit_id: str, user_id: int, tmp_dir: Path, filename: str, email: str, graph_enabled: bool = False, is_admin: bool = False):
    import shutil
    _stop_keepalive = asyncio.Event()
    _keepalive_task = asyncio.create_task(_keepalive(_stop_keepalive))
    async with _auditoria_lock:
        try:
            actualizar_auditoria(audit_id, progress_msg="Extrayendo texto del documento...", progress_pct=10)

            def _ocr_progress(pct: int, msg: str) -> None:
                try:
                    actualizar_auditoria(audit_id, progress_pct=pct, progress_msg=msg)
                except Exception:
                    pass

            _, texto = await asyncio.get_event_loop().run_in_executor(
                None, lambda: procesar_documentos_carpeta(tmp_dir, ocr_progress=_ocr_progress)
            )
            if not texto:
                actualizar_auditoria(audit_id, status="error", error_detail="No se pudo extraer texto.")
                return

            # Guardar texto para reutilizarlo en consultas interactivas futuras
            try:
                actualizar_auditoria(audit_id, texto_contrato=texto)
            except Exception:
                pass  # No crítico

            modo = "RAG + GraphRAG" if graph_enabled else "RAG"
            actualizar_auditoria(audit_id, progress_msg=f"Construyendo base de conocimiento ({modo})...", progress_pct=30)
            llm = await asyncio.get_event_loop().run_in_executor(None, build_llm)

            actualizar_auditoria(audit_id, progress_msg="Auditando sección 1…", progress_pct=55)
            progress_cb = _make_progress_callback(audit_id)
            start = time.time()
            resultado = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ejecutar_auditoria_contrato(
                    texto, llm, graph_enabled=graph_enabled, progress_callback=progress_cb
                )
            )
            duracion = round(time.time() - start, 1)

            actualizar_auditoria(audit_id, progress_msg="Generando informe final...", progress_pct=90)
            md = render_auditoria_markdown(resultado)
            n_hallazgos = sum(
                len(r.get("hallazgos", [])) for r in resultado.get("resultados_auditoria", [])
            )
            n_secciones = len(resultado.get("resultados_auditoria", []))
            registrar_auditoria(user_id)
            tipo_rag = "GraphRAG" if graph_enabled else "RAG"
            _log_web(user_id, "auditoria", filename, duracion=duracion, n_hallazgos=n_hallazgos, tipo_rag=tipo_rag)
            # Serializar datos técnicos (solo admins)
            import json
            import networkx as nx
            metadata_tecnica = resultado.get("metadata_tecnica")
            grafo = resultado.get("grafo")
            imagen_grafo_png = resultado.get("imagen_grafo_png")

            if is_admin and metadata_tecnica:
                try:
                    mt_json = json.dumps(metadata_tecnica, ensure_ascii=False)
                    gd_json = None
                    if grafo is not None and grafo.number_of_nodes() > 0:
                        gd_json = json.dumps(
                            nx.node_link_data(grafo), ensure_ascii=False
                        )
                    actualizar_auditoria(
                        audit_id,
                        metadata_tecnica=mt_json,
                        graph_data=gd_json,
                    )
                except Exception as te:
                    print(f"[TECNICO] No se pudo guardar metadata técnica: {te}")

            actualizar_auditoria(
                audit_id,
                status="done",
                informe=md,
                n_hallazgos=n_hallazgos,
                n_secciones=n_secciones,
                progress_msg="Completado",
                progress_pct=100,
            )
            # Notificar por email (PDF adjunto si se puede generar)
            try:
                asunto, html, texto_plain = email_auditoria_lista(filename, n_hallazgos, n_secciones)
                pdf_bytes = None
                adjunto_nombre = "informe_auditoria.pdf"
                try:
                    adjunto_nombre = filename.rsplit(".", 1)[0] + "_informe.pdf"
                    pdf_bytes = generar_pdf_auditoria(md, filename)
                except Exception as pdf_err:
                    print(f"[PDF] No se pudo generar PDF adjunto: {pdf_err}")

                # PDF técnico (solo admins)
                pdf_tecnico_bytes = None
                adjunto_tecnico_nombre = filename.rsplit(".", 1)[0] + "_tecnico.pdf"
                if is_admin and metadata_tecnica:
                    try:
                        pdf_tecnico_bytes = generar_pdf_tecnico(
                            metadata_tecnica=metadata_tecnica,
                            grafo=grafo,
                            imagen_grafo_png=imagen_grafo_png,
                            filename_contrato=filename,
                        )
                    except Exception as pt_err:
                        print(f"[PDF-TECNICO] No se pudo generar: {pt_err}")

                enviar_email(
                    email, asunto, html, texto_plain,
                    adjunto_pdf=pdf_bytes,
                    adjunto_nombre=adjunto_nombre,
                    adjunto_pdf_tecnico=pdf_tecnico_bytes,
                    adjunto_nombre_tecnico=adjunto_tecnico_nombre,
                )
            except Exception as mail_err:
                print(f"[EMAIL] No se pudo enviar notificación a {email}: {mail_err}")
        except Exception as e:
            import traceback
            detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
            print(f"[AUDIT ERROR] {audit_id}: {detail}")
            actualizar_auditoria(audit_id, status="error", error_detail=str(e)[:500], progress_msg="Error")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    _stop_keepalive.set()
    _keepalive_task.cancel()


def _log_web(
    telegram_id: int,
    accion: str,
    detalle: str,
    duracion: float = None,
    n_hallazgos: int = None,
    tipo_rag: str = None,
) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO logs (telegram_id, accion, detalle, timestamp, "
                "duracion_segundos, canal, n_hallazgos, tipo_rag) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (telegram_id, accion, detalle, datetime.now().isoformat(),
                 duracion, "web", n_hallazgos, tipo_rag),
            )
    except Exception:
        pass  # No interrumpir el flujo principal si el log falla
