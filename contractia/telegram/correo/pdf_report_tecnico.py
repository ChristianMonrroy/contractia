"""
Generación del Informe Técnico de Auditoría (solo admins).

Incluye:
  - Fase 0: estructura del contrato (capítulos, anexos, cláusulas)
  - Fase 0.5: auditoría de secuencia de cláusulas
  - GraphRAG: nodos, aristas y representación visual del grafo
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import networkx as nx
from fpdf import FPDF

_NAVY   = (30, 58, 95)
_GRAY   = (71, 85, 105)
_LIGHT  = (203, 213, 225)
_GREEN  = (22, 163, 74)
_RED    = (220, 38, 38)
_ORANGE = (234, 88, 12)
FONT    = "Helvetica"

_NOMBRES_MODELO = {
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
}


def _safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _h1(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font(FONT, "B", 13)
    pdf.set_text_color(*_NAVY)
    pdf.multi_cell(0, 7, _safe(text))
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)
    pdf.set_text_color(15, 23, 42)


def _h2(pdf: FPDF, text: str) -> None:
    pdf.ln(2)
    pdf.set_font(FONT, "B", 11)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(0, 6, _safe(text))
    pdf.set_draw_color(*_LIGHT)
    pdf.set_line_width(0.3)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(15, 23, 42)


def _body(pdf: FPDF, text: str, size: int = 10) -> None:
    pdf.set_font(FONT, "", size)
    pdf.multi_cell(0, 5, _safe(text))


def _bullet(pdf: FPDF, text: str, color: tuple = None) -> None:
    pdf.set_font(FONT, "", 9)
    if color:
        pdf.set_text_color(*color)
    pdf.set_x(24)
    pdf.multi_cell(0, 5, _safe("- " + text))
    pdf.set_text_color(15, 23, 42)


def generar_pdf_tecnico(
    metadata_tecnica: Dict,
    grafo: Optional[nx.DiGraph],
    imagen_grafo_png: Optional[bytes],
    filename_contrato: str,
    modelo: str = "gemini-2.5-pro",
) -> bytes:
    """
    Genera el informe técnico en PDF para usuarios admin.

    Args:
        metadata_tecnica: dict con n_capitulos, n_anexos, n_secciones,
                          capitulos, anexos, validacion_clausulas.
        grafo: DiGraph de NetworkX con el grafo de conocimiento.
        imagen_grafo_png: bytes PNG del grafo, o None si GraphRAG no estaba activo.
        filename_contrato: nombre del contrato auditado.

    Returns:
        bytes del PDF.
    """
    nombre_modelo = _NOMBRES_MODELO.get(modelo, modelo)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # ── Encabezado ──────────────────────────────────────────────────────────
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, 210, 28, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(FONT, "B", 16)
    pdf.set_xy(20, 7)
    pdf.cell(0, 8, _safe("ContractIA - Informe Tecnico (Admin)"), align="L")
    pdf.set_font(FONT, "", 9)
    pdf.set_xy(20, 17)
    pdf.cell(0, 5, _safe(filename_contrato), align="L")
    pdf.set_font(FONT, "", 8)
    pdf.set_xy(110, 12)
    pdf.cell(0, 5, _safe(f"Modelo IA: {nombre_modelo}"), align="R")
    pdf.set_xy(110, 17)
    pdf.cell(0, 5, _safe(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), align="R")
    pdf.ln(20)
    pdf.set_text_color(15, 23, 42)

    # ── FASE 0: Análisis Estructural ─────────────────────────────────────────
    _h1(pdf, "FASE 0: Analisis Estructural")
    n_caps  = metadata_tecnica.get("n_capitulos", 0)
    n_anxs  = metadata_tecnica.get("n_anexos", 0)
    n_total = metadata_tecnica.get("n_secciones", 0)

    _body(pdf, f"Total de secciones detectadas: {n_total}  ({n_caps} capitulos, {n_anxs} anexos)")
    pdf.ln(2)

    caps = metadata_tecnica.get("capitulos", [])
    if caps:
        _h2(pdf, f"Capitulos ({n_caps})")
        for titulo in caps:
            _bullet(pdf, titulo)

    anxs = metadata_tecnica.get("anexos", [])
    if anxs:
        _h2(pdf, f"Anexos ({n_anxs})")
        for titulo in anxs:
            _bullet(pdf, titulo)

    # ── FASE 0.5: Validación de Secuencia ────────────────────────────────────
    _h1(pdf, "FASE 0.5: Auditoria de Secuencia de Clausulas")

    validacion: List[Dict] = metadata_tecnica.get("validacion_clausulas", [])
    if not validacion:
        _body(pdf, "No se encontraron capitulos con clausulas para validar.")
    else:
        n_validos   = sum(1 for v in validacion if v["valido"])
        n_invalidos = len(validacion) - n_validos
        _body(pdf, f"Capitulos auditados: {len(validacion)}  |  Validos: {n_validos}  |  Con gaps: {n_invalidos}")
        pdf.ln(2)

        for v in validacion:
            seccion = v.get("seccion", "N/A")
            n       = v.get("n_clausulas", 0)
            valido  = v.get("valido", True)
            faltant = v.get("faltantes", [])

            if valido:
                marca = "[OK]"
                color = _GREEN
            else:
                marca = "[!] "
                color = _RED

            pdf.set_font(FONT, "B", 9)
            pdf.set_text_color(*color)
            pdf.set_x(20)
            pdf.write(5, _safe(f"{marca} "))
            pdf.set_text_color(15, 23, 42)
            pdf.set_font(FONT, "", 9)
            detalle = f"{seccion}  ({n} clausulas)"
            if faltant:
                detalle += f"  — Faltan: {', '.join(faltant[:8])}"
                if len(faltant) > 8:
                    detalle += f" ... (+{len(faltant) - 8} mas)"
            pdf.multi_cell(0, 5, _safe(detalle))

    # ── GraphRAG: Estadísticas del grafo ─────────────────────────────────────
    _h1(pdf, "GraphRAG: Grafo de Conocimiento")

    if grafo is None or grafo.number_of_nodes() == 0:
        _body(pdf, "GraphRAG no estaba activo en esta auditoria.")
    else:
        n_nodos   = grafo.number_of_nodes()
        n_aristas = grafo.number_of_edges()
        _body(pdf, f"Nodos: {n_nodos}    Relaciones (aristas): {n_aristas}")
        pdf.ln(2)

        # Conteo de tipos de relación
        relaciones: Dict[str, int] = {}
        for _, _, data in grafo.edges(data=True):
            rel = data.get("relacion", "DESCONOCIDA")
            relaciones[rel] = relaciones.get(rel, 0) + 1

        if relaciones:
            _h2(pdf, "Tipos de relacion")
            for rel, cnt in sorted(relaciones.items(), key=lambda x: -x[1]):
                _bullet(pdf, f"{rel}: {cnt}")

        # Top 10 nodos más conectados
        grado = dict(grafo.degree())
        top10 = sorted(grado.items(), key=lambda x: -x[1])[:10]
        if top10:
            pdf.ln(2)
            _h2(pdf, "Top 10 nodos mas conectados")
            for nodo, deg in top10:
                _bullet(pdf, f"[grado {deg}]  {nodo}")

        # Aristas completas
        aristas_data = list(grafo.edges(data=True))
        _h2(pdf, f"Listado de relaciones ({len(aristas_data)})")
        for u, v, d in aristas_data:
            rel = d.get("relacion", "")
            ctx = d.get("contexto", "")
            linea = f"{u} --[{rel}]--> {v}"
            if ctx:
                linea += f"  ({ctx[:80]}{'...' if len(ctx) > 80 else ''})"
            _bullet(pdf, linea)

        # Imagen del grafo
        if imagen_grafo_png:
            pdf.add_page()
            _h1(pdf, "Visualizacion del Grafo")
            _body(pdf, "Representacion visual del grafo de conocimiento del contrato.", size=9)
            pdf.ln(3)

            import io
            import tempfile, os
            # Guardar PNG en archivo temporal para fpdf2 (no soporta bytes directos en image())
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(imagen_grafo_png)
                tmp_path = tmp.name
            try:
                # Centrar la imagen en la página (170mm de ancho disponible)
                pdf.image(tmp_path, x=20, y=None, w=170)
            finally:
                os.unlink(tmp_path)

    # ── Pie de página ────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.4)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)
    pdf.set_font(FONT, "I", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5, _safe("Informe tecnico confidencial - Generado por ContractIA - contractia.pe"), align="C")

    return bytes(pdf.output())
