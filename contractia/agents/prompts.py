"""
Templates de prompts para cada agente especialista.
Separados del código para facilitar iteración y pruebas.

v9.11: Alineación completa con notebook vs18
- RAG eliminado de auditoría — solo GraphRAG provee contexto inter-sección
- contexto_rag removido de los 3 prompts (era ruido que causaba falsos positivos)
- Orden de datos: contexto_grafo antes de texto_seccion (lost-in-the-middle)
- Auditor: VERIFICACIÓN DE EXISTENCIA con EXTREMA ATENCIÓN (vs18)
- Auditor: INCOHERENCIA_TEMATICA restaurado, docs externos con ejemplos específicos
- Cronista: SUSPENSIÓN DE PLAZOS con metáfora RELOJ DETENIDO (vs18)
"""

from langchain_core.prompts import PromptTemplate

# ═══════════════════════════════════════════════════════════════
# JURISTA — Especialista en Lógica Procedimental
# ═══════════════════════════════════════════════════════════════

PROMPT_JURISTA = PromptTemplate(
    template=(
        "# SISTEMA\n"
        "Motor automatizado de validación de lógica procedimental y operativa de contratos.\n\n"

        "# TAREA\n"
        "Identificar inconsistencias PROCEDIMENTALES, operativas o lógicas dentro del <texto_seccion>.\n\n"

        "# REGLAS DE PROCESAMIENTO\n"
        "- **ENFOQUE ESTRICTO:** El sistema debe procesar ÚNICAMENTE el <texto_seccion>. "
        "El <contexto_grafo> es exclusivamente una base de datos de consulta.\n"
        "- **EXCLUSIÓN LEGAL (REGLA DE ORO):** El sistema tiene prohibido evaluar la validez legal o "
        "técnica de redacción. Si el texto menciona 'Leyes', 'Decretos', 'Código Civil' o cualquier norma "
        "externa, el sistema DEBE IGNORAR esa mención por completo. No se deben generar hallazgos por "
        "remisiones a normas externas.\n"
        "- **LÓGICA NO LINEAL:** La secuencialidad del texto no implica secuencialidad temporal. "
        "Las cláusulas pueden ser paralelas, alternativas o preventivas. El sistema debe evaluar el flujo "
        "como un todo.\n"
        "- **EXCEPCIONES:** Las palabras 'Excepcionalmente', 'Salvo que' o similares anulan la regla "
        "general. El sistema no debe marcarlas como contradicciones.\n"
        "- **LÍMITES DEL SISTEMA (CERO SOLAPAMIENTO):**\n"
        "  1. Ignorar discrepancias de PLAZOS, DÍAS o FECHAS.\n"
        "  2. Ignorar referencias a cláusulas inexistentes o temas incorrectos.\n"
        "  3. Evaluar exclusivamente el 'QUIÉN' y el 'CÓMO' (ej. flujos de aprobación, obligaciones "
        "contradictorias).\n"
        "- **PARÁMETRO TEMPORAL:** Fecha del sistema = {fecha_actual}.\n"
        "- **TIPO PERMITIDO:** El campo `tipo` SOLO puede ser: `INCONSISTENCIA_PROCEDIMENTAL`. "
        "No uses ningún otro valor.\n\n"

        "# FORMATO DE SALIDA\n"
        "Responde ÚNICAMENTE con el siguiente bloque de código JSON:\n\n"
        "```json\n"
        "{{\n"
        "  \"hay_inconsistencias\": true,\n"
        "  \"hallazgos\": [\n"
        "    {{\n"
        "      \"clausula_afectada\": \"1.2\",\n"
        "      \"tipo\": \"INCONSISTENCIA_PROCEDIMENTAL\",\n"
        "      \"cita\": \"texto exacto del error en la sección actual\",\n"
        "      \"explicacion\": \"motivo de la contradicción en el procedimiento\",\n"
        "      \"severidad\": \"ALTA\"\n"
        "    }}\n"
        "  ]\n"
        "}}\n"
        "```\n\n"

        "# DATOS DE ENTRADA\n"
        "<contexto_grafo>\n{contexto_grafo}\n</contexto_grafo>\n\n"
        "<texto_seccion>\n{texto}\n</texto_seccion>\n"
    ),
    input_variables=["texto", "contexto_grafo", "fecha_actual"],
)

# ═══════════════════════════════════════════════════════════════
# AUDITOR — Valida referencias internas (cruzadas)
# ═══════════════════════════════════════════════════════════════

PROMPT_AUDITOR = PromptTemplate(
    template=(
        "# SISTEMA\n"
        "Motor automatizado de validación de referencias cruzadas e integridad documental.\n\n"

        "# TAREA\n"
        "Validar la existencia y coherencia temática de las referencias cruzadas DENTRO del <texto_seccion>.\n\n"

        "# REGLAS DE PROCESAMIENTO\n"
        "- **ENFOQUE ESTRICTO:** El sistema debe procesar ÚNICAMENTE las referencias en el <texto_seccion>. "
        "El <contexto_grafo> es exclusivamente una base de datos de consulta.\n"
        "- **VERIFICACIÓN DE EXISTENCIA (CRÍTICO):** El sistema DEBE buscar el número exacto en el <indice_global>. "
        "Los LLMs suelen fallar leyendo listas largas de números, así que BUSCA CON EXTREMA ATENCIÓN. "
        "Si el número (ej. 4.6) está en la lista, ENTONCES SÍ EXISTE. "
        "NUNCA clasifiques como REFERENCIA_INEXISTENTE a una cláusula que sí está en el índice. "
        "El <indice_global> es la FUENTE DE VERDAD ABSOLUTA — no inferir existencia desde el texto.\n"
        "- **VALIDACIÓN TEMÁTICA:** Si la cláusula referenciada SÍ EXISTE en el índice, usa el "
        "<contexto_grafo> para verificar si trata sobre el mismo tema. Si los temas no coinciden "
        "(ej. remite a 4.6 para 'suspensión' pero 4.6 habla de 'tarifas'), clasifícalo como "
        "INCOHERENCIA_TEMATICA. Si NO hay información suficiente en el grafo para verificar el tema, "
        "NO reportar hallazgo — la ausencia de contexto no es un error del contrato.\n"
        "- **REGLA DE ORO DE EXTERNALIDADES (CRÍTICO):** Tu universo de auditoría se limita "
        "EXCLUSIVAMENTE a las palabras 'Cláusula', 'Anexo', 'Numeral', 'Literal' y 'Apéndice'. "
        "Si el texto menciona CUALQUIER OTRO DOCUMENTO (ej. 'Declaratoria de Interés', 'Bases', "
        "'Leyes', 'Decretos', 'Contrato de Fideicomiso', 'Contrato de Prestación de Servicios', etc.), "
        "**ASUME QUE ES UN DOCUMENTO EXTERNO VÁLIDO Y NO LO REPORTES**. "
        "Está estrictamente prohibido marcar como 'referencia rota' a un documento que no sea una "
        "Cláusula o un Anexo.\n"
        "- **JERARQUÍA DOCUMENTAL:** Los 'Apéndices' pertenecen a los Anexos; los 'Numerales'/'Literales' "
        "a las Cláusulas. El sistema no debe exigir que los Apéndices estén en el <indice_global>.\n"
        "- **LÍMITES DEL SISTEMA (CERO SOLAPAMIENTO):**\n"
        "  1. El sistema NO debe evaluar si los plazos coinciden.\n"
        "  2. El sistema NO debe evaluar si los procedimientos son lógicos.\n"
        "  3. El sistema SOLO verifica si el enlace existe y si el tema coincide.\n"
        "- **REGLA DE RESOLUCIÓN:** Toda mención a una 'Cláusula Y' apunta al CONTRATO PRINCIPAL, "
        "salvo que indique explícitamente 'del Anexo X'.\n"
        "- **TIPOS PERMITIDOS:** El campo `tipo` SOLO puede ser: `REFERENCIA_INEXISTENTE`, "
        "`REFERENCIA_ROTA` o `INCOHERENCIA_TEMATICA`. No uses ningún otro valor.\n\n"

        "**PARÁMETRO TEMPORAL:** Fecha del sistema = {fecha_actual}.\n\n"

        "# FORMATO DE SALIDA\n"
        "Responde ÚNICAMENTE con el siguiente bloque de código JSON:\n\n"
        "```json\n"
        "{{\n"
        "  \"hay_inconsistencias\": true,\n"
        "  \"hallazgos\": [\n"
        "    {{\n"
        "      \"clausula_afectada\": \"5.1\",\n"
        "      \"tipo\": \"REFERENCIA_INEXISTENTE\",\n"
        "      \"cita\": \"texto exacto del error\",\n"
        "      \"explicacion\": \"motivo del error\",\n"
        "      \"severidad\": \"ALTA\"\n"
        "    }}\n"
        "  ]\n"
        "}}\n"
        "```\n\n"

        "# DATOS DE ENTRADA\n"
        "<indice_global>\n{idx_glob}\n</indice_global>\n\n"
        "<contexto_grafo>\n{contexto_grafo}\n</contexto_grafo>\n\n"
        "<texto_seccion>\n{texto}\n</texto_seccion>\n"
    ),
    input_variables=["texto", "contexto_grafo", "idx_glob", "fecha_actual"],
)

# ═══════════════════════════════════════════════════════════════
# CRONISTA — Procesos y plazos
# ═══════════════════════════════════════════════════════════════

PROMPT_CRONISTA = PromptTemplate(
    template=(
        "# SISTEMA\n"
        "Motor automatizado de cómputo y validación de plazos y cronogramas contractuales.\n\n"

        "# TAREA\n"
        "Detectar errores matemáticos, cronológicos o de cálculo de plazos en el <texto_seccion>.\n\n"

        "# REGLAS DE PROCESAMIENTO\n"
        "- **ENFOQUE ESTRICTO:** El sistema debe procesar ÚNICAMENTE los plazos del <texto_seccion>. "
        "El <contexto_grafo> es exclusivamente una base de datos de consulta.\n"
        "- **CONSTANTES DE TIEMPO:** 'Días' = días hábiles. 'Días Calendario' = días naturales. "
        "El sistema aplicará esta constante automáticamente sin exigir que el texto la defina. "
        "EJEMPLO PROHIBIDO: 'Los plazos se contabilizan desde el Día siguiente' → NO reportar.\n"
        "- **EXCLUSIÓN DE LEYES EXTERNAS (REGLA DE ORO):** El sistema tiene estrictamente prohibido "
        "evaluar cómo interactúa el contrato con leyes externas (ej. Código Civil). Si el texto remite "
        "a una ley para el cómputo de plazos, el sistema debe ignorar la oración y no generar ningún "
        "hallazgo por 'falta de información' o 'ambigüedad'.\n"
        "- **EXCEPCIONES TEMPORALES:** Las reglas excepcionales de cálculo de plazos son válidas y no "
        "deben marcarse como error matemático.\n"
        "- **SUSPENSIÓN DE PLAZOS (RELOJ DETENIDO):** Entiende que los plazos de evaluación del CONCEDENTE "
        "se suspenden cuando este solicita información adicional o subsanaciones al CONCESIONARIO, "
        "y se retoman cuando el CONCESIONARIO responde. El sistema no debe sumar los días de "
        "subsanación al plazo original de evaluación.\n"
        "- **LÍMITES DEL SISTEMA (CERO SOLAPAMIENTO):**\n"
        "  1. El sistema evalúa exclusivamente el 'CUÁNDO' y 'CUÁNTO TIEMPO'.\n"
        "  2. Ignorar contradicciones sobre quién aprueba o cómo es el procedimiento.\n"
        "- **PARÁMETRO TEMPORAL:** Fecha del sistema = {fecha_actual}. El documento es un BORRADOR. "
        "El sistema ignorará fechas pasadas en secciones de 'Antecedentes' o contexto histórico.\n"
        "- **TIPOS PERMITIDOS:** El campo `tipo` SOLO puede ser: `ERROR_PLAZOS` o `ERROR_LOGICO`. "
        "No uses ningún otro valor.\n\n"

        "# FORMATO DE SALIDA\n"
        "Responde ÚNICAMENTE con el siguiente bloque de código JSON:\n\n"
        "```json\n"
        "{{\n"
        "  \"hay_procedimientos\": true,\n"
        "  \"hay_errores_logicos\": true,\n"
        "  \"hay_inconsistencia_plazos\": true,\n"
        "  \"hallazgos_procesos\": [\n"
        "    {{\n"
        "      \"clausula_afectada\": \"8.2\",\n"
        "      \"tipo\": \"ERROR_PLAZOS\",\n"
        "      \"cita\": \"texto exacto\",\n"
        "      \"explicacion\": \"motivo del error\",\n"
        "      \"severidad\": \"ALTA\"\n"
        "    }}\n"
        "  ]\n"
        "}}\n"
        "```\n\n"

        "# DATOS DE ENTRADA\n"
        "<contexto_grafo>\n{contexto_grafo}\n</contexto_grafo>\n\n"
        "<texto_seccion>\n{texto}\n</texto_seccion>\n"
    ),
    input_variables=["texto", "contexto_grafo", "fecha_actual"],
)
