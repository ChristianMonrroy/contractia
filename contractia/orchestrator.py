"""
Orquestador principal: coordina segmentación, RAG y agentes multi-agente.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Set

from tqdm.auto import tqdm

from contractia.agents.factory import crear_agentes
from contractia.config import ENABLE_LLM, GRAPH_ENABLED, RAG_ENABLED
from contractia.core.graph import construir_grafo_conocimiento, obtener_contexto_grafo
from contractia.core.segmenter import (
    _get_all_section_numbers_as_str,
    construir_mapa_clausula_a_seccion,
    crear_indice_capitulos_anexos,
    crear_indice_de_clausulas_por_seccion,
    crear_indice_global_clausulas,
    separar_en_secciones,
)
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto


def auditar_consistencia(
    texto_seccion: str,
    indice_secciones: List[Dict],
    indice_global_clausulas: List[str],
    indice_clausulas_seccion: List[str],
    section_nums_to_ignore: Set[str],
    llm,
    retriever=None,
    contexto_grafo: str = "",
) -> List[Dict]:
    """Audita una sección individual con los tres agentes.

    Jurista y Cronista se ejecutan en paralelo (son independientes).
    El Auditor se ejecuta después del Jurista (necesita sus referencias externas).
    """

    if not ENABLE_LLM or llm is None:
        return []

    jurista, auditor, cronista = crear_agentes(llm)

    # ── RAG: contexto adicional de otras secciones ──
    contexto_rag = ""
    if retriever is not None:
        try:
            consulta = texto_seccion[:500]
            ctx = recuperar_contexto(retriever, consulta, max_tokens=2000)
            if ctx:
                contexto_rag = (
                    "\n\n--- CONTEXTO ADICIONAL (de otras secciones, vía RAG) ---\n"
                    + ctx
                    + "\n--- FIN CONTEXTO ADICIONAL ---\n"
                )
        except Exception:
            contexto_rag = ""

    # Preparar índices (sin LLM, rápido)
    str_idx_sec = ", ".join([f"{x['tipo']} {x['n']}" for x in indice_secciones])
    str_idx_glob = ", ".join(indice_global_clausulas)
    local_filtrado = [
        x for x in indice_clausulas_seccion
        if x not in section_nums_to_ignore and not (x.isdigit() and int(x) > 100)
    ]
    str_idx_loc = ", ".join(local_filtrado) if local_filtrado else "Ninguna"

    hallazgos_totales = []

    # ── Fase 1: Jurista + Cronista en paralelo (son independientes entre sí) ──
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_jurista = pool.submit(
            jurista.ejecutar,
            {"texto": texto_seccion, "contexto_grafo": contexto_grafo},
        )
        fut_cronista = pool.submit(
            cronista.ejecutar,
            {"texto": texto_seccion, "contexto_grafo": contexto_grafo},
        )

        try:
            res_jurista = fut_jurista.result()
        except Exception:
            res_jurista = {}

        try:
            res_cronista = fut_cronista.result()
        except Exception as e:
            print(f"Error Cronista: {e}")
            res_cronista = {}

    # Procesar resultado del Jurista
    if isinstance(res_jurista, list):
        lista_externa = [str(x) for x in res_jurista]
    elif isinstance(res_jurista, dict):
        lista_externa = res_jurista.get("referencias_externas", [])
    else:
        lista_externa = []
    str_externas = ", ".join(lista_externa) if lista_externa else "Ninguna"

    # Procesar resultado del Cronista
    if isinstance(res_cronista, dict):
        if res_cronista.get("hay_errores_logicos") or res_cronista.get("hay_inconsistencia_plazos"):
            hallazgos_totales.extend(res_cronista.get("hallazgos_procesos", []))
    elif isinstance(res_cronista, list):
        hallazgos_totales.extend(res_cronista)

    # ── Fase 2: Auditor (usa refs_externas del Jurista) ──
    try:
        res_aud = auditor.ejecutar({
            "texto": texto_seccion + contexto_rag,  # RAG enriquece al auditor
            "idx_glob": str_idx_glob,
            "idx_sec": str_idx_sec,
            "idx_loc": str_idx_loc,
            "refs_externas": str_externas,
            "contexto_grafo": contexto_grafo,
        })
        if isinstance(res_aud, dict) and res_aud.get("hay_inconsistencias"):
            hallazgos_totales.extend(res_aud.get("hallazgos", []))
        elif isinstance(res_aud, list):
            hallazgos_totales.extend(res_aud)
    except Exception as e:
        print(f"Error Auditor: {e}")

    return hallazgos_totales


def ejecutar_auditoria_contrato(
    texto_contrato: str,
    llm,
    graph_enabled: bool = GRAPH_ENABLED,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict:
    """
    Pipeline completo de auditoría:
      1. Segmentación regex
      2. Construcción de índices
      3. Creación de vector store RAG (si está habilitado)
      4. Auditoría multi-agente por sección (Jurista+Cronista en paralelo, luego Auditor)

    Args:
        progress_callback: función(pct: int, msg: str) llamada al iniciar cada sección.
                           Permite actualizar el progreso en tiempo real desde el caller.
    """
    secciones = separar_en_secciones(texto_contrato)
    indice_secciones = crear_indice_capitulos_anexos(secciones)
    indice_global_clausulas = crear_indice_global_clausulas(secciones)
    mapa_clausula_a_seccion = construir_mapa_clausula_a_seccion(secciones)
    section_nums_to_ignore = _get_all_section_numbers_as_str(secciones)

    # ── RAG: crear vector store ──
    retriever = None
    if RAG_ENABLED:
        try:
            print("\n📚 Construyendo base de conocimiento RAG...")
            vector_store = crear_vector_store(texto_contrato, secciones)
            retriever = crear_retriever(vector_store)
            print("✅ RAG activo: los agentes consultarán contexto relevante.\n")
        except Exception as e:
            print(f"⚠️ RAG no disponible ({e}). Continuando sin RAG.\n")

    # ── GraphRAG: construir grafo de conocimiento ──
    grafo = None
    if graph_enabled:
        try:
            print("\n🕸️  Construyendo grafo de conocimiento (GraphRAG)...")
            grafo = construir_grafo_conocimiento(secciones, llm)
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
        # Actualizar progreso: de 55% a 88% durante el loop de secciones
        if progress_callback:
            pct = 55 + int((i / n_secciones) * 33)
            progress_callback(pct, f"Auditando sección {i + 1}/{n_secciones}…")

        idx_local = crear_indice_de_clausulas_por_seccion(sec.get("contenido", ""))

        # Contexto del grafo para esta sección
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
                indice_secciones=indice_secciones,
                indice_global_clausulas=indice_global_clausulas,
                indice_clausulas_seccion=idx_local,
                section_nums_to_ignore=section_nums_to_ignore,
                llm=llm,
                retriever=retriever,
                contexto_grafo=contexto_grafo,
            )

            if hallazgos:
                resultados_auditoria.append({
                    "seccion": sec.get("titulo", "Sección"),
                    "tipo": sec.get("tipo", "?"),
                    "hallazgos": hallazgos,
                })

            time.sleep(0.5)  # Pausa breve entre secciones (rate-limit safe a <10 req/s)

        except Exception as e:
            print(f"⚠️ Error en sección '{sec.get('titulo')}': {e}")

    return {
        "secciones": secciones,
        "indice_secciones": indice_secciones,
        "indice_global_clausulas": indice_global_clausulas,
        "resultados_auditoria": resultados_auditoria,
    }
