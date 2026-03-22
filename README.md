# ContractIA v10.2.0

Sistema de auditoría inteligente de contratos, impulsado por IA generativa (Gemini 2.5 Pro), con arquitectura multi-agente en paralelo, GraphRAG, defensa contra prompt injection en 2 capas, cache de grafos en GCS, y acceso via web y Telegram.

**Producción:** [contractia.pe](https://contractia.pe) | **API:** [contractia-api-444429430547.us-central1.run.app](https://contractia-api-444429430547.us-central1.run.app/docs)

---

## Benchmark v10.2.0

| Métrica | Resultado |
|---------|-----------|
| **F1-Score** | **76-83%** |
| **Recall** | 77-80% (55-57 de 71 hallazgos de referencia) |
| **Precisión** | 74-86% (9-19 falsos positivos) |
| **Tiempo de auditoría** | ~24 min (324 págs, 41 secciones, 448 cláusulas) |
| **Contrato de prueba** | VIC PTAR San Martín (concesión de saneamiento, 324 páginas) |

## Novedades v10.2.0

| Área | Cambio |
|------|--------|
| **Agentes en paralelo** | Los 3 agentes (Jurista, Auditor, Cronista) se ejecutan simultáneamente con `ThreadPoolExecutor(max_workers=3)`. Reduce el tiempo de auditoría de ~72 min a ~24 min sin pérdida de calidad |
| **Timeout 600s** | Timeout del LLM aumentado de 180s a 600s (idéntico al notebook vs18). Permite a Gemini razonar más profundamente: tiempo por agente sube de ~12s a ~34s, pero F1 sube de 61% a 83% |
| **Sin structured output** | Eliminado `with_structured_output(Pydantic)` de los agentes. Se usa texto libre + `parse_json_seguro` (idéntico al notebook). El modo estructurado restringía la generación del LLM |
| **parse_json idéntico a notebook** | Eliminada reparación de JSON truncado y tags `<razonamiento>`. Produce grafos más pequeños y estables (~235 nodos vs ~400) |
| **PyPDFLoader** | Extracción de texto idéntica al notebook (antes PdfReader + OCR producía ~2,000 chars extras que desestabilizaban el grafo) |
| **Prompts idénticos a notebook vs18** | Sin `contexto_rag`, sin TIPOS PERMITIDOS, sin salvaguardas anti-FP. El LLM elige tipos libremente |

## Novedades v9.11.0

| Área | Cambio |
|------|--------|
| **Auditoría sin RAG (alineación notebook vs18)** | Los agentes de auditoría (Jurista, Auditor, Cronista) ya no reciben `contexto_rag`; solo trabajan con `texto_seccion` + `contexto_grafo` (GraphRAG). RAG + Scout siguen activos para consultas interactivas |
| **Scout solo en consultas** | El Agente Scout (Agentic RAG) ya no se ejecuta durante auditorías; solo enriquece consultas interactivas donde el usuario hace preguntas libres |

## Novedades v9.10.0

| Área | Cambio |
|------|--------|
| **Bot → tabla `auditorias`** | Las auditorías del bot Telegram ahora se registran en la misma tabla `auditorias` de PostgreSQL que las web; visibles en el panel admin "Auditorías de todos los usuarios" con estado, hallazgos y logs de diagnóstico |
| **Bot → email con PDF** | Al completar una auditoría por Telegram, se envía email al usuario con el informe en PDF adjunto (mismo template y formato que el flujo web); requiere que el usuario tenga email registrado |
| **Web → progreso del grafo en diagnóstico** | La FASE 1.5 (construcción GraphRAG) ahora reporta progreso por sección (`Grafo [i/N] Título — X tripletas`) al panel de diagnóstico web; antes solo mostraba el inicio de la fase sin detalle |
| **Cache de grafos en GCS** | Grafos GraphRAG se cachean en GCS (SHA256 hash del texto + prompt); reutilización ahorra ~40 min por auditoría; bot pregunta "Reutilizar/Reconstruir" si detecta cache; web-auditoría siempre reconstruye y actualiza cache |
| **`/rebuild_graph`** | Nuevo comando del bot para reconstruir manualmente el grafo cacheado del contrato activo |
| **PI en consultas** | Defensa contra prompt injection (Capa 1 + Capa 2) extendida a flujos de consulta interactiva (bot + web), no solo auditorías |
| **`deploy.yml`** | `AUDIT_QUEUE_BUCKET` agregado como variable persistente en el workflow de CI/CD para evitar pérdida en deploys |

## Novedades v9.9.0

| Área | Cambio |
|------|--------|
| **Capa 1 — Sanitización programática** | Nuevo módulo `contractia/core/sanitizer.py`: elimina caracteres Unicode invisibles (zero-width spaces, BOM, soft hyphens, directional marks), normaliza a NFC, y detecta 7 patrones heurísticos de prompt injection bilingüe (ES/EN) por regex sin depender del LLM |
| **Capa 2 — Escaneo LLM pre-auditoría** | Nuevo módulo `contractia/core/security.py`: analiza el texto completo con el LLM usando aislamiento por etiquetas `<documento>` antes de que los agentes lo procesen; diseño **fail-closed** (si falla → documento inseguro); output estructurado con Pydantic (`es_seguro`, `evidencia`, `confianza`) |
| **Tabla `prompt_injection_logs`** | Nueva tabla dedicada en PostgreSQL para registrar cada intento de prompt injection con: `audit_id`, `user_id`, `filename`, `evidencia_llm`, `alertas_heuristicas`, `texto_sospechoso`, `confianza`, `detected_at` |
| **Alerta por correo al admin** | Cuando se detecta prompt injection, se envía email automático al `ADMIN_EMAIL` con evidencia del LLM, alertas heurísticas y datos del incidente; envío en thread separado (no bloqueante) |
| **Excepción `PromptInjectionDetectedError`** | Nueva excepción en `orchestrator.py` que aborta la auditoría de forma controlada; manejada en API (status "Bloqueado por seguridad") y bot Telegram (mensaje de alerta al usuario) |
| **`config.py`** | Nueva variable `ADMIN_EMAIL` (default `admin@contractia.pe`) para alertas de seguridad |
| **Template `email_alerta_injection`** | Nuevo template HTML en `templates.py` con estilo rojo/alerta, tabla de datos del incidente, evidencia del LLM y alertas heurísticas |
| **Distinción de falsos positivos** | Cláusulas imperativas normales ("El Concesionario deberá...") NO se marcan como injection; solo se detectan comandos dirigidos a la IA |

## Novedades v9.8.0

| Área | Cambio |
|------|--------|
| **Logs de diagnóstico en tiempo real** | El panel de auditoría muestra los avances del pipeline (FASE 0, 0.5, 1.5, sección por sección) en vivo durante la auditoría y en la pestaña "Diagnóstico técnico" al finalizar |
| **`log_context.py`** | Nuevo módulo `contractia/core/log_context.py`: `ContextVar` que propaga el callback de logs a todos los threads del pipeline sin modificar firmas de funciones |
| **`print()` → `log()`** | `segmenter.py`, `graph.py` y `orchestrator.py` reemplazaron `print()` por `log()` para que los mensajes lleguen al panel de diagnóstico |
| **FASE 0 / 0.5 / 1.5** | `orchestrator.py` emite ahora headers de fase: FASE 0 (estructura: N capítulos, M anexos), FASE 0.5 (índice global de cláusulas y anexos), log por sección con conteo de hallazgos; `graph.py` emite FASE 1.5 al inicio de la construcción del grafo |
| **Endpoint histórico de logs** | Nuevo `GET /contracts/audit/{id}/logs` devuelve todos los logs de diagnóstico de una auditoría completada |
| **Frontend — pestaña Diagnóstico técnico** | Polling cada 5s a `/audit/{id}/logs` durante la auditoría (reemplaza SSE, incompatible con Cloud Run); tab "Diagnóstico técnico" con terminal monoespacio y color-coding al finalizar |
| **`provider.py`** | `timeout=480s` para `gemini-3.1-pro-preview` (8 min vs 180s anterior); evita `ReadTimeout` en contratos de 300+ páginas |
| **Reintentos throttle** | `_MAX_REINTENTOS_THROTTLE=5` para modelos lentos (Gemini 3.1, Claude 4.x); antes los tres modelos usaban el mismo límite de 3 |
| **Bug fix — badge de modelo** | El badge de modelo en pantalla ahora muestra el modelo real de la auditoría (leído de `modelo_usado` vía polling); antes siempre mostraba "Gemini 2.5 Pro" |
| **Bug fix — null safety logs** | `entry.msg?.startsWith()` protegido con `(entry.msg ?? "")` para evitar `TypeError` cuando la DB contiene entradas con `msg: null` |

## Novedades v9.7.0

| Área | Cambio |
|------|--------|
| **Alineación vs16 — Prompts** | Los tres agentes usan `# SISTEMA / Motor automatizado...` y `# REGLAS DE PROCESAMIENTO`; Jurista: **LÓGICA NO LINEAL** (cláusulas paralelas/alternativas no son contradictorias); Auditor: **JERARQUÍA DOCUMENTAL** (Apéndices no exigidos en índice global) y **VALIDACIÓN TEMÁTICA** explícita; Cronista: **SUSPENSIÓN DE PLAZOS** (días de subsanación no se suman al plazo de evaluación) y **CONSTANTES DE TIEMPO** con ejemplo prohibido |
| **Alineación vs16 — Segmentación exacta** | `construir_mapa_clausula_a_seccion` almacena el texto preciso de cada cláusula (desde su posición hasta la siguiente) en lugar del contenido completo de la sección; alineado con la "Segmentación por Diccionario Exacto" del notebook vs16 |
| **Alineación vs16 — GraphRAG** | `obtener_contexto_grafo` recupera `mapa_textos[id_ref]["texto"]` directamente sin truncado ni búsqueda posicional; formato de salida con salto de línea; relación por defecto `CONECTA_CON` igual que vs16 |
| **Scout — Claude omitido** | El Agente Scout se salta explícitamente para modelos Claude; cae a RAG estático sin depender de excepciones (cuota de Vertex AI insuficiente para LLM calls extra del Scout) |
| **Throttle Claude Sonnet** | `claude-sonnet-4-6` confirmado con 429 en producción; mantenido en `_MODELOS_THROTTLE` (agentes en serie, 10s pausa) y `_GRAPH_MODELOS_THROTTLE` (8s sleep) |
| **Cloud Run — BUCKET_NAME** | `BUCKET_NAME=contractia-contracts` agregado como variable de entorno persistente; corrige error de GCS en nuevas instancias con cold start |
| **Cloud Run — Scout activo** | `AGENTIC_RAG_ENABLED=true` configurado como variable persistente en Cloud Run |

## Novedades v9.6.0

| Área | Cambio |
|------|--------|
| **Admin — Todas las auditorías** | Nueva página `/admin/auditorias` con tabla de todas las auditorías de todos los usuarios; auto-refresh cada 10s si hay auditorías en proceso; barra de progreso en tiempo real; botón cancelar desde el panel admin |
| **`admin_router.py`** | Nuevo endpoint `GET /admin/auditorias` (requiere rol admin); lista auditorías de todos los usuarios con JOIN a `usuarios` |
| **`database.py`** | Nueva función `get_todas_auditorias()`; migraciones `modelo_usado TEXT` en `auditorias` y `logs` |
| **Modelo IA en todas las salidas** | Badge de modelo (Gemini 2.5/3.1, Claude Sonnet/Opus) visible en dashboard, registro de actividad admin, PDF estándar (encabezado), PDF técnico (encabezado) y email de notificación |
| **Índice global del Auditor** | `auditar_consistencia()` ahora pasa al Auditor `CLÁUSULAS: ... \| ANEXOS: Anexo I, Anexo II...` (antes solo números de cláusulas); el Auditor puede verificar referencias a anexos contra el índice real del contrato |
| **`orchestrator.py`** | `_MODELOS_THROTTLE` movido a constante de módulo (corrige `NameError` que saltaba el sleep entre secciones); `nombres_anexos` extraído y propagado a `auditar_consistencia()` |
| **PDF técnico — relaciones completas** | Eliminado el límite de 100 relaciones; el PDF muestra todas las aristas del grafo con contexto de hasta 80 chars |
| **`requirements.txt`** | `matplotlib>=3.7.0` añadido (corrige `No module named 'matplotlib'` en generación de imagen del grafo en Cloud Run) |
| **`api.ts`** | Nueva interfaz `AdminAuditRow`; métodos `adminAPI.getTodasAuditorias()` y `adminAPI.cancelAuditAdmin()` |
| **Frontend — admin** | Botón "Todas las auditorías" (azul) en header del panel admin junto al existente "Reporte de actividad" |

## Novedades v9.5.0

| Área | Cambio |
|------|--------|
| **Modelos Claude (admin)** | Claude Sonnet 4.6 y Claude Opus 4.6 disponibles como modelos LLM para auditoría, restringidos a usuarios `admin`; selector de modelo en el frontend de auditoría |
| **Throttle Claude** | `claude-opus-4-6` añadido a `_MODELOS_THROTTLE`; agentes en serie + 10s entre secciones para evitar rate-limit |

## Novedades v9.4.0

| Área | Cambio |
|------|--------|
| **Informe Técnico (Admin)** | Nuevo PDF técnico exclusivo para usuarios `admin`: incluye análisis estructural (Fase 0/0.5), validación de secuencia de cláusulas con gaps detectados, estadísticas del grafo GraphRAG (nodos, aristas, tipos de relación, top-10 conectados), listado completo de relaciones y visualización del grafo como imagen PNG |
| **`segmenter.py`** | Nueva función `separar_en_secciones_con_metadata()` que devuelve `(secciones, metadata_tecnica)` con datos de Fase 0 y 0.5; calcula secuencias de cláusulas con detalle de gaps |
| **`graph.py`** | Nueva función `generar_imagen_grafo()` usando matplotlib Agg (sin GUI, compatible Cloud Run); colorea nodos por tipo (capítulo/anexo), dibuja relaciones etiquetadas, devuelve bytes PNG |
| **`orchestrator.py`** | Retorna `metadata_tecnica`, `grafo` e `imagen_grafo_png` en el resultado de auditoría |
| **`pdf_report_tecnico.py`** | Nuevo generador de PDF técnico (fpdf2); encabezado corporativo, tablas de validación, listado de aristas, imagen del grafo embebida |
| **`sender.py`** | Soporte para segundo PDF adjunto en el email (`adjunto_pdf_tecnico`, `adjunto_nombre_tecnico`) |
| **`database.py`** | Nuevas columnas `metadata_tecnica TEXT` y `graph_data TEXT` en `auditorias`; migraciones idempotentes |
| **`contracts_router.py`** | Guarda metadata y grafo serializado (JSON node-link) cuando es admin; nuevo endpoint `GET /contracts/audit/{id}/pdf-tecnico` (requiere rol admin); envía PDF técnico como segundo adjunto en el email |
| **Dashboard** | Botón "Técnico" (ícono FlaskConical, color púrpura) en historial de auditorías — visible solo para admins cuando hay datos técnicos disponibles |

## Novedades v9.3.0 — v9.3.2

| Área | Cambio |
|------|--------|
| **v9.3.2 — Separación RAG** | `contexto_rag` pasa como variable separada `{contexto_rag}` con tag `<contexto_rag>` (antes mezclado en `{texto}`); los agentes ya no pueden auditar contenido del contexto RAG |
| **v9.3.2 — Tipos explícitos** | Cada agente restringe el campo `tipo` a valores exactos: Jurista→`INCONSISTENCIA_PROCEDIMENTAL`, Auditor→`REFERENCIA_INEXISTENTE\|REFERENCIA_ROTA`, Cronista→`ERROR_PLAZOS\|ERROR_LOGICO` |
| **v9.3.1 — Sin truncado** | Eliminado `_MAX_SECTION_CHARS`: se envía el texto completo de cada sección a los agentes |
| **v9.3.0 — Jurista rediseñado** | Nuevo rol "Especialista en Lógica Procedimental": detecta inconsistencias operativas internas (no normativa externa) |
| **v9.3.0 — Auditor simplificado** | 6 reglas limpias + XML tags; prohibición absoluta de auditar referencias a leyes/decretos externos |
| **v9.3.0 — Agentes paralelos** | Los 3 agentes se ejecutan en paralelo con `ThreadPoolExecutor(max_workers=3)` |

## Novedades v9.2.0

| Área | Cambio |
|------|--------|
| **Auditor — Externalidades** | Nueva regla "PROHIBICIÓN ABSOLUTA DE EXTERNALIDADES": el Auditor ya no marcará como 'referencia rota' las citas a leyes externas (Código Civil, Ley 30225, D.S., ISO). Solo audita referencias a Cláusulas y Anexos del propio contrato; la normativa externa es responsabilidad del Jurista |
| **Auditor — Mismo tema** | El PASO 3 del árbol de decisión ahora exige que la referencia hable del **mismo tema** (no solo que sea coherente). Si los plazos o montos difieren pero el tema es el mismo, se ignora la discrepancia; reduce falsos positivos en referencias a cláusulas con datos actualizados |
| **Cronista — Días = hábiles** | Eliminada la regla que marcaba como error la falta de definición explícita de "Días" vs "Días Calendario". El Cronista ahora asume directamente: `Días` = hábiles, `Días Calendario` = naturales, sin reportar ambigüedad por omisión |
| **Cronista — Externalidades** | Nueva regla "PROHIBICIÓN ABSOLUTA DE EXTERNALIDADES": el Cronista ya no reportará como error ni ambigüedad que el contrato remita a leyes externas (Código Civil, Ley 27444) para el cómputo de plazos |

## Novedades v9.1.0

| Área | Cambio |
|------|--------|
| **Conciencia temporal — Agentes** | Los 3 agentes (Jurista, Auditor, Cronista) reciben `fecha_actual` (fecha del día en formato `YYYY-MM-DD`) en su prompt; permite detectar plazos vencidos, hitos pasados y fechas ilógicas en el contrato |
| **Jurista** | Nueva instrucción "CONCIENCIA TEMPORAL": evalúa si los hitos temporales internos son lógicamente vigentes respecto al día de hoy |
| **Auditor** | Nueva instrucción "CONCIENCIA TEMPORAL": verifica si fechas concretas mencionadas en el texto resultan ilógicas en relación al día de hoy |
| **Cronista** | Nueva instrucción "CONCIENCIA TEMPORAL": calcula si plazos internos han vencido y detecta fechas de entrega ya superadas — el agente más beneficiado por este cambio |
| **GraphRAG — texto preciso** | `obtener_contexto_grafo` ahora busca la posición exacta de la cláusula referenciada dentro del texto de su sección (regex + offset -50 chars) y extrae 1000 chars desde esa posición; antes tomaba siempre los primeros 500 chars del inicio, perdiendo cláusulas ubicadas en el medio del capítulo |

## Novedades v9.0.0

| Área | Cambio |
|------|--------|
| **Agentic RAG — Agente Scout** | Nuevo `AgenteScout` en `contractia/agents/scout.py`; corre antes de Jurista/Auditor/Cronista y usa `bind_tools` (tool calling de Gemini) en un ReAct loop manual para recuperar contexto dinámicamente |
| **Agentic RAG — Tools** | Dos herramientas: `buscar_en_contrato(consulta)` (Hybrid RAG semántico) y `obtener_clausula(numero)` (búsqueda exacta por número); el LLM decide cuándo y cuántas veces llamarlas |
| **Agentic RAG — Retrocompatible** | `AGENTIC_RAG_ENABLED=false` por defecto; sin este flag el pipeline funciona exactamente igual que v8.8.0; cero cambios en prompts, schemas ni routers |
| **Agentic RAG — 3 agentes enriquecidos** | El contexto Scout se pasa vía `{texto}` a los 3 agentes (Jurista, Auditor, Cronista), no solo al Auditor |
| **Degradación silenciosa** | Si el Scout falla en cualquier iteración, cae automáticamente a RAG estático; la auditoría nunca se interrumpe |
| **config** | Nuevas variables: `AGENTIC_RAG_ENABLED`, `SCOUT_MAX_ITER` (default 2), `SCOUT_MAX_TOKENS` (default 3000) |
| **factory** | Nueva función `crear_scout(llm, retriever, vector_store)` en `factory.py` |
| **orchestrator** | `_rag_estatico()` extraída como función privada; `vector_store` propagado al scope amplio; `auditar_consistencia()` acepta `vector_store=None` (retrocompatible) |

## Novedades v8.8.0

| Área | Cambio |
|------|--------|
| **Retrieve-and-Rerank** | `crear_retriever` ahora usa `CohereRerank(rerank-multilingual-v3.0)` via `ContextualCompressionRetriever`; recupera top-20 candidatos (Hybrid RAG) y reordena a top-K por relevancia real contra la consulta |
| **Pipeline en capas** | Tres capas apiladas en `pipeline.py`: FAISS (base) → BM25+EnsembleRetriever (Hybrid) → Cohere Reranker (final); cada capa degrada silenciosamente a la anterior si falla |
| **Mayor recall** | `k_candidatos = min(k × 5, 20)`: retriever busca 5× más candidatos antes del reranking para maximizar cobertura antes del filtro final |
| **config** | Nueva variable `COHERE_API_KEY` en `config.py`; si está vacía el pipeline funciona sin reranking (modo v8.7) |
| **deps** | `cohere>=5.0.0` y `langchain-cohere>=0.3.0` añadidos a `requirements.txt` |
| **Secret Manager** | Agregar `COHERE_API_KEY` en GCP Secret Manager para activar reranking en producción |

## Novedades v8.7.0

| Área | Cambio |
|------|--------|
| **Hybrid RAG** | `pipeline.py` combina BM25 (`rank_bm25`) + FAISS via `EnsembleRetriever` con RRF (pesos 0.4/0.6); BM25 captura keywords legales exactos ("Ley 30225", "D.S. 344-2018-EF", números de cláusula) que los embeddings no discriminan bien |
| **Hybrid RAG — Retrocompatible** | Cero cambios en callers (orchestrator, contracts_router, query_flow, bot); los docs se almacenan en `vector_store._contractia_docs` y `crear_retriever` los detecta automáticamente |
| **Hybrid RAG — Fallback** | Si `rank_bm25` no está instalado o falla, degradación silenciosa a FAISS puro; la auditoría nunca se interrumpe por esto |
| **deps** | `rank_bm25>=0.2.2` añadido a `requirements.txt` |

## Novedades v8.6.0

| Área | Cambio |
|------|--------|
| **GraphRAG — Prompt CoT + Few-Shot** | `_PROMPT_EXTRACCION` en `graph.py` reescrito con CoT de 5 pasos, ejemplo concreto (few-shot) y bloque `<razonamiento>`; consistente con la calidad de los prompts de los agentes |
| **GraphRAG — Búsqueda regex** | Reemplazado `if cid in str(n)` por regex con word-boundary negativo (`(?<!\d)cid(?!\d)`); evita que "5" matchee "15", "25" o "5.1" — menos falsos contextos |
| **GraphRAG — Profundidad 2** | `obtener_contexto_grafo` usa `nx.ego_graph(radius=2)` en lugar de buscar solo vecinos directos; detecta cadenas `A→B→C` (ej. plazos encadenados entre cláusulas) |
| **GraphRAG — Filtro CONTIENE** | Las aristas jerárquicas `CONTIENE` se omiten del contexto enviado a los agentes; eran ruido estructural sin valor legal |
| **Bot — Selector GraphRAG** | Nuevo paso en el flujo del bot: al elegir Auditoría o Consulta, el usuario ve botones `[🕸️ Sí, con GraphRAG] [⚡ No, solo RAG]` antes de subir el archivo |
| **Bot — GraphRAG en consulta** | `query_flow.py` construye el grafo al indexar si se activa; `responder_pregunta` enriquece automáticamente el prompt con relaciones del grafo cuando la pregunta menciona cláusulas |
| **Bot — GraphRAG en auditoría** | `ejecutar_auditoria` acepta `graph_enabled=True/False`; el caption del informe indica el modo usado |
| **Sesiones bot** | `sessions.py` guarda `grafo` y `mapa_textos` junto al retriever; nuevas funciones `get_grafo()` y `get_mapa_textos()` |

## Novedades v8.5.0

| Área | Cambio |
|------|--------|
| **Seguridad JWT** | Reemplazado `python-jose` (sin mantenimiento desde 2021, CVE activo) por `PyJWT>=2.9.0`; API idéntica para HS256, cero cambios en endpoints |
| **Limpieza deps** | Eliminado `passlib` de `requirements.txt` — el proyecto ya usaba `bcrypt` directamente; sin impacto en comportamiento |
| **Fecha UTC** | `datetime.utcnow()` reemplazado por `datetime.now(timezone.utc)` en `api/auth.py` (deprecado en Python 3.12+) |
| **Agentes — salida estructurada** | `AgenteEspecialista` ahora usa `llm.with_structured_output(schema)` (LangChain + Gemini); elimina el parser regex frágil; los schemas Pydantic ya existentes (`SalidaJurista`, `SalidaAuditor`, `SalidaCronista`) garantizan output válido |
| **Prompts — CoT** | Los tres agentes incorporan árbol de decisión explícito y bloque `<razonamiento>` (Chain-of-Thought); el parser lo ignora automáticamente |
| **Prompts — Few-Shot** | `PROMPT_JURISTA` incluye ejemplo concreto externas vs. internas para reducir falsos positivos |
| **Prompts — Severidad dinámica** | Criterios ALTA/MEDIA/BAJA explícitos en Auditor y Cronista; antes `"ALTA"` era hardcodeado en el template para todos los hallazgos |

## Novedades v8.4.0

| Área | Cambio |
|------|--------|
| **GraphRAG en consulta interactiva** | El modo Consulta ahora incluye selector RAG / GraphRAG igual que el modo Auditoría; el grafo se construye al subir el archivo si se activa la opción |
| **Reutilizar auditoría previa** | Usuarios auditor/admin pueden seleccionar una auditoría anterior como base para consulta interactiva; el texto del contrato se recupera desde DB sin re-subir el archivo |
| **Persistencia texto contrato** | `texto_contrato TEXT` añadido a la tabla `auditorias`; se guarda tras extracción exitosa para reutilización futura |
| **Endpoint `/session/from-audit`** | `POST /contracts/session/from-audit` reconstruye RAG (~10s) y opcionalmente GraphRAG desde el texto almacenado; retorna `session_id` listo para consultas |
| **Fix SafetySetting VertexAI** | Corregido `PydanticUserError` en `langchain_google_vertexai 2.x` al usar `from __future__ import annotations`; `model_rebuild()` ahora recibe namespace completo de `vertexai.generative_models` via `importlib` |
| **Fix aiplatform version** | `google-cloud-aiplatform` cambiado a `!=1.65.0,>=1.38.0` para permitir ≥1.65.1 donde `SafetySetting` es importable correctamente |

## Novedades v8.3.0

| Área | Cambio |
|------|--------|
| **Descarga PDF** | Nuevo endpoint `GET /contracts/audit/{id}/pdf` — genera y descarga el informe como PDF real (fpdf2); botón del frontend usa JWT y descarga directo |
| **Email con PDF** | El email de notificación incluye el informe adjunto en PDF; si la generación del PDF falla, el email se envía igual (sin adjunto) |
| **Progreso PDF** | Extracción de texto PDF muestra "Leyendo página X/N…" para texto embebido y "OCR página X/N…" para escaneos |
| **OCR robusto** | Timeout de 15 s por página en pypdf (ThreadPoolExecutor); si falla → OCR de respaldo para esa página específica; DPI 200→150 (44% más rápido) |
| **Agentes paralelos** | Jurista + Cronista se ejecutan en paralelo (ThreadPoolExecutor); pausa entre secciones 2 s→0.5 s |
| **Reintentos agentes** | Hasta 3 reintentos automáticos con 10 s de pausa si el LLM falla (timeout 600→180 s) |
| **Cloud Run CPU** | `--no-cpu-throttling` en deploy: mantiene CPU activo entre requests para que los `BackgroundTasks` no queden congelados |
| **Bot fix listar usuarios** | Corregido `KeyError` silencioso en "Listar usuarios" del panel admin del bot (`u['id']` vs `u['telegram_id']`) |
| **Dependencias GCP** | `google-cloud-aiplatform` pinado `<1.65.0` para evitar circular import de `ExampleStoreServiceClient` |
| **Límite archivos** | Auditoría rechaza archivos >30 MB (antes sin límite explícito) |

## Novedades v8.2.0

| Área | Cambio |
|------|--------|
| **GraphRAG** | Integración completa al pipeline de auditoría: grafo de conocimiento (networkx) con tripletas extraídas por LLM; fix `KeyError 'texto'` que bloqueaba todas las auditorías |
| **Auditorías** | Estado persistido en tabla PostgreSQL `auditorias` — seguro para multi-instancia Cloud Run |
| **Lock concurrencia** | Reemplaza `asyncio.Semaphore` (en memoria) por `hay_auditoria_en_progreso()` basado en DB; auto-expira en 20 min |
| **Admin — Actividad** | Nueva página `/admin/actividad` con métricas, filtros y tabla de logs por usuario |
| **Admin endpoints** | Nuevos `GET /admin/actividad` y `GET /admin/actividad/resumen` |
| **Logs extendidos** | Tabla `logs` añade `duracion_segundos`, `canal` (bot/web), `n_hallazgos` |
| **Frontend fixes** | `extractError` null-safe, campos `activo` corregidos, auditoría usa multipart |

---

## Arquitectura general

```
contractia.pe (Next.js 14 · Vercel)        Telegram Bot (webhook)
        ↕ HTTPS                                    ↕
api.contractia.pe → Cloud Run (FastAPI · Python) ←─┘
        ↕
   Escudo de Seguridad (Capa 1: Sanitización + Capa 2: Escaneo LLM)
        ↕
   Cloud SQL (PostgreSQL 15 · us-central1)
   └── auditorias (web + bot unificado), logs, prompt_injection_logs
        ↕
   Cloud Storage (GCS)
   ├── contractia-contracts/ (PDFs originales)
   └── graph-cache/ (grafos GraphRAG cacheados, SHA256 key)
        ↕
   FAISS (vectores RAG in-memory)
        ↕
   VertexAI (Gemini 2.5 Pro · text-embedding-004)
        ↕
   GraphRAG (networkx DiGraph · tripletas extraídas por LLM)
        ↕
   Email (Gmail SMTP · PDF adjunto)
```

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Vercel |
| Backend | FastAPI, Python 3.11, Uvicorn |
| Base de datos | PostgreSQL 15 (Cloud SQL) |
| LLM | Gemini 2.5 Pro via VertexAI |
| Embeddings | text-embedding-004 (VertexAI) |
| Vector store | FAISS |
| Auth | JWT (8h, PyJWT), bcrypt, OTP por email |
| Bot | python-telegram-bot (webhook) |
| CI/CD | GitHub Actions → Docker → Artifact Registry → Cloud Run |
| Secretos | GCP Secret Manager |
| DNS | NIC.pe (contractia.pe) |

---

## Estructura del repositorio

```
ContractIA/
├── api/                        ← FastAPI app
│   ├── main.py                 ← Entry point + webhook Telegram
│   ├── auth.py                 ← JWT tokens
│   └── routers/
│       ├── auth_router.py      ← /auth/* (register, verify, login, reset)
│       ├── contracts_router.py ← /contracts/* (upload, query, audit)
│       └── admin_router.py     ← /admin/* (usuarios, roles)
├── contractia/
│   ├── config.py               ← Variables de entorno (+ ADMIN_EMAIL)
│   ├── orchestrator.py         ← Pipeline de auditoría (seguridad + RAG + GraphRAG)
│   ├── agents/                 ← Jurista, Auditor, Cronista
│   ├── core/
│   │   ├── sanitizer.py        ← Capa 1: sanitización Unicode + detección heurística
│   │   ├── security.py         ← Capa 2: escaneo LLM + registro + alerta email
│   │   ├── graph.py            ← GraphRAG (networkx + extracción LLM)
│   │   ├── graph_cache.py      ← Cache de grafos en GCS (SHA256 key, pickle)
│   │   ├── loader.py           ← PDF/DOCX → texto
│   │   ├── segmenter.py        ← Segmentación de cláusulas
│   │   └── report.py           ← Generación de informe Markdown
│   ├── rag/                    ← FAISS pipeline
│   ├── llm/                    ← VertexAI / Ollama provider
│   └── telegram/
│       ├── handler.py          ← Bot handlers + flujo de aprobación
│       ├── db/                 ← database.py, usuarios.py
│       └── correo/             ← sender.py, templates.py, pdf_report.py
├── frontend/                   ← Next.js 14
│   └── src/
│       ├── app/
│       │   ├── page.tsx        ← Landing (/)
│       │   ├── login/          ← /login
│       │   ├── register/       ← /register
│       │   ├── forgot-password/← /forgot-password
│       │   ├── dashboard/      ← /dashboard
│       │   ├── audit/          ← /audit
│       │   └── admin/
│       │       ├── page.tsx    ← /admin (panel)
│       │       └── actividad/  ← /admin/actividad (reportes)
│       ├── components/
│       │   └── Navbar.tsx
│       ├── context/
│       │   └── AuthContext.tsx ← JWT + roles
│       └── lib/
│           └── api.ts          ← Axios client
├── Dockerfile
├── requirements.txt
└── .github/workflows/deploy.yml← CI/CD
```

---

## Endpoints de la API

### Autenticación (`/auth`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/auth/register` | Envía OTP al email para registrarse |
| `POST` | `/auth/verify` | Verifica OTP y crea la cuenta |
| `POST` | `/auth/login` | Login con email + password → JWT |
| `POST` | `/auth/forgot-password` | Envía OTP para resetear contraseña |
| `POST` | `/auth/reset-password` | Actualiza contraseña con OTP |

### Contratos (`/contracts`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/contracts/upload` | Sube PDF/DOCX, vectoriza con FAISS; `graph_enabled=true` construye GraphRAG |
| `POST` | `/contracts/query` | Consulta RAG/GraphRAG sobre el contrato activo |
| `POST` | `/contracts/audit` | Inicia auditoría multi-agente (background) |
| `POST` | `/contracts/session/from-audit` | Crea sesión de consulta desde una auditoría previa (texto en DB) |
| `GET`  | `/contracts/audits` | Historial de auditorías del usuario |
| `GET`  | `/contracts/audit/{id}` | Polling de estado y resultado de auditoría |
| `GET`  | `/contracts/audit/{id}/pdf` | Descarga el informe en PDF |
| `GET`  | `/contracts/audit/{id}/pdf-tecnico` | Descarga el informe técnico en PDF (solo admin) |
| `GET`  | `/contracts/audit/{id}/logs` | Historial de logs de diagnóstico de la auditoría |
| `GET`  | `/contracts/audit/{id}/logs/stream` | Stream SSE de logs en tiempo real (mantenido para integración futura) |
| `PATCH`| `/contracts/audit/{id}/cancelar` | Cancela una auditoría atascada |

### Admin (`/admin`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`  | `/admin/usuarios` | Lista todos los usuarios |
| `PATCH`| `/admin/usuarios/rol` | Cambia el rol de un usuario |
| `PATCH`| `/admin/usuarios/{id}/suspender` | Suspende una cuenta |
| `PATCH`| `/admin/usuarios/{id}/activar` | Activa una cuenta |
| `GET`  | `/admin/actividad` | Logs de actividad filtrados (usuario, fecha, tipo) |
| `GET`  | `/admin/actividad/resumen` | Métricas agregadas (totales, duración promedio, top usuarios) |

---

## Roles de usuario

| Rol | Descripción | Límites |
|-----|-------------|---------|
| `pendiente` | Recién registrado, sin acceso | — |
| `basico` | Usuario aprobado | 10 consultas |
| `auditor` | Acceso a auditorías completas | 3 auditorías · 30 consultas |
| `admin` | Acceso total + panel admin | Ilimitado |

---

## Agentes de auditoría

| Agente | Rol |
|--------|-----|
| **Jurista** | Detecta inconsistencias procedimentales y operativas internas |
| **Auditor** | Valida referencias cruzadas internas (cláusulas y anexos) |
| **Cronista** | Analiza plazos, cronología y errores de cálculo temporal |

**Ejecución:** Los 3 agentes corren en **paralelo** (ThreadPoolExecutor, max_workers=3) para modelos estables; en serie para modelos con cuota limitada (Claude, Gemini 3.1). Limitado a 1 auditoría concurrente via check en DB. Cada agente reintenta hasta 3-5 veces si el LLM falla.

---

## Seguridad — Defensa contra Prompt Injection

Sistema de defensa en 2 capas que analiza los documentos **antes** de que lleguen a los agentes:

| Capa | Tipo | Descripción |
|------|------|-------------|
| **Capa 1** | Programática (sin IA) | Sanitización Unicode (chars invisibles, BOM, homoglyphs) + 7 patrones regex de injection bilingüe (ES/EN) |
| **Capa 2** | Escaneo LLM | Análisis con aislamiento `<documento>`, alertas heurísticas como contexto, output Pydantic, diseño **fail-closed** |

**Si se detecta injection:**
1. Auditoría abortada inmediatamente
2. Registro en tabla `prompt_injection_logs` (PostgreSQL)
3. Email de alerta al administrador (thread separado, no bloqueante)
4. Usuario notificado (web: status "Bloqueado por seguridad" / Telegram: mensaje de alerta)

---

## Flujo de registro web

```
1. Usuario ingresa email → POST /auth/register → llega OTP al correo
2. Ingresa OTP → POST /auth/verify → cuenta creada (rol: pendiente)
3. Admin aprueba desde Telegram o panel /admin → rol cambia a basico/auditor
4. Usuario puede hacer login con email + contraseña enviada al correo
```

---

## CI/CD

Cada `push` a `main` dispara el workflow de GitHub Actions:

```
push → GitHub Actions
  → docker build & push → Artifact Registry
  → gcloud run deploy → Cloud Run (us-central1)

push frontend → Vercel (deploy automático)
```

---

## Desarrollo local

```bash
# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # configurar variables
uvicorn api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev            # http://localhost:3000
```

---

## Variables de entorno requeridas (GCP Secret Manager)

| Secret | Descripción |
|--------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `TELEGRAM_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_ADMIN_ID` | Telegram ID del administrador |
| `EMAIL_PASSWORD` | Password de Google Workspace (admin@contractia.pe) |
| `ADMIN_EMAIL` | Email del administrador para alertas de seguridad (default: admin@contractia.pe) |
| `JWT_SECRET` | Clave secreta para firmar JWT |

---

## Capstone Project II — UTEC

Proyecto de Maestría en Ciencia de Datos e IA · 2025-2026
Dominio: [contractia.pe](https://contractia.pe)
