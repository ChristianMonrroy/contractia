"""
Construcción y consulta del grafo de conocimiento (GraphRAG).

Extrae tripletas (entidad, relación, entidad) de cada sección del contrato
usando el LLM, y construye un DiGraph de networkx. El grafo permite a los
agentes navegar relaciones entre cláusulas, leyes y plazos.
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
        "Eres un experto en extracción de datos legales. Analiza el siguiente texto "
        "de un contrato y extrae las relaciones en formato de tripletas.\n\n"
        "Entidades válidas: Cláusulas (ej. 'Cláusula 5.1'), Leyes/Normas (ej. 'Ley 30225'), "
        "Plazos (ej. '15 días hábiles'), Roles (ej. 'Contratista').\n"
        "Relaciones válidas: REFERENCIA_A, SE_RIGE_POR, ESTABLECE_PLAZO, MODIFICA_A, DEPENDE_DE.\n\n"
        "Responde SOLO con un JSON que sea una lista de diccionarios con este formato exacto:\n"
        "[\n"
        "  {{\"origen\": \"Cláusula 5.1\", \"relacion\": \"REFERENCIA_A\", "
        "\"destino\": \"Cláusula 8.2\", \"contexto\": \"Para el pago de penalidades\"}},\n"
        "  {{\"origen\": \"Cláusula 2\", \"relacion\": \"SE_RIGE_POR\", "
        "\"destino\": \"Código Civil\", \"contexto\": \"Marco legal supletorio\"}}\n"
        "]\n\n"
        "Si no hay relaciones relevantes, responde con una lista vacía: []\n\n"
        "Texto de la sección:\n{texto}\n"
    ),
    input_variables=["texto"],
)


def construir_grafo_conocimiento(secciones: List[Dict], llm) -> nx.DiGraph:
    """
    Construye un grafo de conocimiento a partir de las secciones del contrato.

    Por cada sección:
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

        try:
            raw = cadena.invoke({"texto": contenido[:3000]})  # Límite de tokens
            tripletas = parse_json_seguro(raw)

            if isinstance(tripletas, list):
                for t in tripletas:
                    if not isinstance(t, dict):
                        continue
                    origen = t.get("origen", "")
                    destino = t.get("destino", "")
                    relacion = t.get("relacion", "")
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

    Para cada cláusula de la sección, busca nodos del grafo que la contengan
    y devuelve sus sucesores y predecesores con sus relaciones. Si el sucesor
    es una cláusula referenciada, añade un extracto de su texto.

    Returns:
        String con las relaciones encontradas, o mensaje indicando ausencia.
    """
    if G is None or G.number_of_nodes() == 0:
        return "No hay relaciones en el grafo para esta sección."

    contexto = []
    nodos_vistos: set = set()

    for cid in clausulas_locales:
        nodos_grafo = [n for n in G.nodes() if cid in str(n)]

        for nodo in nodos_grafo:
            if nodo in nodos_vistos:
                continue
            nodos_vistos.add(nodo)

            # Sucesores (lo que esta cláusula referencia)
            for sucesor in G.successors(nodo):
                datos = G.get_edge_data(nodo, sucesor) or {}
                rel = datos.get("relacion", "RELACIONADO_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {nodo} --[{rel}]--> {sucesor} (Contexto: {ctx})")

                # Si el sucesor es una cláusula conocida, añadir su texto
                match = re.search(r"\b(\d+(?:\.\d+)+)\b", str(sucesor))
                if match:
                    id_ref = match.group(1)
                    if id_ref in mapa_textos:
                        texto_ref = mapa_textos[id_ref].get("texto", "")[:500]
                        contexto.append(f"  [TEXTO DE {sucesor}]: {texto_ref}...")

            # Predecesores (qué cláusulas referencian a esta)
            for predecesor in G.predecessors(nodo):
                datos = G.get_edge_data(predecesor, nodo) or {}
                rel = datos.get("relacion", "RELACIONADO_CON")
                ctx = datos.get("contexto", "")
                contexto.append(f"- {predecesor} --[{rel}]--> {nodo} (Contexto: {ctx})")

    return "\n".join(contexto) if contexto else "No hay relaciones en el grafo para esta sección."
