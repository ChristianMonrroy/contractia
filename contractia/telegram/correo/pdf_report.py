"""
Generación de PDF del informe de auditoría usando fpdf2 (pure Python, sin deps del SO).

Convierte el Markdown producido por render_auditoria_markdown en un PDF
con estilos corporativos de ContractIA: encabezado azul marino, tipografía
limpia y soporte completo para caracteres en español (Latin-1).
"""

import re
from fpdf import FPDF

_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_NAVY = (30, 58, 95)      # --primary ContractIA
_GRAY = (71, 85, 105)     # texto secundario
_LIGHT = (203, 213, 225)  # líneas sutiles


def _safe(text: str) -> str:
    """Convierte a Latin-1 (todas las letras del español están incluidas)."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _write_line(pdf: FPDF, text: str, font: str, size: int, x: float = None) -> None:
    """Escribe una línea con soporte de **negrita** inline usando write()."""
    if x is not None:
        pdf.set_x(x)
    parts = _BOLD_RE.split(text)
    for i, part in enumerate(parts):
        if not part:
            continue
        pdf.set_font(font, "B" if i % 2 == 1 else "", size)
        pdf.write(5, _safe(part))
    pdf.ln()


def generar_pdf_auditoria(md_content: str, filename: str) -> bytes:
    """
    Genera el informe de auditoría en PDF a partir del contenido Markdown.

    Returns:
        Bytes del PDF listo para adjuntar a un email.
    """
    FONT = "Helvetica"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # ── Encabezado ──────────────────────────────────────────────────────────
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, 210, 28, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(FONT, "B", 16)
    pdf.set_xy(20, 8)
    pdf.cell(0, 8, "ContractIA — Informe de Auditoría", align="L")
    pdf.set_font(FONT, "", 9)
    pdf.set_xy(20, 18)
    pdf.cell(0, 5, _safe(filename), align="L")
    pdf.ln(18)

    # ── Cuerpo del informe ───────────────────────────────────────────────────
    pdf.set_text_color(15, 23, 42)  # --foreground

    for raw_line in md_content.split("\n"):
        line = raw_line.rstrip()

        # Línea vacía
        if not line.strip():
            pdf.ln(2)
            continue

        # H1
        if line.startswith("# "):
            pdf.ln(3)
            pdf.set_font(FONT, "B", 14)
            pdf.set_text_color(*_NAVY)
            pdf.multi_cell(0, 7, _safe(line[2:]))
            pdf.set_draw_color(*_NAVY)
            pdf.set_line_width(0.5)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(3)
            pdf.set_text_color(15, 23, 42)

        # H2
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font(FONT, "B", 12)
            pdf.set_text_color(*_NAVY)
            pdf.multi_cell(0, 6, _safe(line[3:]))
            pdf.set_draw_color(*_LIGHT)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(2)
            pdf.set_text_color(15, 23, 42)

        # H3
        elif line.startswith("### "):
            pdf.ln(1)
            pdf.set_font(FONT, "B", 11)
            pdf.set_text_color(*_GRAY)
            pdf.multi_cell(0, 6, _safe(line[4:]))
            pdf.ln(1)
            pdf.set_text_color(15, 23, 42)

        # Separador horizontal
        elif line.strip().startswith("---"):
            pdf.set_draw_color(*_LIGHT)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y() + 1, 190, pdf.get_y() + 1)
            pdf.ln(4)

        # Elemento de lista con viñeta
        elif line.strip().startswith(("- ", "* ")):
            indent = 4 * (len(line) - len(line.lstrip()))  # sangría proporcional
            bullet_text = line.strip()[2:]
            pdf.set_x(20 + indent + 3)
            pdf.set_font(FONT, "", 10)
            pdf.write(5, "\x95 ")  # bullet •
            _write_line(pdf, bullet_text, FONT, 10, x=None)

        # Texto normal (con posible **negrita** inline)
        else:
            _write_line(pdf, line.strip(), FONT, 10, x=20)

    # ── Pie de página ───────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.4)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)
    pdf.set_font(FONT, "I", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5, "Generado automáticamente por ContractIA — contractia.pe", align="C")

    return bytes(pdf.output())
