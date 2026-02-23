"""
ContractIA — Modo consulta interactiva al contrato via RAG.

Uso:
    python query.py
    python query.py --contracts-dir ./docs
    python query.py --top-k 5
"""

import argparse

from contractia.config import CONTRACTS_DIR, RAG_TOP_K
from contractia.core.loader import procesar_documentos_carpeta
from contractia.llm.provider import build_llm
from contractia.rag.pipeline import crear_retriever, crear_vector_store, recuperar_contexto

PROMPT_TEMPLATE = """\
Eres un asistente legal especializado en contratos de concesión. \
Responde la pregunta basándote ÚNICAMENTE en el contexto del contrato que se te proporciona. \
Si la respuesta no está en el contexto, dilo claramente.

CONTEXTO DEL CONTRATO:
{contexto}

PREGUNTA: {pregunta}

RESPUESTA:"""


def parse_args():
    parser = argparse.ArgumentParser(description="ContractIA — Consulta interactiva al contrato")
    parser.add_argument("--contracts-dir", default=None, help="Carpeta con los documentos del contrato")
    parser.add_argument("--top-k", type=int, default=RAG_TOP_K, help="Número de fragmentos a recuperar")
    return parser.parse_args()


def main():
    args = parse_args()
    contracts_dir = args.contracts_dir or CONTRACTS_DIR

    print("=" * 60)
    print("  ContractIA — Consulta interactiva al contrato")
    print("=" * 60)

    # Cargar LLM
    try:
        llm = build_llm()
    except Exception as e:
        print(f"🔴 No se pudo inicializar el LLM: {e}")
        return

    # Cargar documentos
    print(f"\n📂 Cargando contrato desde: {contracts_dir}")
    try:
        _, texto_contrato = procesar_documentos_carpeta(contracts_dir)
    except Exception as e:
        print(f"🔴 Error leyendo documentos: {e}")
        return

    if not texto_contrato:
        print("🔴 No se encontraron documentos. Abortando.")
        return

    # Construir vector store RAG
    print("\n📚 Construyendo base de conocimiento RAG...")
    try:
        vector_store = crear_vector_store(texto_contrato)
        retriever = crear_retriever(vector_store, k=args.top_k)
        print(f"✅ RAG listo. Recuperando los {args.top_k} fragmentos más relevantes por consulta.\n")
    except Exception as e:
        print(f"🔴 No se pudo construir el RAG: {e}")
        return

    # Bucle de consultas
    print("Escribe tu pregunta sobre el contrato (o 'salir' para terminar).")
    print("-" * 60)

    while True:
        try:
            pregunta = input("\n🔎 Pregunta: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSaliendo...")
            break

        if not pregunta:
            continue
        if pregunta.lower() in ("salir", "exit", "quit", "q"):
            print("Hasta luego.")
            break

        contexto = recuperar_contexto(retriever, pregunta, max_tokens=3000)
        if not contexto:
            print("⚠️  No se encontraron fragmentos relevantes para esa consulta.")
            continue

        prompt = PROMPT_TEMPLATE.format(contexto=contexto, pregunta=pregunta)

        try:
            respuesta = llm.invoke(prompt)
            # Extraer texto si es un objeto AIMessage
            texto = respuesta.content if hasattr(respuesta, "content") else str(respuesta)
            print(f"\n💬 Respuesta:\n{texto}")
        except Exception as e:
            print(f"⚠️  Error al consultar el LLM: {e}")


if __name__ == "__main__":
    main()
