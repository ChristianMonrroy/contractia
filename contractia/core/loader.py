"""
Carga de documentos PDF y DOCX desde una carpeta.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document


def procesar_documentos_carpeta(
    folder_path: str | Path,
) -> Tuple[Optional[List[Document]], Optional[str]]:
    """
    Lee todos los PDF y DOCX de una carpeta y devuelve:
      - Lista de objetos Document (LangChain)
      - Texto concatenado completo
    """
    folder = Path(folder_path)
    if not folder.exists():
        print(f"⚠️ La carpeta '{folder}' no existe.")
        return None, None

    archivos = list(folder.iterdir())
    if not archivos:
        print(f"⚠️ La carpeta '{folder}' está vacía.")
        return None, None

    documentos: List[Document] = []
    partes_texto: List[str] = []

    print(f"📂 Procesando carpeta: {folder}")
    for archivo in sorted(archivos):
        if not archivo.is_file():
            continue

        ext = archivo.suffix.lower()
        print(f"  → Cargando: {archivo.name}")

        try:
            if ext == ".pdf":
                loader = PyPDFLoader(str(archivo))
            elif ext == ".docx":
                loader = Docx2txtLoader(str(archivo))
            else:
                continue

            docs = loader.load()
            documentos.extend(docs)
            partes_texto.extend(doc.page_content for doc in docs)
        except Exception as e:
            print(f"  ⚠️ No se pudo cargar {archivo.name}: {e}")

    if not documentos:
        return None, None

    texto_completo = "\n\n".join(partes_texto)
    print(f"  ✅ {len(documentos)} documentos cargados ({len(texto_completo):,} caracteres).")
    return documentos, texto_completo
