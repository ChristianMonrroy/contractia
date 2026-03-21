"""
Carga de documentos PDF y DOCX desde una carpeta.
Usa PyPDFLoader (idéntico al notebook vs18) para extracción de texto.
"""

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document


def _load_pdf(
    archivo: Path,
    ocr_progress: Optional[Callable[[int, str], None]] = None,
) -> List[Document]:
    """
    Carga un PDF usando PyPDFLoader (misma librería que el notebook vs18).

    Esto garantiza que el texto extraído sea idéntico al del notebook,
    produciendo grafos GraphRAG con el mismo número de nodos/relaciones.
    """
    loader = PyPDFLoader(str(archivo))
    docs = loader.load()

    # Reportar progreso si hay callback
    if ocr_progress:
        n = len(docs)
        for i in range(n):
            pct = 10 + int(((i + 1) / n) * 15)  # 10 % → 25 %
            ocr_progress(pct, f"Leyendo página {i + 1}/{n}…")

    return docs


def procesar_documentos_carpeta(
    folder_path: str | Path,
    ocr_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[Optional[List[Document]], Optional[str]]:
    """
    Lee todos los PDF y DOCX de una carpeta y devuelve:
      - Lista de objetos Document (LangChain)
      - Texto concatenado completo

    Args:
        ocr_progress: callback(pct, msg) que se llama por cada página
                      del PDF para reportar progreso.
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
                docs = _load_pdf(archivo, ocr_progress=ocr_progress)
            elif ext == ".docx":
                loader = Docx2txtLoader(str(archivo))
                docs = loader.load()
            else:
                continue

            documentos.extend(docs)
            partes_texto.extend(doc.page_content for doc in docs)
        except Exception as e:
            print(f"  ⚠️ No se pudo cargar {archivo.name}: {e}")

    if not documentos:
        return None, None

    texto_completo = "\n\n".join(partes_texto)
    print(f"  ✅ {len(documentos)} documentos cargados ({len(texto_completo):,} caracteres).")
    return documentos, texto_completo
