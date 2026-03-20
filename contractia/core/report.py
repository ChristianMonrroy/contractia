"""
Generación del informe de auditoría en formato Markdown.
"""

from pathlib import Path
from typing import Dict, List

from contractia.core.segmenter import _key_sort_clauses


_NOMBRES_MODELO = {
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
}


def render_auditoria_markdown(resultado: Dict, modelo: str = "gemini-2.5-pro") -> str:
    """Convierte el resultado de la auditoría en un informe Markdown."""
    secciones_idx = resultado.get("indice_secciones", [])
    claus_idx = resultado.get("indice_global_clausulas", [])
    resultados = resultado.get("resultados_auditoria", [])

    md = ["# Informe de Auditoría Contractual (Detalle por Cláusula)"]

    md.append("## Resumen Estructural")
    md.append(f"- **Secciones Analizadas**: {len(secciones_idx)}")
    md.append(f"- **Cláusulas Definidas**: {len(claus_idx)}")

    total_errores = sum(len(r["hallazgos"]) for r in resultados)
    md.append(f"- **Total de Inconsistencias Detectadas**: {total_errores}")
    md.append(f"- **Modelo IA utilizado**: {_NOMBRES_MODELO.get(modelo, modelo)}")

    md.append("\n## Índice Global de Cláusulas (Definiciones)")
    if claus_idx:
        md.append(", ".join(claus_idx))
    else:
        md.append("_No se detectaron cláusulas._")

    md.append("\n## Hallazgos Detallados")

    if not resultados:
        md.append("_No se detectaron inconsistencias en el contrato._")
        return "\n\n".join(md)

    for res_sec in resultados:
        titulo_sec = res_sec["seccion"]
        hallazgos = res_sec["hallazgos"]

        md.append(f"\n### {titulo_sec}")

        # Agrupar por cláusula
        mapa_clausulas: Dict[str, List] = {}
        for h in hallazgos:
            if isinstance(h, dict):
                c_id = h.get("clausula_afectada", "General")
            else:
                c_id = getattr(h, "clausula_afectada", "General")
            mapa_clausulas.setdefault(c_id, []).append(h)

        claves = sorted(
            mapa_clausulas.keys(),
            key=lambda x: _key_sort_clauses(x) if x != "General" else [0],
        )

        for c_id in claves:
            lista_h = mapa_clausulas[c_id]
            md.append(f"\n#### Cláusula {c_id}")

            for item in lista_h:
                if isinstance(item, dict):
                    tipo = item.get("tipo", "ERROR")
                    sev = item.get("severidad", "MEDIA")
                    expl = item.get("explicacion", "")
                    cita = item.get("cita", "")
                else:
                    tipo, sev = item.tipo, item.severidad
                    expl, cita = item.explicacion, item.cita

                md.append(f"- **[{tipo}]** ({sev})")
                md.append(f"  - *Problema:* {expl}")
                if cita:
                    md.append(f'  - *Cita:* "{cita}"')

    return "\n\n".join(md)


def save_report(md_text: str, filepath: Path) -> None:
    """Guarda el informe Markdown en disco."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(md_text or "", encoding="utf-8")
    print(f"\n💾 Informe guardado en '{filepath}'.")
