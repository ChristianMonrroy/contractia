"""
Carga de documentos PDF y DOCX desde una carpeta.
Soporta PDFs con texto embebido y PDFs escaneados (OCR automático).
"""

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from langchain_community.document_loaders import Docx2txtLoader
from langchain_core.documents import Document


def _load_pdf(
    archivo: Path,
    ocr_progress: Optional[Callable[[int, str], None]] = None,
) -> List[Document]:
    """
    Carga un PDF página a página, reportando progreso en tiempo real.

    Fase 1 — texto embebido (pypdf): muestra "Leyendo página X/N…"
    Fase 2 — OCR con Tesseract si no hay texto: muestra "OCR página X/N…"

    El rango de porcentaje usado es 10 % → 25 % (dentro de _run_audit).
    """
    # ── Obtener número de páginas ──
    n_pages = 0
    try:
        from pypdf import PdfReader as _PdfReader
        _r = _PdfReader(str(archivo))
        n_pages = len(_r.pages)
    except Exception:
        pass

    # ── Fase 1: lectura con pypdf, página a página ──
    docs_embebidos: List[Document] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(archivo))
        n = len(reader.pages)

        for i, page in enumerate(reader.pages):
            if ocr_progress and n > 0:
                pct = 10 + int(((i + 1) / n) * 15)  # 10 % → 25 %
                ocr_progress(pct, f"Leyendo página {i + 1}/{n}…")

            texto = page.extract_text() or ""
            if texto.strip():
                docs_embebidos.append(Document(
                    page_content=texto,
                    metadata={"source": str(archivo), "page": i},
                ))

        if docs_embebidos:
            return docs_embebidos

    except Exception as e:
        print(f"  ⚠️ pypdf falló: {e}")

    # ── Fase 2: OCR con Tesseract (PDF escaneado / sin texto embebido) ──
    print(f"  → Sin texto embebido en {archivo.name}, aplicando OCR ({n_pages} páginas)...")
    try:
        from pdf2image import convert_from_path
        import pytesseract

        ocr_docs: List[Document] = []

        if n_pages > 0:
            for i in range(1, n_pages + 1):
                if ocr_progress:
                    pct = 10 + int((i / n_pages) * 15)
                    ocr_progress(pct, f"OCR página {i}/{n_pages}…")

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
            # Fallback: procesar todas las páginas a la vez
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
        ocr_progress: callback(pct, msg) que se llama por cada página
                      del PDF (tanto texto embebido como OCR).
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
