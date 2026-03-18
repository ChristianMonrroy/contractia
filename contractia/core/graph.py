"""
Construcción y consulta del grafo de conocimiento (GraphRAG).

Extrae tripletas (entidad, relación, entidad) de cada sección del contrato
usando el LLM, y construye un DiGraph de networkx. El grafo permite a los
agentes navegar relaciones entre cláusulas, leyes y plazos.

v9.3.0:
- Prompt de extracción alineado con notebook vs14:
  · Prohibición estricta de nodos externos (leyes, decretos, normas)
  · Elimina relación SE_RIGE_POR (solo relaciones internas)
  · XML tags para delimitar secciones
  · Sin truncado de texto (se envía sección completa)
- obtener_contexto_grafo: recorrido directo sucesores+predecesores (depth 1)
  en lugar de ego_graph(radius=2) — alineado con notebook vs14
- Búsqueda de nodos por \b word-boundary (alineado con notebook)
"""

import io
import re
import time
from typing import Dict, List, Optional

import networkx as nx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from contractia.agents.base import parse_json_seguro
from contractia.core.log_context import log

_PROMPT_EXTRACCION = PromptTemplate(
    template=(
        "# ROL\n"
        "Eres un experto en extracción de datos legales y grafos de conocimiento.\n\n"

        "# TAREA\n"
        "Analiza el texto de un contrato y extrae las relaciones lógicas internas en formato de tripletas.\n\n"

        "# REGLAS DE EXTRACCIÓN\n"
        "- **Entidades válidas:** Cláusulas, Plazos, Roles, Entregables, Penalidades.\n"
        "- **REGLA DE DESAMBIGUACIÓN (MUY IMPORTANTE):** Para evitar colisiones entre el contrato "
        "principal y los anexos, SIEMPRE incluye el nombre de la sección o anexo en la entidad de la "
        "cláusula. Ejemplo: Usa 'Cláusula 7.1 (Capítulo VII)' o 'Cláusula 7.1 (Anexo 22)' en lugar "
        "de solo 'Cláusula 7.1'.\n"
        "- **PROHIBICIÓN ESTRICTA:** NO extraigas, ni menciones, ni crees nodos para leyes, normativas, "
        "códigos civiles, decretos o cualquier documento externo al contrato. El análisis es 100% interno.\n"
        "- **Relaciones válidas:** REFERENCIA_A, ESTABLECE_PLAZO, MODIFICA_A, DEPENDE_DE, OBLIGA_A.\n\n"

        "# FORMATO DE SALIDA\n"
        "Responde ÚNICAMENTE con un bloque de código JSON válido. No incluyas texto fuera del bloque JSON.\n\n"
        "```json\n"
        "[\n"
        "  {{\"origen\": \"Cláusula 5.1 (Capítulo V)\", \"relacion\": \"REFERENCIA_A\", "
        "\"destino\": \"Cláusula 8.2 (Capítulo VIII)\", \"contexto\": \"Para el pago de penalidades\"}},\n"
        "  {{\"origen\": \"Contratista\", \"relacion\": \"OBLIGA_A\", "
        "\"destino\": \"Cláusula 3 (Anexo 1)\", \"contexto\": \"Entrega de informes\"}}\n"
        "]\n"
        "```\n\n"

        "# DATOS DE ENTRADA\n"
        "<texto_seccion>\n{texto}\n</texto_seccion>\n"
    ),
    input_variables=["texto"],
)


_GRAPH_MODELOS_THROTTLE = {"gemini-3.1-pro-preview", "claude-sonnet-4-6", "claude-opus-4-6"}


class GrafoCancelledError(Exception):
    """Señal de que el usuario canceló la construcción del grafo."""
    pass


def construir_grafo_conocimiento(secciones: List[Dict], llm, modelo: Optional[str] = None, audit_id: Optional[str] = None, on_progress=None, cancel_check=None) -> nx.DiGraph:
    """
    Construye un grafo de conocimiento a partir de las secciones del contrato.

    Por cada sección:
      - Fuerza la creación del nodo del Capítulo/Anexo
      - Llama al LLM para extraer tripletas (origen, relacion, destino, contexto)
      - Añade aristas al grafo con los atributos de relación
      - Añade arista jerárquica: titulo_seccion → origen (relacion=CONTIENE)

    Returns:
        nx.DiGraph con nodos de entidades y aristas de relaciones.
    """
    log("--- FASE 1.5: Construyendo Grafo de Conocimiento (GraphRAG) ---")
    if audit_id:
        try:
            from contractia.telegram.db.database import agregar_log_auditoria
            agregar_log_auditoria(audit_id, "--- FASE 1.5: Construyendo Grafo de Conocimiento (GraphRAG) ---")
        except Exception:
            pass
    G = nx.DiGraph()
    # Modelos con cuota estricta necesitan más pausa entre llamadas al grafo
    _model_name = modelo or str(getattr(llm, "model_name", "") or "")
    _sleep_s = 8 if _model_name in _GRAPH_MODELOS_THROTTLE else 1
    try:
        cadena = _PROMPT_EXTRACCION | llm | StrOutputParser()
    except Exception as e:
        log(f"⚠️ No se pudo construir la cadena GraphRAG: {e}")
        return G  # Grafo vacío; la auditoría continuará sin GraphRAG

    total = len(secciones)
    for i, sec in enumerate(secciones, 1):
        # Verificar cancelación antes de cada sección
        if cancel_check and cancel_check():
            log(f"  ⛔ Grafo cancelado por el usuario en sección [{i}/{total}]")
            raise GrafoCancelledError("Cancelado por el usuario")

        titulo = sec.get("titulo", "Sección Desconocida")
        contenido = sec.get("contenido", "")
        if not contenido.strip():
            log(f"  Grafo [{i}/{total}] {titulo} — vacía, omitida")
            continue

        # Forzar la creación del nodo del Capítulo/Anexo
        G.add_node(titulo, tipo=sec.get("tipo", "DESCONOCIDO"))

        t0 = time.time()
        try:
            raw = cadena.invoke({"texto": contenido})
            tripletas = parse_json_seguro(raw)
            n_tripletas = 0

            if not isinstance(tripletas, list) or len(tripletas) == 0:
                raw_preview = (raw[:200] if raw else "(vacío)").replace("\n", " ")
                log(f"  [DEBUG] {titulo} → type={type(tripletas).__name__}, raw[:200]={raw_preview}")

            if isinstance(tripletas, list):
                for t in tripletas:
                    if not isinstance(t, dict):
                        continue
                    origen = t.get("origen", "").strip()
                    destino = t.get("destino", "").strip()
                    relacion = t.get("relacion", "").strip()
                    if not origen or not destino or not relacion:
                        continue
                    # Arista de relación extraída
                    G.add_edge(
                        origen, destino,
                        relacion=relacion,
                        contexto=t.get("contexto", ""),
                    )
                    # Arista jerárquica: sección → entidad
                    G.add_edge(
                        titulo, origen,
                        relacion="CONTIENE",
                        contexto="Estructura del documento",
                    )
                    n_tripletas += 1

            elapsed = round(time.time() - t0, 1)
            log(f"  Grafo [{i}/{total}] {titulo} — {n_tripletas} tripletas ({elapsed}s)")
            if on_progress:
                try:
                    on_progress(i, total, titulo, n_tripletas)
                except Exception:
                    pass
            time.sleep(_sleep_s)  # Rate limit VertexAI (más largo para modelos throttled)

        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            log(f"  ⚠️ Grafo [{i}/{total}] {titulo} — ERROR ({elapsed}s): {e}")
            if on_progress:
                try:
                    on_progress(i, total, titulo, 0)
                except Exception:
                    pass

    log(
        f"✅ Grafo construido: {G.number_of_nodes()} nodos, "
        f"{G.number_of_edges()} relaciones."
    )
    return G


def obtener_contexto_grafo(
    clausulas_locales: List[str],
    G: nx.DiGraph,
    mapa_textos: Dict[str, Dict],
) -> str:
    if G is None or G.number_of_nodes() == 0:
        return "No hay relaciones en el grafo para esta sección."

    contexto = []
    nodos_vistos: set = set()

    for cid in clausulas_locales:
        # Búsqueda por word-boundary: evita que "3.3" matchee "13.3"
        nodos_grafo = [
            n for n in G.nodes()
            if re.search(rf"\b{re.escape(cid)}\b", str(n))
        ]

        for nodo in nodos_grafo:
            if nodo in nodos_vistos:
                continue
            nodos_vistos.add(nodo)

            # Sucesores directos
            for sucesor in G.successors(nodo):
                datos = G.get_edge_data(nodo, sucesor)
                rel = datos.get("relacion", "CONECTA_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {nodo} --[{rel}]--> {sucesor} (Contexto: {ctx})")

                match = re.search(r"\b(\d+(?:\.\d+)+)\b", str(sucesor))
                if match:
                    id_ref = match.group(1)
                    if id_ref in mapa_textos:
                        texto_ref = mapa_textos[id_ref]["texto"]
                        contexto.append(f"  [TEXTO RECUPERADO DE {sucesor}]:\n{texto_ref}\n")

            # Predecesores directos
            for predecesor in G.predecessors(nodo):
                datos = G.get_edge_data(predecesor, nodo)
                rel = datos.get("relacion", "CONECTA_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {predecesor} --[{rel}]--> {nodo} (Contexto: {ctx})")

    return "\n".join(contexto) if contexto else "No hay relaciones en el grafo para esta sección."


def generar_imagen_grafo(G: Optional[nx.DiGraph], max_nodos: int = 80) -> Optional[bytes]:
    """
    Genera una imagen PNG del grafo de conocimiento y la devuelve como bytes.

    Usa el backend Agg de matplotlib (sin GUI) para compatibilidad con Cloud Run.
    Si el grafo tiene más de max_nodos nodos, dibuja solo los más conectados.

    Returns:
        bytes PNG si el grafo tiene nodos, None si el grafo es None o vacío.
    """
    if G is None or G.number_of_nodes() == 0:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")  # Backend sin GUI, compatible con Cloud Run
        import matplotlib.pyplot as plt

        # Si hay demasiados nodos, filtrar a los más conectados
        if G.number_of_nodes() > max_nodos:
            grado = dict(G.degree())
            top_nodos = sorted(grado, key=grado.get, reverse=True)[:max_nodos]
            G = G.subgraph(top_nodos)

        fig, ax = plt.subplots(figsize=(18, 12))

        # Layout jerárquico si es un DAG, de lo contrario spring
        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=2.5)

        # Colorear nodos por tipo
        colores = []
        for nodo in G.nodes():
            tipo = G.nodes[nodo].get("tipo", "")
            if tipo == "CAPITULO":
                colores.append("#4A90D9")
            elif tipo == "ANEXO":
                colores.append("#E67E22")
            else:
                colores.append("#95A5A6")

        nx.draw_networkx(
            G,
            pos=pos,
            ax=ax,
            node_color=colores,
            node_size=800,
            font_size=6,
            arrows=True,
            arrowsize=12,
            edge_color="#AAAAAA",
            width=0.8,
        )

        # Etiquetas de aristas (relaciones)
        edge_labels = {(u, v): d.get("relacion", "") for u, v, d in G.edges(data=True)}
        nx.draw_networkx_edge_labels(
            G, pos=pos, edge_labels=edge_labels,
            font_size=5, ax=ax,
        )

        ax.set_title(
            f"Grafo de Conocimiento ContractIA — "
            f"{G.number_of_nodes()} nodos, {G.number_of_edges()} relaciones",
            fontsize=12,
        )
        ax.axis("off")
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        print(f"⚠️ No se pudo generar imagen del grafo: {e}")
        return None
