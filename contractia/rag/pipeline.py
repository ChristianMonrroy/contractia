"""
Pipeline RAG: vectorización del contrato y recuperación por similitud.

Flujo completo (Hybrid RAG + Reranking desde v8.8.0):
  Documento → Chunks → Embeddings → FAISS  ┐
                     → BM25 (rank_bm25)    ┘→ EnsembleRetriever (RRF, top-20)
                                                        ↓
                                          Cohere rerank-multilingual-v3.0
                                                        ↓
                                                  top-K chunks finales
                                                        ↓
                                                     Agentes

- BM25 captura keywords legales exactos ("Ley 30225", "D.S. 344-2018-EF").
- FAISS captura similitud semántica.
- Cohere reranker ordena los 20 candidatos por relevancia real contra la consulta.
- Si COHERE_API_KEY no está configurada, usa EnsembleRetriever sin reranking.

Proveedores de embeddings soportados (según LLM_PROVIDER en .env):
  - vertexai : VertexAIEmbeddings  (text-embedding-004)
  - ollama   : OllamaEmbeddings    (nomic-embed-text)
"""

from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm.auto import tqdm

from contractia.config import (
    COHERE_API_KEY,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_EMBEDDING_MODEL,
    RAG_TOP_K,
    VERTEXAI_EMBEDDING_MODEL,
    VERTEXAI_LOCATION,
    VERTEXAI_PROJECT,
)


def _build_text_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=RAG_CHUNK_SIZE,
        chunk_overlap=RAG_CHUNK_OVERLAP,
        separators=[
            "\nCAPÍTULO", "\nANEXO", "\nSECCIÓN",
            "\nArtículo", "\nCláusula",
            "\n\n", "\n", ". ", " ",
        ],
        length_function=len,
        is_separator_regex=False,
    )


def crear_vector_store(texto_contrato: str, secciones: Optional[List[Dict]] = None):
    """
    Crea un FAISS vector store a partir del texto del contrato.

    Si se proporcionan secciones del motor regex, las usa como base
    (con metadata enriquecida). Si no, divide el texto plano.

    Returns:
        FAISS vector store
    """
    from langchain_community.vectorstores import FAISS

    if LLM_PROVIDER == "vertexai":
        from langchain_google_vertexai import VertexAIEmbeddings
        embeddings = VertexAIEmbeddings(
            model_name=VERTEXAI_EMBEDDING_MODEL,
            project=VERTEXAI_PROJECT,
            location=VERTEXAI_LOCATION,
        )
        modelo_label = VERTEXAI_EMBEDDING_MODEL
    else:
        from langchain_ollama import OllamaEmbeddings
        embeddings = OllamaEmbeddings(model=RAG_EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
        modelo_label = RAG_EMBEDDING_MODEL

    print("🔍 Creando base de conocimiento vectorial (RAG)...")
    splitter = _build_text_splitter()
    documentos: List[Document] = []

    if secciones:
        print(f"   📄 Procesando {len(secciones)} secciones del contrato...")
        for sec in secciones:
            contenido = sec.get("contenido", "")
            if not contenido.strip():
                continue

            metadata = {
                "titulo": sec.get("titulo", "Sin título"),
                "tipo": sec.get("tipo", "desconocido"),
                "numero": sec.get("n", ""),
                "source": f"{sec.get('tipo', '')} {sec.get('n', '')} - {sec.get('titulo', '')}",
            }

            if len(contenido) <= RAG_CHUNK_SIZE + 300:
                documentos.append(Document(page_content=contenido, metadata=metadata))
            else:
                chunks = splitter.split_text(contenido)
                for i, chunk in enumerate(chunks):
                    chunk_meta = {**metadata, "chunk_index": i, "total_chunks": len(chunks)}
                    documentos.append(Document(page_content=chunk, metadata=chunk_meta))
    else:
        print("   📄 Dividiendo texto plano en fragmentos...")
        chunks = splitter.split_text(texto_contrato)
        for i, chunk in enumerate(chunks):
            documentos.append(
                Document(page_content=chunk, metadata={"source": f"chunk_{i}", "chunk_index": i})
            )

    print(f"   📦 Total de fragmentos: {len(documentos)}")
    print(f"   🧮 Generando embeddings con '{modelo_label}'...")

    # VertexAI text-embedding-004 acepta hasta 20k tokens por batch;
    # con chunks de ~1800 chars → máximo ~10 docs seguros por llamada.
    batch_size = 10 if LLM_PROVIDER == "vertexai" else 50
    vector_store = None

    for i in tqdm(range(0, len(documentos), batch_size), desc="   Vectorizando"):
        batch = documentos[i : i + batch_size]
        if vector_store is None:
            vector_store = FAISS.from_documents(batch, embeddings)
        else:
            vector_store.add_documents(batch)

    print(f"   ✅ Vector store FAISS creado ({len(documentos)} fragmentos).")

    # Guardar los documentos en el objeto para que crear_retriever
    # pueda construir el índice BM25 sin cambiar la firma de los callers.
    vector_store._contractia_docs = documentos

    return vector_store


def crear_retriever(vector_store, k: int = None):
    """
    Crea el retriever completo con tres capas opcionales:

    1. FAISS (siempre activo): búsqueda semántica por embeddings.
    2. BM25 + EnsembleRetriever (si rank_bm25 está instalado):
       recupera más candidatos (k×5, máx 20) combinando búsqueda
       exacta (BM25) y semántica (FAISS) con RRF.
    3. Cohere Reranker (si COHERE_API_KEY está configurada):
       ordena los candidatos por relevancia real y devuelve top-k.

    Degradación silenciosa: si alguna capa no está disponible,
    usa la anterior como fallback. La auditoría nunca se interrumpe.
    """
    k = k or RAG_TOP_K
    # Capa 2 y 3 recuperan más candidatos para que el reranker tenga más para elegir
    k_candidatos = min(k * 5, 20)

    faiss_retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k_candidatos},
    )

    # ── Capa 2: Hybrid RAG (BM25 + FAISS) ────────────────────────────────────
    base_retriever = faiss_retriever
    docs = getattr(vector_store, "_contractia_docs", None)
    if docs:
        try:
            from langchain_community.retrievers import BM25Retriever
            from langchain.retrievers import EnsembleRetriever

            bm25_retriever = BM25Retriever.from_documents(docs, k=k_candidatos)
            base_retriever = EnsembleRetriever(
                retrievers=[bm25_retriever, faiss_retriever],
                weights=[0.4, 0.6],
            )
            print(f"   🔀 Hybrid RAG: BM25 + FAISS ({k_candidatos} candidatos)")
        except ImportError:
            print("   ⚠️ rank_bm25 no instalado — usando solo FAISS.")
        except Exception as e:
            print(f"   ⚠️ Hybrid RAG no disponible ({e}) — usando solo FAISS.")

    # ── Capa 3: Cohere Reranker ───────────────────────────────────────────────
    if COHERE_API_KEY:
        try:
            from langchain_cohere import CohereRerank
            from langchain.retrievers import ContextualCompressionRetriever

            reranker = CohereRerank(
                cohere_api_key=COHERE_API_KEY,
                model="rerank-multilingual-v3.0",
                top_n=k,
            )
            print(f"   🎯 Reranker Cohere activo: top {k_candidatos} → top {k}")
            return ContextualCompressionRetriever(
                base_compressor=reranker,
                base_retriever=base_retriever,
            )
        except ImportError:
            print("   ⚠️ langchain-cohere no instalado — usando retriever sin reranking.")
        except Exception as e:
            print(f"   ⚠️ Reranker Cohere no disponible ({e}) — usando retriever sin reranking.")
    else:
        print("   ℹ️ COHERE_API_KEY no configurada — sin reranking (solo Hybrid RAG).")

    return base_retriever


def recuperar_contexto(retriever, consulta: str, max_tokens: int = 2000) -> str:
    """
    Recupera fragmentos relevantes del contrato para una consulta.
    Llamada por los agentes antes de analizar una sección.
    """
    try:
        docs = retriever.invoke(consulta)
        partes = []
        total_chars = 0

        for doc in docs:
            source = doc.metadata.get("source", "")
            texto = doc.page_content

            if total_chars + len(texto) > max_tokens * 4:
                break

            bloque = f"[Fuente: {source}]\n{texto}"
            partes.append(bloque)
            total_chars += len(bloque)

        return "\n\n---\n\n".join(partes) if partes else ""
    except Exception as e:
        print(f"   ⚠️ Error en RAG retrieval: {e}")
        return ""


def buscar_clausula(vector_store, numero_clausula: str) -> str:
    """Busca el texto de una cláusula específica por número."""
    try:
        resultados = vector_store.similarity_search(f"Cláusula {numero_clausula}", k=2)
        for doc in resultados:
            if numero_clausula in doc.page_content:
                return doc.page_content
        return resultados[0].page_content if resultados else ""
    except Exception:
        return ""
