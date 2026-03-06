"""
Construcción y consulta del grafo de conocimiento (GraphRAG).

Extrae tripletas (entidad, relación, entidad) de cada sección del contrato
usando el LLM, y construye un DiGraph de networkx. El grafo permite a los
agentes navegar relaciones entre cláusulas, leyes y plazos.

Mejoras v8.6.0:
- Prompt de extracción con CoT + Few-Shot (mismo estilo que los agentes)
- Búsqueda de nodos por regex con word-boundary (evita "5" matchando "15", "25")
- Profundidad 2 en la consulta del grafo (ego_graph radius=2)
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
        "Eres un experto en análisis estructural de contratos legales peruanos. "
        "Tu tarea es extraer relaciones explícitas entre entidades del texto dado.\n\n"

        "ENTIDADES VÁLIDAS:\n"
        "- Cláusulas/numerales: 'Cláusula 5', 'numeral 3.2', 'literal a) del artículo 8'\n"
        "- Leyes y normas: 'Ley 30225', 'D.S. 344-2018-EF', 'Código Civil'\n"
        "- Plazos: '15 días hábiles', '30 días calendario'\n"
        "- Roles: 'Contratista', 'Entidad', 'Supervisor'\n\n"

        "RELACIONES VÁLIDAS (elige SOLO una por tripleta):\n"
        "- REFERENCIA_A: una cláusula cita explícitamente a otra\n"
        "- SE_RIGE_POR: una cláusula se subordina a una ley o norma externa\n"
        "- ESTABLECE_PLAZO: una cláusula define un plazo concreto\n"
        "- MODIFICA_A: una cláusula altera o complementa a otra\n"
        "- DEPENDE_DE: una obligación está condicionada a otra\n\n"

        "EJEMPLO (few-shot):\n"
        "Texto: 'El Contratista deberá cumplir lo señalado en la Cláusula 8.2 "
        "dentro de los 15 días hábiles siguientes a la notificación. "
        "Este plazo se rige por el D.S. 344-2018-EF.'\n"
        "Extracción correcta:\n"
        "[\n"
        "  {\"origen\": \"Cláusula actual\", \"relacion\": \"REFERENCIA_A\", "
        "\"destino\": \"Cláusula 8.2\", \"contexto\": \"obligación de cumplimiento\"},\n"
        "  {\"origen\": \"Cláusula actual\", \"relacion\": \"ESTABLECE_PLAZO\", "
        "\"destino\": \"15 días hábiles\", \"contexto\": \"plazo desde notificación\"},\n"
        "  {\"origen\": \"Cláusula actual\", \"relacion\": \"SE_RIGE_POR\", "
        "\"destino\": \"D.S. 344-2018-EF\", \"contexto\": \"marco normativo del plazo\"}\n"
        "]\n\n"

        "PROCESO (sigue estos pasos):\n"
        "<razonamiento>\n"
        "1. Identifica todas las entidades mencionadas en el texto.\n"
        "2. Para cada par de entidades, determina si existe una relación explícita.\n"
        "3. Elige la relación más específica de las 5 válidas.\n"
        "4. Descarta relaciones implícitas o inferidas — solo lo que dice el texto.\n"
        "5. Si no hay relaciones claras, devuelve [].\n"
        "</razonamiento>\n\n"

        "Responde SOLO con JSON válido (lista de tripletas o lista vacía []).\n\n"
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
            # Eliminar bloque <razonamiento> antes de parsear
            raw_limpio = re.sub(r"<razonamiento>.*?</razonamiento>", "", raw, flags=re.DOTALL).strip()
            tripletas = parse_json_seguro(raw_limpio)

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


def _normalizar_id(cid: str) -> str:
    """Normaliza un ID de cláusula para búsqueda: strip + lowercase."""
    return cid.strip().lower()


def _nodos_matching(G: nx.DiGraph, cid: str) -> List[str]:
    """
    Busca nodos del grafo que correspondan al ID de cláusula dado.
    Usa regex con word-boundary para evitar que "5" matchee "5.1", "15" o "25".
    """
    # Escapa el cid para usarlo en regex (ej. "5.1" → "5\\.1")
    patron = re.compile(r"(?<!\d)" + re.escape(cid) + r"(?!\d)", re.IGNORECASE)
    return [n for n in G.nodes() if patron.search(str(n))]


def obtener_contexto_grafo(
    clausulas_locales: List[str],
    G: nx.DiGraph,
    mapa_textos: Dict[str, Dict],
    profundidad: int = 2,
) -> str:
    """
    Recupera el contexto del grafo relevante para una sección.

    Para cada cláusula de la sección, obtiene un ego-grafo de profundidad
    `profundidad` (default=2) y devuelve todas las relaciones encontradas.
    Si el nodo destino es una cláusula conocida, añade un extracto de su texto.

    Returns:
        String con las relaciones encontradas, o mensaje indicando ausencia.
    """
    if G is None or G.number_of_nodes() == 0:
        return "No hay relaciones en el grafo para esta sección."

    contexto = []
    aristas_vistas: set = set()

    for cid in clausulas_locales:
        nodos_grafo = _nodos_matching(G, cid)

        for nodo_raiz in nodos_grafo:
            # Ego-grafo de profundidad 2: incluye vecinos directos e indirectos
            try:
                subgrafo = nx.ego_graph(G, nodo_raiz, radius=profundidad, undirected=False)
            except Exception:
                subgrafo = G  # Fallback a grafo completo si falla

            for origen, destino, datos in subgrafo.edges(data=True):
                arista_key = (origen, destino)
                if arista_key in aristas_vistas:
                    continue
                aristas_vistas.add(arista_key)

                rel = datos.get("relacion", "RELACIONADO_CON")
                ctx = datos.get("contexto", "")

                # Omitir aristas jerárquicas CONTIENE en el contexto (ruido)
                if rel == "CONTIENE":
                    continue

                contexto.append(f"- {origen} --[{rel}]--> {destino} (Contexto: {ctx})")

                # Si el destino es una cláusula conocida, añadir su texto
                match = re.search(r"\b(\d+(?:\.\d+)+)\b", str(destino))
                if match:
                    id_ref = match.group(1)
                    if id_ref in mapa_textos:
                        texto_ref = mapa_textos[id_ref].get("texto", "")[:500]
                        contexto.append(f"  [TEXTO DE {destino}]: {texto_ref}...")

    return "\n".join(contexto) if contexto else "No hay relaciones en el grafo para esta sección."
