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

import re
import time
from typing import Dict, List

import networkx as nx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from contractia.agents.base import parse_json_seguro

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


def construir_grafo_conocimiento(secciones: List[Dict], llm) -> nx.DiGraph:
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
    G = nx.DiGraph()
    try:
        cadena = _PROMPT_EXTRACCION | llm | StrOutputParser()
    except Exception as e:
        print(f"⚠️ No se pudo construir la cadena GraphRAG: {e}")
        return G  # Grafo vacío; la auditoría continuará sin GraphRAG

    for sec in secciones:
        titulo = sec.get("titulo", "Sección Desconocida")
        contenido = sec.get("contenido", "")
        if not contenido.strip():
            continue

        # Forzar la creación del nodo del Capítulo/Anexo
        G.add_node(titulo, tipo=sec.get("tipo", "DESCONOCIDO"))

        try:
            raw = cadena.invoke({"texto": contenido})
            tripletas = parse_json_seguro(raw)

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

            time.sleep(1)  # Rate limit VertexAI

        except Exception as e:
            print(f"⚠️ Error extrayendo grafo en sección '{titulo}': {e}")

    print(
        f"✅ Grafo construido: {G.number_of_nodes()} nodos, "
        f"{G.number_of_edges()} relaciones."
    )
    return G


def obtener_contexto_grafo(
    clausulas_locales: List[str],
    G: nx.DiGraph,
    mapa_textos: Dict[str, Dict],
) -> str:
    """
    Recupera el contexto del grafo relevante para una sección.

    Para cada cláusula de la sección recorre sucesores y predecesores directos
    (profundidad 1), igual que el notebook vs14. Si el destino es una cláusula
    conocida, añade un extracto de su texto hasta el inicio de la siguiente cláusula.

    Returns:
        String con las relaciones encontradas, o mensaje indicando ausencia.
    """
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
                rel = datos.get("relacion", "RELACIONADO_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {nodo} --[{rel}]--> {sucesor} (Contexto: {ctx})")

                # Si el destino es una cláusula conocida, añadir su texto
                match = re.search(r"\b(\d+(?:\.\d+)+)\b", str(sucesor))
                if match:
                    id_ref = match.group(1)
                    if id_ref in mapa_textos:
                        texto_completo = mapa_textos[id_ref].get("texto", "")
                        match_pos = re.search(rf"\b{re.escape(id_ref)}\b", texto_completo)
                        if match_pos:
                            inicio = match_pos.start()
                            texto_restante = texto_completo[inicio + len(id_ref):]
                            siguiente = re.search(
                                r"\n\s*(?:CL[AÁ]USULA\s+|ART[IÍ]CULO\s+)?\d+\.\d+\b",
                                texto_restante,
                                re.IGNORECASE,
                            )
                            if siguiente:
                                fin = inicio + len(id_ref) + siguiente.start()
                                texto_ref = texto_completo[inicio:fin].strip()
                            else:
                                texto_ref = texto_completo[inicio:inicio + 4000].strip()
                        else:
                            texto_ref = texto_completo[:4000]
                        contexto.append(f"  [TEXTO RECUPERADO DE {sucesor}]: ...{texto_ref}...")

            # Predecesores directos
            for predecesor in G.predecessors(nodo):
                datos = G.get_edge_data(predecesor, nodo)
                rel = datos.get("relacion", "RELACIONADO_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {predecesor} --[{rel}]--> {nodo} (Contexto: {ctx})")

    return "\n".join(contexto) if contexto else "No hay relaciones en el grafo para esta sección."
