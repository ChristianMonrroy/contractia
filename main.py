"""
ContractIA v6 — Punto de entrada principal.

Uso:
    python main.py                          # Usa configuración de .env
    python main.py --provider vertexai      # Fuerza Vertex AI
    python main.py --contracts-dir ./docs   # Carpeta personalizada
    python main.py --no-rag                 # Desactiva RAG
"""

import argparse
import time
import traceback

from contractia import __version__
from contractia.config import (
    CONTRACTS_DIR,
    LLM_PROVIDER,
    OUTPUT_DIR,
    RAG_ENABLED,
    REPORT_FILENAME,
)
from contractia.core.loader import procesar_documentos_carpeta
from contractia.core.report import render_auditoria_markdown, save_report
from contractia.llm.provider import build_llm
from contractia.orchestrator import ejecutar_auditoria_contrato


def parse_args():
    parser = argparse.ArgumentParser(description="ContractIA v6 — Auditoría Contractual Multi-Agente")
    parser.add_argument("--provider", choices=["ollama", "vertexai"], default=None,
                        help="Proveedor LLM (override de .env)")
    parser.add_argument("--contracts-dir", type=str, default=None,
                        help="Carpeta con los documentos del contrato")
    parser.add_argument("--no-rag", action="store_true",
                        help="Desactivar RAG")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Carpeta de salida para el informe")
    return parser.parse_args()


def main():
    args = parse_args()

    # Override config con argumentos CLI
    if args.provider:
        import contractia.config as cfg
        cfg.LLM_PROVIDER = args.provider
    if args.no_rag:
        import contractia.config as cfg
        cfg.RAG_ENABLED = False

    contracts_dir = args.contracts_dir or CONTRACTS_DIR
    output_dir = args.output_dir or OUTPUT_DIR

    print("=" * 60)
    print(f"  ContractIA v{__version__}")
    print(f"  Proveedor: {LLM_PROVIDER}")
    print(f"  RAG: {'Activado' if RAG_ENABLED and not args.no_rag else 'Desactivado'}")
    print(f"  Contratos: {contracts_dir}")
    print("=" * 60)
    print()

    # ── Paso 1: Construir LLM ──
    try:
        llm = build_llm()
    except Exception as e:
        print(f"🔴 No se pudo inicializar el LLM: {e}")
        return

    # ── Paso 2: Cargar documentos ──
    print("\n--- PASO 1: Procesando el Contrato a Auditar ---")
    try:
        docs, texto_contrato = procesar_documentos_carpeta(contracts_dir)
    except Exception as e:
        print(f"🔴 Error leyendo documentos: {e}")
        return

    if not texto_contrato:
        print("🔴 No se encontraron documentos en la carpeta. Abortando.")
        return

    # ── Paso 3: Ejecutar auditoría ──
    start_time = time.time()

    try:
        resultado = ejecutar_auditoria_contrato(
            texto_contrato=texto_contrato,
            llm=llm,
        )
    except Exception as e:
        print(f"🔴 Error en el pipeline de auditoría: {e}")
        traceback.print_exc()
        return

    elapsed = time.time() - start_time

    print("\n" + "=" * 50)
    print("AUDITORÍA COMPLETADA")
    print("=" * 50)
    print(f"⏱️  Tiempo total: {elapsed:.2f} segundos")
    print("=" * 50 + "\n")

    # ── Paso 4: Generar informe ──
    try:
        md = render_auditoria_markdown(resultado)
        md += f"\n\n---\n*Tiempo de ejecución del análisis: {elapsed:.2f} segundos.*"
        print(md)
    except Exception as e:
        print(f"⚠️ Error renderizando informe: {e}")
        md = "Error generando el informe."

    report_path = output_dir / REPORT_FILENAME if hasattr(output_dir, '__truediv__') else __import__('pathlib').Path(output_dir) / REPORT_FILENAME
    save_report(md, report_path)


if __name__ == "__main__":
    main()
