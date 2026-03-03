"""
Carga de documentos PDF y DOCX desde una carpeta.
Soporta PDFs con texto embebido y PDFs escaneados (OCR automático).
"""

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document


def _get_pdf_page_count(archivo: Path) -> int:
    """Devuelve el número de páginas de un PDF usando pypdf (sin cargar el texto)."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(archivo)).pages)
    except Exception:
        return 0


def _load_pdf(
    archivo: Path,
    ocr_progress: Optional[Callable[[int, str], None]] = None,
) -> List[Document]:
    """
    Carga un PDF. Si no tiene capa de texto (PDF escaneado),
    aplica OCR con Tesseract automáticamente, página a página.

    Args:
        ocr_progress: callback(pct: int, msg: str) llamado por cada página
                      durante el OCR para actualizar el progreso en tiempo real.
    """
    # Intento 1: PyPDFLoader (rápido, sin dependencias extra)
    try:
        loader = PyPDFLoader(str(archivo))
        docs = loader.load()
        texto_total = "".join(d.page_content.strip() for d in docs)
        if texto_total:
            return docs
    except Exception as e:
        print(f"  ⚠️ PyPDFLoader falló: {e}")

    # Intento 2: OCR con Tesseract (para PDFs escaneados / sin texto)
    n_pages = _get_pdf_page_count(archivo)
    total_str = f"/{n_pages}" if n_pages > 0 else ""
    print(f"  → Sin texto embebido en {archivo.name}, aplicando OCR ({n_pages} páginas)...")

    try:
        from pdf2image import convert_from_path
        import pytesseract

        ocr_docs: List[Document] = []

        if n_pages > 0:
            # Procesar página a página: menos memoria y progreso en tiempo real
            for i in range(1, n_pages + 1):
                if ocr_progress:
                    # Progreso de 10% a 25% durante la fase OCR
                    pct = 10 + int((i / n_pages) * 15)
                    ocr_progress(pct, f"OCR página {i}{total_str}…")

                try:
                    imagenes = convert_from_path(
                        str(archivo), dpi=150, first_page=i, last_page=i
                    )
                    if imagenes:
                        texto = pytesseract.image_to_string(imagenes[0], lang="spa+eng")
                        if texto.strip():
                            ocr_docs.append(Document(
                                page_content=texto,
                                metadata={"source": str(archivo), "page": i - 1},
                            ))
                except Exception as e:
                    print(f"  ⚠️ OCR falló en página {i}: {e}")
        else:
            # Fallback: procesar todo de una vez si no se pudo obtener el n.º de páginas
            imagenes = convert_from_path(str(archivo), dpi=150)
            total = len(imagenes)
            for i, img in enumerate(imagenes, start=1):
                if ocr_progress:
                    pct = 10 + int((i / total) * 15)
                    ocr_progress(pct, f"OCR página {i}/{total}…")
                try:
                    texto = pytesseract.image_to_string(img, lang="spa+eng")
                    if texto.strip():
                        ocr_docs.append(Document(
                            page_content=texto,
                            metadata={"source": str(archivo), "page": i - 1},
                        ))
                except Exception as e:
                    print(f"  ⚠️ OCR falló en página {i}: {e}")

        if ocr_docs:
            print(f"  ✅ OCR extrajo texto de {len(ocr_docs)} página(s).")
            return ocr_docs
        print(f"  ⚠️ OCR no encontró texto en {archivo.name}.")
    except Exception as e:
        print(f"  ⚠️ OCR falló para {archivo.name}: {e}")

    return []


def procesar_documentos_carpeta(
    folder_path: str | Path,
    ocr_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[Optional[List[Document]], Optional[str]]:
    """
    Lee todos los PDF y DOCX de una carpeta y devuelve:
      - Lista de objetos Document (LangChain)
      - Texto concatenado completo

    Args:
        ocr_progress: callback(pct, msg) que se pasa a _load_pdf para
                      reportar progreso página a página durante el OCR.
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
