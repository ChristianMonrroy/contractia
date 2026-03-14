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
from contractia.core.graph import construir_grafo_conocimiento, obtener_contexto_grafo
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

# Intentos máximos por agente si falla o el LLM devuelve error/timeout.
_MAX_REINTENTOS = 3
_PAUSA_REINTENTO_S = 10

# Modelos con cuota limitada: agentes en serie + pausa larga entre secciones.
_MODELOS_THROTTLE = {"gemini-3.1-pro-preview", "claude-sonnet-4-6", "claude-opus-4-6"}


def _ejecutar_con_reintento(agente, inputs: dict, audit_id: Optional[str] = None) -> dict:
    """Ejecuta un agente con hasta _MAX_REINTENTOS intentos.

    Si el LLM lanza un error (incluyendo timeout del cliente VertexAI),
    espera _PAUSA_REINTENTO_S segundos y reintenta. Nunca omite silenciosamente:
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
    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            return agente.ejecutar(inputs)
        except Exception as e:
            ultimo_error = e
            if intento < _MAX_REINTENTOS:
                _log(
                    f"Agente falló (intento {intento}/{_MAX_REINTENTOS}): {type(e).__name__}: {str(e)[:200]}. "
                    f"Reintentando en {_PAUSA_REINTENTO_S}s..."
                )
                time.sleep(_PAUSA_REINTENTO_S)
            else:
                _log(
                    f"Agente no respondió tras {_MAX_REINTENTOS} intentos: {type(ultimo_error).__name__}: {str(ultimo_error)[:200]}",
                    nivel="ERROR",
                )
    return {}


def _rag_estatico(retriever, texto_truncado: str) -> str:
    """Wrapper del RAG estático original para reutilización interna."""
    try:
        ctx = recuperar_contexto(retriever, texto_truncado[:500], max_tokens=2000)
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
                    print(f"   🔍 Scout: {len(ctx_scout)} chars de contexto enriquecido")
                else:
                    contexto_rag = _rag_estatico(retriever, texto_seccion)
            except Exception as e:
                print(f"   ⚠️ Scout falló ({e}), usando RAG estático.")
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
    _workers = 1 if modelo in _MODELOS_THROTTLE else 3
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
) -> Dict:
    """
    Pipeline completo de auditoría:
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
    """
    secciones, metadata_tecnica = separar_en_secciones_con_metadata(texto_contrato)
    indice_secciones = crear_indice_capitulos_anexos(secciones)
    indice_global_clausulas = crear_indice_global_clausulas(secciones)
    mapa_clausula_a_seccion = construir_mapa_clausula_a_seccion(secciones)
    nombres_anexos = [s["titulo"] for s in secciones if s.get("tipo") == "ANEXO"]

    # ── RAG: crear vector store ──
    retriever = None
    vector_store = None  # Declarar en scope amplio para pasarlo al Scout
    if RAG_ENABLED:
        try:
            print("\n📚 Construyendo base de conocimiento RAG...")
            vector_store = crear_vector_store(texto_contrato, secciones)
            retriever = crear_retriever(vector_store)
            modo_rag = "Hybrid RAG + Reranker + Scout" if AGENTIC_RAG_ENABLED else "Hybrid RAG + Reranker"
            print(f"✅ RAG activo ({modo_rag}).\n")
        except Exception as e:
            print(f"⚠️ RAG no disponible ({e}). Continuando sin RAG.\n")

    # ── GraphRAG: construir grafo de conocimiento ──
    grafo = None
    if graph_enabled:
        try:
            print("\n🕸️  Construyendo grafo de conocimiento (GraphRAG)...")
            grafo = construir_grafo_conocimiento(secciones, llm, modelo=modelo)
            print("✅ GraphRAG activo.\n")
        except Exception as e:
            print(f"⚠️ GraphRAG no disponible ({e}). Continuando sin grafo.\n")

    # ── Auditoría multi-agente ──
    resultados_auditoria = []
    labels = []
    if retriever:
        labels.append("RAG")
    if grafo is not None:
        labels.append("GraphRAG")
    label_str = " + ".join(labels) + " " if labels else ""
    n_secciones = len(secciones)
    print(f"\n🚀 Iniciando auditoría {label_str}en {n_secciones} secciones...")

    for i, sec in enumerate(tqdm(secciones, desc="Auditando Secciones")):
        # Actualizar progreso y verificar cancelación (55% → 88%)
        if progress_callback:
            pct = 55 + int((i / n_secciones) * 33)
            stop_requested = progress_callback(pct, f"Auditando sección {i + 1}/{n_secciones}…")
            if stop_requested:
                print(f"[AUDIT] Auditoría detenida en sección {i + 1} por cancelación externa.")
                break

        idx_local = crear_indice_de_clausulas_por_seccion(sec.get("contenido", ""))

        contexto_grafo = ""
        if grafo is not None:
            try:
                contexto_grafo = obtener_contexto_grafo(
                    idx_local, grafo, mapa_clausula_a_seccion
                )
            except Exception as e:
                print(f"⚠️ GraphRAG context error: {e}")

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

            if hallazgos:
                resultados_auditoria.append({
                    "seccion": sec.get("titulo", "Sección"),
                    "tipo": sec.get("tipo", "?"),
                    "hallazgos": hallazgos,
                })

            # Throttle models: longer pause to avoid 429 rate limit
            # Stable models (gemini-2.5-pro): 2s as before
            _pausa = 10 if modelo in _MODELOS_THROTTLE else 2
            time.sleep(_pausa)

        except Exception as e:
            print(f"⚠️ Error en sección '{sec.get('titulo')}': {e}")

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
