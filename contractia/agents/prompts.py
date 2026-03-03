"""
Templates de prompts para cada agente especialista.
Separados del código para facilitar iteración y pruebas.
"""

from langchain_core.prompts import PromptTemplate

# ═══════════════════════════════════════════════════════════════
# JURISTA — Identifica normativa externa
# ═══════════════════════════════════════════════════════════════

PROMPT_JURISTA = PromptTemplate(
    template=(
        "Eres un experto legal. Identifica referencias a NORMATIVA EXTERNA.\n"
        "Utiliza el CONTEXTO DEL GRAFO para detectar si una cláusula invoca una ley "
        "que contradice el marco general del contrato.\n\n"
        "CONTEXTO DEL GRAFO (relaciones de esta sección):\n{contexto_grafo}\n\n"
        "Incluye 'CONTRATO DE PRESTACIÓN DE SERVICIOS' como externo.\n"
        "Salida: JSON con lista de strings (ej. [\"Ley 123\", \"Código Civil\"]).\n"
        "Responde SOLO con el JSON.\n"
        "Texto:\n{texto}\n"
    ),
    input_variables=["texto", "contexto_grafo"],
)

# ═══════════════════════════════════════════════════════════════
# AUDITOR — Valida referencias internas (cruzadas)
# ═══════════════════════════════════════════════════════════════

PROMPT_AUDITOR = PromptTemplate(
    template=(
        "Eres Auditor de Contratos. Valida referencias internas.\n"
        "Fuentes:\n- Global: {idx_glob}\n- Secciones: {idx_sec}\n- Local: {idx_loc}\n"
        "Ignora externas: {refs_externas}.\n\n"
        "CONTEXTO DEL GRAFO (textos de cláusulas referenciadas):\n{contexto_grafo}\n\n"
        "INSTRUCCIONES:\n"
        "1. Identifica la **Cláusula Específica** (ej. 5.1) del error.\n"
        "2. Si una cláusula no está en el ÍNDICE GLOBAL, es REFERENCIA_INEXISTENTE.\n"
        "3. Usa el grafo para verificar si la referencia tiene sentido lógico.\n"
        "4. Solo reporta ERRORES REALES (referencias rotas o incoherentes).\n"
        "5. Ignora años, montos o días.\n\n"
        "Responde SOLO con JSON válido:\n"
        "{{\n"
        '  "hay_inconsistencias": bool,\n'
        '  "hallazgos": [\n'
        '    {{"clausula_afectada": "...", "tipo": "REFERENCIA_ROTA", '
        '"cita": "...", "explicacion": "...", "severidad": "ALTA"}}\n'
        "  ]\n"
        "}}\n"
        "Texto:\n{texto}\n"
    ),
    input_variables=["texto", "idx_glob", "idx_sec", "idx_loc", "refs_externas", "contexto_grafo"],
)

# ═══════════════════════════════════════════════════════════════
# CRONISTA — Procesos y plazos
# ═══════════════════════════════════════════════════════════════

PROMPT_CRONISTA = PromptTemplate(
    template=(
        "Eres un experto Senior en Gestión de Procesos y Plazos Contractuales. "
        "Analiza el texto de forma EXHAUSTIVA.\n\n"
        "REGLAS DE INTERPRETACIÓN DE PLAZOS (CRÍTICO):\n"
        "- **'Días' o 'Día' (con mayúscula)** = DÍAS HÁBILES (Business Days).\n"
        "- **'Días Calendario'** = DÍAS NATURALES (Calendar Days).\n"
        "- Mezclar estos términos sin conversión explícita es un ERROR de ambigüedad.\n\n"
        "CONTEXTO DEL GRAFO (cadena de eventos y plazos relacionados):\n{contexto_grafo}\n"
        "Usa el grafo para sumar plazos encadenados y verificar si exceden máximos globales.\n\n"
        "TUS TAREAS (Análisis Profundo):\n"
        "1. **Lógica Secuencial:** Analiza paso a paso el flujo. ¿El paso A lleva al B? "
        "¿Qué pasa si el paso B falla? Si no hay ruta de salida (dead-end), es un ERROR.\n"
        "2. **Cálculo de Plazos:** Suma los plazos parciales. Si el contrato dice "
        "'Plazo Máximo: 20 Días' pero la suma de (Revisión 10 Días + Subsanación 15 Días) "
        "da 25, es un ERROR GRAVE.\n"
        "3. **Completitud:** ¿Faltan responsables o tiempos de respuesta en algún paso crítico?\n\n"
        "Responde SOLO con JSON válido:\n"
        "{{\n"
        '  "hay_procedimientos": bool,\n'
        '  "hay_errores_logicos": bool,\n'
        '  "hay_inconsistencia_plazos": bool,\n'
        '  "hallazgos_procesos": [\n'
        "    {{\n"
        '      "clausula_afectada": "Nro de cláusula (ej. 5.1)",\n'
        '      "tipo": "LOGICA_PROCESO" o "ERROR_PLAZOS",\n'
        '      "cita": "Texto breve",\n'
        '      "explicacion": "Explicación detallada del problema.",\n'
        '      "severidad": "ALTA"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
        "Texto:\n{texto}\n"
    ),
    input_variables=["texto", "contexto_grafo"],
)
