"""
Orquestador principal: coordina segmentación, RAG y agentes multi-agente.

v9.3.0: Alineación con notebook vs14
- Jurista ahora detecta inconsistencias procedimentales (no normativa externa)
- Los 3 agentes se ejecutan en paralelo (son independientes entre sí)
- Auditor ya no recibe idx_sec, idx_loc ni refs_externas
- sleep entre secciones: 0.5s → 2s
- auditar_consistencia() con firma simplificada

v9.3.1: Sin truncado de sección (igual que notebook)
- Eliminado _MAX_SECTION_CHARS: se envía el texto completo de cada sección
- Evita falsos positivos por literales cortados (ej. literal k de Cláusula 3.3)

v9.3.2: Reducción de falsos positivos y duplicados
- contexto_rag se pasa como variable separada {contexto_rag} (no mezclado en {texto})
- Evita que los agentes auditen contenido del contexto RAG en lugar de la sección
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Dict, List, Optional

from tqdm.auto import tqdm

from contractia.agents.factory import crear_agentes, crear_scout
from contractia.config import AGENTIC_RAG_ENABLED, ENABLE_LLM, GRAPH_ENABLED, RAG_ENABLED
from contractia.core.sanitizer import sanitizar_texto
from contractia.core.security import registrar_y_alertar, verificar_seguridad_documento
from contractia.core.graph import construir_grafo_conocimiento, obtener_contexto_grafo
from contractia.core.log_context import log
from contractia.core.segmenter import (
    _get_all_section_numbers_as_str,
    construir_mapa_clausula_a_seccion,
    crear_indice_capitulos_anexos,
    crear_indice_de_clausulas_por_seccion,
    crear_indice_global_clausulas,
    separar_en_secciones,
    separar_en_secciones_con_metadata,
)
from contractia.core.graph import generar_imagen_grafo
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto

class PromptInjectionDetectedError(Exception):
    """Se lanza cuando el escaneo de seguridad detecta prompt injection en el documento."""
    pass


# Intentos máximos por agente si falla o el LLM devuelve error/timeout.
_MAX_REINTENTOS = 3
_MAX_REINTENTOS_THROTTLE = 5   # Modelos lentos (Gemini 3.1, Claude 4.x)
_PAUSA_REINTENTO_S = 10        # Modelos estables (Gemini 2.5 Pro)
_PAUSA_REINTENTO_THROTTLE_S = 30  # Modelos con cuota estricta (Claude 4.x, Gemini 3.1)

# Modelos con cuota limitada: agentes en serie + pausa larga entre secciones.
_MODELOS_THROTTLE = {"gemini-3.1-pro-preview", "claude-sonnet-4-6", "claude-opus-4-6"}


def _log_directo(msg: str, audit_id: Optional[str] = None) -> None:
    """Log que llega a stdout (notebook/tqdm) Y directamente a la DB.

    Necesario para mensajes de FASE: el ContextVar de log_context no se propaga
    al hilo de run_in_executor en Cloud Run. Este patrón replica lo que ya
    hace _ejecutar_con_reintento para sus logs de error.
    """
    log(msg)
    if audit_id:
        try:
            from contractia.telegram.db.database import agregar_log_auditoria
            agregar_log_auditoria(audit_id, msg)
        except Exception:
            pass


def _ejecutar_con_reintento(agente, inputs: dict, audit_id: Optional[str] = None, pausa_s: int = _PAUSA_REINTENTO_S, max_reintentos: int = _MAX_REINTENTOS) -> dict:
    """Ejecuta un agente con hasta max_reintentos intentos.

    Si el LLM lanza un error (incluyendo timeout del cliente VertexAI),
    espera pausa_s segundos y reintenta. Nunca omite silenciosamente:
    sólo devuelve {} si TODOS los intentos fallan (situación excepcional).
    """
    def _log(msg: str, nivel: str = "WARN") -> None:
        print(f"⚠️  {msg}")
        if audit_id:
            try:
                from contractia.telegram.db.database import agregar_log_auditoria
                agregar_log_auditoria(audit_id, msg, nivel=nivel)
            except Exception:
                pass

    ultimo_error = None
    for intento in range(1, max_reintentos + 1):
        try:
            return agente.ejecutar(inputs)
        except Exception as e:
            ultimo_error = e
            if intento < max_reintentos:
                _log(
                    f"Agente falló (intento {intento}/{max_reintentos}): {type(e).__name__}: {str(e)[:200]}. "
                    f"Reintentando en {pausa_s}s..."
                )
                time.sleep(pausa_s)
            else:
                _log(
                    f"Agente no respondió tras {max_reintentos} intentos: {type(ultimo_error).__name__}: {str(ultimo_error)[:200]}",
                    nivel="ERROR",
                )
    return {}


def _rag_estatico(retriever, texto_truncado: str) -> str:
    """Wrapper del RAG estático original para reutilización interna."""
    try:
        ctx = recuperar_contexto(retriever, texto_truncado[:500], max_tokens=1000)
        if ctx:
            return (
                "\n\n--- CONTEXTO ADICIONAL (de otras secciones, vía RAG) ---\n"
                + ctx
                + "\n--- FIN CONTEXTO ADICIONAL ---\n"
            )
        return ""
    except Exception:
        return ""


def auditar_consistencia(
    texto_seccion: str,
    indice_global_clausulas: List[str],
    llm,
    retriever=None,
    vector_store=None,
    contexto_grafo: str = "",
    modelo: Optional[str] = None,
    nombres_anexos: Optional[List[str]] = None,
    audit_id: Optional[str] = None,
) -> List[Dict]:
    """Audita una sección individual con los tres agentes en paralelo.

    Los tres agentes (Jurista, Auditor, Cronista) son independientes entre sí
    y se ejecutan concurrentemente. Cada agente reintenta hasta _MAX_REINTENTOS
    veces antes de devolver vacío.
    """

    if not ENABLE_LLM or llm is None:
        return []

    jurista, auditor, cronista = crear_agentes(llm)

    # ── RAG: contexto adicional (estático o agéntico según config) ──────────────
    contexto_rag = ""
    if retriever is not None:
        if AGENTIC_RAG_ENABLED and vector_store is not None:
            try:
                scout = crear_scout(llm, retriever, vector_store)
                ctx_scout = scout.ejecutar(texto_seccion)
                if ctx_scout:
                    contexto_rag = (
                        "\n\n--- CONTEXTO AGÉNTICO (Scout v9.0) ---\n"
                        + ctx_scout
                        + "\n--- FIN CONTEXTO SCOUT ---\n"
                    )
                    log(f"   Scout: {len(ctx_scout)} chars de contexto enriquecido")
                else:
                    contexto_rag = _rag_estatico(retriever, texto_seccion)
            except Exception as e:
                log(f"   ⚠️ Scout falló ({e}), usando RAG estático.")
                contexto_rag = _rag_estatico(retriever, texto_seccion)
        else:
            contexto_rag = _rag_estatico(retriever, texto_seccion)

    clausulas_str = ", ".join(indice_global_clausulas) if indice_global_clausulas else "Ninguna"
    anexos_str = ", ".join(nombres_anexos) if nombres_anexos else "Ninguno"
    str_idx_glob = f"CLÁUSULAS: {clausulas_str} | ANEXOS: {anexos_str}"

    hallazgos_totales = []
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    # ── Los 3 agentes son independientes → paralelo en modelos estables,
    #    secuencial en modelos con cuota limitada (preview o admin) ───────────────
    _is_throttle = modelo in _MODELOS_THROTTLE
    _workers = 1 if _is_throttle else 3
    _pausa_retry = _PAUSA_REINTENTO_THROTTLE_S if _is_throttle else _PAUSA_REINTENTO_S
    _reintentos = _MAX_REINTENTOS_THROTTLE if _is_throttle else _MAX_REINTENTOS
    with ThreadPoolExecutor(max_workers=_workers) as pool:
        fut_jurista = pool.submit(
            _ejecutar_con_reintento,
            jurista,
            {
                "texto": texto_seccion,
                "contexto_grafo": contexto_grafo,
                "contexto_rag": contexto_rag,
                "fecha_actual": fecha_hoy,
            },
            audit_id,
            _pausa_retry,
            _reintentos,
        )
        fut_auditor = pool.submit(
            _ejecutar_con_reintento,
            auditor,
            {
                "texto": texto_seccion,
                "idx_glob": str_idx_glob,
                "contexto_grafo": contexto_grafo,
                "contexto_rag": contexto_rag,
                "fecha_actual": fecha_hoy,
            },
            audit_id,
            _pausa_retry,
            _reintentos,
        )
        fut_cronista = pool.submit(
            _ejecutar_con_reintento,
            cronista,
            {
                "texto": texto_seccion,
                "contexto_grafo": contexto_grafo,
                "contexto_rag": contexto_rag,
                "fecha_actual": fecha_hoy,
            },
            audit_id,
            _pausa_retry,
            _reintentos,
        )
        res_jurista = fut_jurista.result()
        res_auditor = fut_auditor.result()
        res_cronista = fut_cronista.result()

    # Procesar resultado del Jurista (inconsistencias procedimentales)
    if isinstance(res_jurista, dict) and res_jurista.get("hay_inconsistencias"):
        hallazgos_totales.extend(res_jurista.get("hallazgos", []))
    elif isinstance(res_jurista, list):
        hallazgos_totales.extend(res_jurista)

    # Procesar resultado del Auditor (referencias cruzadas)
    if isinstance(res_auditor, dict) and res_auditor.get("hay_inconsistencias"):
        hallazgos_totales.extend(res_auditor.get("hallazgos", []))
    elif isinstance(res_auditor, list):
        hallazgos_totales.extend(res_auditor)

    # Procesar resultado del Cronista (plazos)
    if isinstance(res_cronista, dict):
        if res_cronista.get("hay_errores_logicos") or res_cronista.get("hay_inconsistencia_plazos"):
            hallazgos_totales.extend(res_cronista.get("hallazgos_procesos", []))
    elif isinstance(res_cronista, list):
        hallazgos_totales.extend(res_cronista)

    return hallazgos_totales


def ejecutar_auditoria_contrato(
    texto_contrato: str,
    llm,
    graph_enabled: bool = GRAPH_ENABLED,
    progress_callback: Optional[Callable[[int, str], bool]] = None,
    modelo: Optional[str] = None,
    audit_id: Optional[str] = None,
    user_id: Optional[int] = None,
    filename: Optional[str] = None,
) -> Dict:
    """
    Pipeline completo de auditoría:
      0. Sanitización + escaneo de seguridad (prompt injection)
      1. Segmentación regex
      2. Construcción de índices
      3. Creación de vector store RAG (si está habilitado)
      4. Auditoría multi-agente por sección (3 agentes en paralelo)

    Args:
        progress_callback: función(pct: int, msg: str) -> bool.
                           Llamada al iniciar cada sección.
                           Si devuelve True, el loop se detiene (cancelación externa).
        modelo: ID de modelo VertexAI a usar (ej. 'gemini-3.1-pro-preview').
                Si None, usa el default de config (VERTEXAI_MODEL).
        user_id: ID del usuario que solicitó la auditoría (para registro de injection).
        filename: Nombre del archivo subido (para registro de injection).
    """
    # ── CAPA 1: Sanitización programática ──
    _log_directo("--- Escudo de seguridad: Sanitización (Capa 1) ---", audit_id)
    resultado_sanitizacion = sanitizar_texto(texto_contrato)
    texto_contrato = resultado_sanitizacion.texto_limpio
    if resultado_sanitizacion.chars_eliminados > 0:
        _log_directo(f"Sanitización: {resultado_sanitizacion.chars_eliminados} caracteres invisibles eliminados.", audit_id)
    if resultado_sanitizacion.tiene_alertas:
        _log_directo(f"Sanitización: {len(resultado_sanitizacion.alertas)} patrón(es) sospechoso(s) detectado(s).", audit_id)

    # ── CAPA 2: Escaneo LLM pre-auditoría ──
    if ENABLE_LLM and llm is not None:
        _log_directo("--- Escudo de seguridad: Escaneo LLM (Capa 2) ---", audit_id)
        if progress_callback:
            progress_callback(10, "Escaneando seguridad del documento...")
        resultado_seguridad = verificar_seguridad_documento(
            texto=texto_contrato,
            alertas=resultado_sanitizacion.alertas,
            llm=llm,
            audit_id=audit_id,
        )
        if not resultado_seguridad.es_seguro:
            _log_directo(
                f"ALERTA: Prompt injection detectado — {resultado_seguridad.evidencia}",
                audit_id,
            )
            # Registrar en DB y alertar al admin por correo
            if audit_id and user_id is not None:
                registrar_y_alertar(
                    resultado=resultado_seguridad,
                    audit_id=audit_id,
                    user_id=user_id,
                    filename=filename or "desconocido",
                )
            raise PromptInjectionDetectedError(resultado_seguridad.evidencia)
        _log_directo("Documento seguro — continuando auditoría.", audit_id)

    secciones, metadata_tecnica = separar_en_secciones_con_metadata(texto_contrato)
    indice_secciones = crear_indice_capitulos_anexos(secciones)
    indice_global_clausulas = crear_indice_global_clausulas(secciones)
    mapa_clausula_a_seccion = construir_mapa_clausula_a_seccion(secciones)
    nombres_anexos = [s["titulo"] for s in secciones if s.get("tipo") == "ANEXO"]

    # ── FASE 0: Estructura del documento ──
    _caps = [s for s in secciones if s.get("tipo") == "CAPITULO"]
    _anxs = [s for s in secciones if s.get("tipo") == "ANEXO"]
    _log_directo("--- FASE 0: Análisis Estructural ---", audit_id)
    _log_directo(f"Detectados {len(_caps)} capítulos y {len(_anxs)} anexos (total {len(secciones)} secciones).", audit_id)

    # ── FASE 0.5: Índice global ──
    _log_directo("--- FASE 0.5: Índice Global de Cláusulas ---", audit_id)
    _log_directo(f"Cláusulas: {', '.join(indice_global_clausulas) if indice_global_clausulas else 'Ninguna detectada.'}", audit_id)
    _log_directo(f"Anexos: {', '.join(nombres_anexos) if nombres_anexos else 'Ninguno detectado.'}", audit_id)

    # ── RAG: crear vector store ──
    retriever = None
    vector_store = None  # Declarar en scope amplio para pasarlo al Scout
    if RAG_ENABLED:
        try:
            log("\n📚 Construyendo base de conocimiento RAG...")
            vector_store = crear_vector_store(texto_contrato, secciones)
            retriever = crear_retriever(vector_store)
            modo_rag = "Hybrid RAG + Reranker + Scout" if AGENTIC_RAG_ENABLED else "Hybrid RAG + Reranker"
            log(f"✅ RAG activo ({modo_rag}).")
        except Exception as e:
            log(f"⚠️ RAG no disponible ({e}). Continuando sin RAG.")

    # ── GraphRAG: construir grafo de conocimiento ──
    grafo = None
    if graph_enabled:
        try:
            log("\n🕸️  Construyendo grafo de conocimiento (GraphRAG)...")
            grafo = construir_grafo_conocimiento(secciones, llm, modelo=modelo, audit_id=audit_id)
            log("✅ GraphRAG activo.")
        except Exception as e:
            log(f"⚠️ GraphRAG no disponible ({e}). Continuando sin grafo.")

    # ── Auditoría multi-agente ──
    resultados_auditoria = []
    labels = []
    if retriever:
        labels.append("RAG")
    if grafo is not None:
        labels.append("GraphRAG")
    label_str = " + ".join(labels) + " " if labels else ""
    n_secciones = len(secciones)
    log(f"\n🚀 Iniciando auditoría {label_str}en {n_secciones} secciones...")

    for i, sec in enumerate(tqdm(secciones, desc="Auditando Secciones")):
        # Actualizar progreso y verificar cancelación (55% → 88%)
        if progress_callback:
            pct = 55 + int((i / n_secciones) * 33)
            stop_requested = progress_callback(pct, f"Auditando sección {i + 1}/{n_secciones}…")
            if stop_requested:
                log(f"[AUDIT] Auditoría detenida en sección {i + 1} por cancelación externa.")
                break

        idx_local = crear_indice_de_clausulas_por_seccion(sec.get("contenido", ""))

        contexto_grafo = ""
        if grafo is not None:
            try:
                contexto_grafo = obtener_contexto_grafo(
                    idx_local, grafo, mapa_clausula_a_seccion
                )
            except Exception as e:
                log(f"⚠️ GraphRAG context error: {e}")

        titulo_sec = sec.get("titulo", f"Sección {i + 1}")
        _log_directo(f"--- Auditando: {titulo_sec} ({i + 1}/{n_secciones}) ---", audit_id)
        try:
            hallazgos = auditar_consistencia(
                texto_seccion=sec.get("contenido", ""),
                indice_global_clausulas=indice_global_clausulas,
                llm=llm,
                retriever=retriever,
                vector_store=vector_store,
                contexto_grafo=contexto_grafo,
                modelo=modelo,
                nombres_anexos=nombres_anexos,
                audit_id=audit_id,
            )

            n_h = len(hallazgos) if hallazgos else 0
            if hallazgos:
                resultados_auditoria.append({
                    "seccion": sec.get("titulo", "Sección"),
                    "tipo": sec.get("tipo", "?"),
                    "hallazgos": hallazgos,
                })
                _log_directo(f"  {n_h} hallazgo(s) encontrado(s).", audit_id)
            else:
                _log_directo(f"  Sin hallazgos.", audit_id)

            # Throttle models: longer pause to avoid 429 rate limit
            # Stable models (gemini-2.5-pro): 2s as before
            _pausa = 10 if modelo in _MODELOS_THROTTLE else 2
            time.sleep(_pausa)

        except Exception as e:
            log(f"⚠️ Error en sección '{sec.get('titulo')}': {e}")

    # Generar imagen del grafo (None si GraphRAG no estaba activo)
    imagen_grafo_png: Optional[bytes] = generar_imagen_grafo(grafo) if grafo is not None else None

    return {
        "secciones": secciones,
        "indice_secciones": indice_secciones,
        "indice_global_clausulas": indice_global_clausulas,
        "resultados_auditoria": resultados_auditoria,
        # Datos técnicos para el informe admin
        "metadata_tecnica": metadata_tecnica,
        "grafo": grafo,
        "imagen_grafo_png": imagen_grafo_png,
        "modelo_usado": modelo or "gemini-2.5-pro",
    }
