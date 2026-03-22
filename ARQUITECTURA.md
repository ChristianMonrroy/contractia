# ContractIA — Documento de Arquitectura Técnica
**Versión:** 10.2.0 | **Fecha:** Marzo 2026

---

## 1. ¿Qué es ContractIA?

ContractIA es un sistema de **auditoría inteligente de contratos legales** accesible vía web (contractia.pe) y bot de Telegram. Permite a usuarios autorizados subir un contrato en PDF o DOCX y obtener:

- **Auditoría completa:** análisis multi-agente (Jurista + Auditor + Cronista) que detecta inconsistencias legales, referencias cruzadas rotas y errores en plazos y procesos, enriquecido con RAG y GraphRAG.
- **Consulta interactiva (RAG):** preguntas en lenguaje natural respondidas con base en el contenido del contrato.

---

## 2. Arquitectura General

```
┌──────────────────────────────────────────────────────────────────┐
│                      CANAL WEB (NUEVO)                           │
│                                                                  │
│  contractia.pe (Next.js 14 · Vercel)                            │
│       ↕ HTTPS/JWT                                               │
│  api.contractia.pe → Cloud Run (FastAPI · Python)               │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT                              │
│                                                                  │
│  Usuario → Telegram API → webhook → handler.py                  │
│                                        │                        │
│              Selector GraphRAG (Sí/No) │                        │
│                    ┌───────────────────┤                        │
│                    ▼                   ▼                        │
│             audit_flow.py       query_flow.py                   │
│          (graph_enabled=T/F)  (graph_enabled=T/F)               │
└────────────────────┼───────────────────┼────────────────────────┘
                     │                   │
         ┌───────────▼──────┐    ┌───────▼───────────┐
         │   ORQUESTADOR    │    │   RAG PIPELINE    │
         │  orchestrator.py │    │   pipeline.py     │
         │                  │    │                   │
         │  segmenter.py    │    │  BM25+FAISS (RRF) │
         │  graph.py        │    │  Cohere Reranker  │
         │  scout.py (v9)   │    │  Scout (Agentic)  │
         └────────┬─────────┘    └───────────────────┘
                  │
         ┌────────▼─────────────────────────┐
         │        MULTI-AGENT LAYER         │
         │                                  │
         │  Jurista ─┐                      │
         │  Auditor  ├─ paralelo (3 workers)│
         │  Cronista ┘                      │
         │  (LangChain + PromptTemplate)    │
         │  + contexto GraphRAG             │
         └────────┬─────────────────────────┘
                  │
         ┌────────▼─────────┐
         │   LLM PROVIDER   │
         │  provider.py     │
         │                  │
         │  VertexAI        │
         │  (Gemini 2.5 Pro)│
         │  timeout=600s    │
         └──────────────────┘

┌─────────────────────────────────────┐
│           CAPA DE DATOS             │
│                                     │
│  Cloud SQL — PostgreSQL 15          │
│  ├── usuarios                       │
│  ├── codigos_verificacion (OTP)     │
│  ├── uso_diario (rate limiting)     │
│  ├── logs (+ duracion, canal,       │
│  │        n_hallazgos)              │
│  ├── auditorias (web + bot          │
│  │    unificado desde v9.10)        │
│  └── prompt_injection_logs (v9.9)   │
│                                     │
│  Cloud Storage (GCS)                │
│  ├── contractia-contracts/ (PDFs)   │
│  └── graph-cache/ (grafos GraphRAG  │
│       cacheados, SHA256 key, v9.10) │
│                                     │
│  FAISS en memoria (por sesión RAG)  │
│  GraphRAG: networkx DiGraph         │
│            (en memoria, por audit)  │
└─────────────────────────────────────┘
```

---

## 3. Estructura de Módulos

```
contractia/
├── config.py                   # Variables de entorno centralizadas
├── orchestrator.py             # Pipeline principal (RAG + GraphRAG + Agentes)
│
├── core/
│   ├── sanitizer.py            # Capa 1: sanitización Unicode + detección heurística (v9.9)
│   ├── security.py             # Capa 2: escaneo LLM pre-auditoría + registro + alerta (v9.9)
│   ├── loader.py               # Extracción de texto (PDF/DOCX)
│   ├── log_context.py          # ContextVar para propagación de logs a threads (v9.8)
│   ├── segmenter.py            # Motor regex de segmentación estructural
│   ├── graph.py                # GraphRAG: extracción de tripletas + networkx DiGraph
│   ├── graph_cache.py          # Cache de grafos en GCS (SHA256 key, pickle) (v9.10)
│   └── report.py               # Renderizado del informe Markdown
│
├── agents/
│   ├── base.py                 # Clase AgenteEspecialista + parser JSON robusto
│   ├── factory.py              # Crea los 3 agentes
│   ├── prompts.py              # Prompts de cada agente (PromptTemplate)
│   └── schemas.py              # Esquemas de salida
│
├── llm/
│   └── provider.py             # Construcción del LLM (VertexAI o Ollama)
│
├── rag/
│   └── pipeline.py             # Vector store FAISS + retriever + recuperación
│
└── telegram/
    ├── handler.py              # Router de mensajes (máquina de estados)
    ├── sessions.py             # Sesiones en memoria (autenticación activa)
    ├── auth/crypto.py          # OTP y generación de passwords
    ├── correo/                 # SMTP Gmail + generación de PDF (fpdf2)
    │   ├── sender.py           # Envío vía Gmail SMTP; soporta 2 PDFs adjuntos
    │   ├── templates.py        # HTML templates (verificación, bienvenida, auditoría)
    │   ├── pdf_report.py       # Markdown → PDF auditoría (fpdf2, pure Python)
    │   └── pdf_report_tecnico.py # Informe técnico admin: Fase 0/0.5 + GraphRAG PNG
    ├── db/
    │   ├── database.py         # PostgreSQL, init_db(), auditorias CRUD,
    │   │                       # get_actividad(), get_resumen_actividad()
    │   ├── usuarios.py         # CRUD usuarios (bcrypt)
    │   └── uso.py              # Rate limiting diario por rol
    └── flows/
        ├── audit_flow.py       # Flujo de auditoría completa (bot)
        └── query_flow.py       # Flujo de consulta RAG interactiva (bot)

api/
├── main.py                     # FastAPI entry point + webhook Telegram
├── auth.py                     # JWT tokens (8h)
└── routers/
    ├── auth_router.py          # /auth/* (register, verify, login, reset-password)
    ├── contracts_router.py     # /contracts/* (upload, query, audit, polling, pdf)
    └── admin_router.py         # /admin/* (usuarios, roles, actividad, todas las auditorías)

frontend/
└── src/
    ├── app/
    │   ├── page.tsx            # Landing (/)
    │   ├── login/              # /login
    │   ├── register/           # /register
    │   ├── forgot-password/    # /forgot-password
    │   ├── dashboard/          # /dashboard
    │   ├── audit/              # /audit (auditoría + consulta RAG)
    │   └── admin/
    │       ├── page.tsx        # /admin (panel de usuarios)
    │       ├── actividad/      # /admin/actividad (reportes de uso)
    │       └── auditorias/     # /admin/auditorias (todas las auditorías, tiempo real)
    ├── components/Navbar.tsx
    ├── context/AuthContext.tsx  # JWT + roles (isAdmin, isAuthenticated)
    └── lib/api.ts               # Axios client (authAPI, contractsAPI, adminAPI);
                                 # interfaces AuditRow, AdminAuditRow, ActividadRow
```

---

## 3.1. Responsabilidades de Cada Módulo

### `contractia/config.py`
Punto único de configuración. Lee todas las variables de entorno (`.env` o Secret Manager) y las expone como atributos tipados. Cualquier módulo que necesite un parámetro (modelo LLM, tamaño de chunk, token de Telegram, etc.) lo importa desde aquí. Centralizar la configuración evita valores hardcodeados dispersos en el código.

---

### `contractia/orchestrator.py`
**Cerebro del pipeline de auditoría.** Coordina la ejecución completa:
1. **Escudo de seguridad (v9.9):** Sanitiza el texto (Capa 1) y lo escanea con el LLM (Capa 2). Si detecta prompt injection, lanza `PromptInjectionDetectedError`, registra en DB y alerta al admin por email.
2. Segmenta el texto en secciones.
3. Emite logs de **FASE 0** (estructura: N capítulos / M anexos) y **FASE 0.5** (índice global de cláusulas y anexos).
4. Construye el vector store RAG (para consultas interactivas) y (opcionalmente) el grafo GraphRAG.
5. Itera sobre cada sección llamando a `auditar_consistencia()`, emitiendo log por sección con conteo de hallazgos. **Los agentes reciben solo `texto_seccion` + `contexto_grafo` (v9.11)** — RAG y Scout no participan en auditoría para evitar ruido que reduce hallazgos.
6. Devuelve el diccionario de resultados completo que luego se convierte en informe.

---

### `contractia/core/`

| Archivo | Responsabilidad |
|---------|----------------|
| `sanitizer.py` | **Capa 1 de seguridad (v9.9).** Filtros determinísticos sin LLM: elimina caracteres Unicode invisibles (zero-width spaces U+200B/200C/200D, BOM U+FEFF, soft hyphens U+00AD, directional marks, control chars), normaliza a NFC para prevenir homoglyphs, y detecta 7 patrones heurísticos de prompt injection bilingüe (ES/EN) por regex. Retorna `ResultadoSanitizacion(texto_limpio, alertas, chars_eliminados)`. Las alertas no bloquean — se pasan a Capa 2 como contexto para el LLM. |
| `security.py` | **Capa 2 de seguridad (v9.9).** Escaneo LLM pre-auditoría con diseño **fail-closed** (excepción → documento inseguro). El texto se envuelve en etiquetas `<documento>` con instrucción explícita de no obedecer contenido interno. Recibe las alertas heurísticas de Capa 1 como pistas. Output estructurado con Pydantic (`es_seguro: bool, evidencia: str, confianza: float`). Distingue falsos positivos (cláusulas imperativas normales vs. comandos dirigidos a la IA). Si detecta injection: registra en tabla `prompt_injection_logs` via `registrar_prompt_injection()` y envía email de alerta al admin en thread separado (no bloqueante). |
| `loader.py` | Extrae texto plano de archivos PDF (pypdf, con OCR por página como fallback vía pytesseract) y DOCX (docx2txt). Aplica timeout por página para evitar bloqueos en PDFs grandes. |
| `log_context.py` | Módulo de logging agéntico (v9.8). Define un `ContextVar[Callable]` que propaga automáticamente el callback de logs a todos los threads lanzados por `ThreadPoolExecutor` sin modificar las firmas de las funciones del pipeline. `set_log_callback(cb)` activa la captura; `log(msg)` imprime y llama al callback si está registrado. |
| `segmenter.py` | Divide el texto en secciones estructurales usando regex (capítulos, cláusulas, anexos). Construye el índice global de cláusulas numeradas y detecta saltos en la secuencia. `construir_mapa_clausula_a_seccion()` usa "Segmentación por Diccionario Exacto" (alineado con notebook vs16): localiza la posición exacta de cada cláusula y extrae solo su texto hasta la siguiente, no el capítulo completo. Nueva función `separar_en_secciones_con_metadata()` retorna también los datos de Fase 0/0.5 (para el informe técnico admin). |
| `graph.py` | Construye el grafo de conocimiento GraphRAG. Emite log FASE 1.5 al inicio. Para cada sección llama al LLM con un prompt que extrae tripletas (origen, relación, destino). Las almacena en un `nx.DiGraph`. Acepta `on_progress` callback para reportar avance por sección al panel de diagnóstico web (v9.10). `obtener_contexto_grafo()` recupera el texto preciso de cada cláusula referenciada directamente desde `mapa_textos` (sin truncado ni búsqueda posicional, alineado con vs16); relación por defecto `CONECTA_CON`. |
| `graph_cache.py` | **(v9.10)** Cache de grafos GraphRAG en GCS. `cache_key(texto, prompt)` genera SHA256 hash como identificador único. `guardar_grafo(key, grafo, mapa)` serializa con pickle y sube a GCS. `cargar_grafo(key)` recupera el grafo cacheado. `borrar_grafo(key)` elimina cache manualmente. Ahorra ~40 min de reconstrucción por auditoría. Bucket configurable vía `AUDIT_QUEUE_BUCKET`. |
| `report.py` | Transforma el diccionario de resultados del orquestador en un informe Markdown legible, agrupando hallazgos por sección y añadiendo resumen ejecutivo. |

---

### `contractia/agents/`

| Archivo | Responsabilidad |
|---------|----------------|
| `base.py` | Define `AgenteEspecialista`: wrapper que combina un `PromptTemplate` con el LLM y devuelve la salida parseada. Incluye `parse_json_seguro()` para manejar JSON malformado del LLM (comas extra, bloques markdown, comentarios). |
| `prompts.py` | Contiene los tres `PromptTemplate` de los agentes (Jurista, Auditor, Cronista). Estructura alineada con notebook vs16: `# SISTEMA / Motor automatizado...` + `# REGLAS DE PROCESAMIENTO` con ENFOQUE ESTRICTO, EXCLUSIÓN LEGAL, LÓGICA NO LINEAL (Jurista), JERARQUÍA DOCUMENTAL (Auditor), SUSPENSIÓN DE PLAZOS (Cronista), LÍMITES DEL SISTEMA y PARÁMETRO TEMPORAL. Adiciones propias de ContractIA: `{contexto_rag}` y `TIPOS PERMITIDOS` por agente. |
| `schemas.py` | Define los esquemas Pydantic de salida (`SalidaJurista`, `SalidaAuditor`, `SalidaCronista`). Usados con `with_structured_output()` para garantizar JSON válido sin parser regex. |
| `factory.py` | Funciones de fábrica (`crear_jurista()`, `crear_auditor()`, `crear_cronista()`) que instancian `AgenteEspecialista` con el prompt y schema correctos. Desacopla la creación del uso. |

---

### `contractia/llm/provider.py`
Construye y devuelve el objeto LLM según `LLM_PROVIDER` en config. Si es `vertexai`, inicializa `ChatVertexAI` con el modelo Gemini configurado. Si es `ollama`, inicializa `ChatOllama`. El resto del sistema usa el objeto LLM sin saber qué backend hay detrás.

---

### `contractia/rag/pipeline.py`
Implementa el pipeline RAG completo:
- **`crear_vector_store()`**: divide secciones en chunks con `RecursiveCharacterTextSplitter`, genera embeddings con VertexAI `text-embedding-004`, construye índice FAISS en memoria.
- **`crear_retriever_hibrido()`**: combina BM25 (léxico) + FAISS (semántico) con fusión RRF sobre los top-20 candidatos; Cohere Reranker filtra al top-K final.
- **`recuperar_contexto()`**: ejecuta la búsqueda y devuelve el texto de los fragmentos más relevantes como string listo para insertar en el prompt.
- **`buscar_clausula()`**: búsqueda directa por número de cláusula (usado por el Agente Scout).

---

### `contractia/telegram/`

| Archivo/Carpeta | Responsabilidad |
|-----------------|----------------|
| `handler.py` | Router principal del bot. Implementa una máquina de estados por usuario: maneja comandos (`/start`, `/help`), botones de aprobación de admin, selector RAG/GraphRAG y delega a `audit_flow.py` o `query_flow.py`. |
| `sessions.py` | Diccionario en memoria de sesiones activas por `user_id`. Almacena el texto del contrato, el vector store, el grafo y el tiempo de última actividad. Expira sesiones tras 8 horas. |
| `auth/crypto.py` | Genera OTPs de 6 dígitos y contraseñas seguras aleatorias para el flujo de registro por email. |
| `correo/sender.py` | Envía emails vía Gmail SMTP (soporte adjunto PDF). |
| `correo/templates.py` | HTML templates de los correos (verificación OTP, bienvenida, notificación de auditoría, alerta de prompt injection). |
| `correo/pdf_report.py` | Convierte el informe Markdown a PDF usando fpdf2 (Python puro, sin dependencias nativas). |
| `db/database.py` | Wrapper de psycopg2 con `get_conn()` como context manager. Expone `init_db()` (crea tablas si no existen), CRUD de auditorías y `registrar_prompt_injection()` para la tabla dedicada de seguridad. |
| `db/usuarios.py` | CRUD de la tabla `usuarios`: crear, buscar por email/telegram_id, actualizar rol, hashear/verificar contraseñas con bcrypt. |
| `db/uso.py` | Rate limiting diario: registra y consulta el número de auditorías/preguntas por usuario por día según su rol. |
| `flows/audit_flow.py` | Orquesta el flujo completo de auditoría en el bot: descarga el archivo, extrae texto, verifica cache de grafo (pregunta "Reutilizar/Reconstruir" si existe), llama al orquestador, registra en tabla `auditorias` (visible en panel admin, v9.10), envía el informe `.md` como adjunto al chat y envía email con PDF adjunto al usuario (v9.10). |
| `flows/query_flow.py` | Maneja la consulta RAG interactiva en el bot: indexa el contrato en la sesión del usuario (si aún no está), recupera contexto, llama al LLM con el prompt de consulta y responde al usuario en el chat. |

---

### `api/`

| Archivo | Responsabilidad |
|---------|----------------|
| `main.py` | Entry point de FastAPI. Registra los routers, configura CORS, monta el endpoint de webhook de Telegram y arranca la inicialización de la DB al levantar. |
| `auth.py` | Generación y verificación de tokens JWT (HS256, 8h). Dependencia `get_current_user()` usada en todas las rutas protegidas. |
| `routers/auth_router.py` | Endpoints `/auth/*`: registro con OTP por email, verificación, login, reset de contraseña. |
| `routers/contracts_router.py` | Endpoints `/contracts/*`: subir contrato, abrir sesión RAG, consulta interactiva, lanzar auditoría (como `BackgroundTask`), polling de progreso, descarga PDF. `GET /audit/{id}/pdf-tecnico` (solo admin): reconstruye grafo, genera PNG y PDF técnico on-the-fly. `GET /audit/{id}/logs`: historial de logs de diagnóstico (JSON). `GET /audit/{id}/logs/stream`: stream SSE de logs en tiempo real. En `_run_audit` activa `set_log_callback()` para capturar todos los `log()` del pipeline y persistirlos en la columna `audit_logs` de la DB. |
| `routers/admin_router.py` | Endpoints `/admin/*`: listar usuarios, cambiar roles, ver logs de actividad y resumen de uso. Solo accesible con rol `admin`. |

---

### `frontend/`

| Archivo/Carpeta | Responsabilidad |
|-----------------|----------------|
| `app/page.tsx` | Landing pública con descripción del producto. |
| `app/login/` · `app/register/` · `app/forgot-password/` | Flujos de autenticación: formularios que llaman a `authAPI`. |
| `app/dashboard/` | Vista principal post-login: acceso rápido a auditoría y consulta. |
| `app/audit/` | Página central: subida de archivo, selector de modelo (Gemini 2.5/3.1, Claude Sonnet/Opus), selector de modo (RAG/GraphRAG), polling de progreso en tiempo real, panel "DIAGNÓSTICO EN VIVO" (polling cada 5s a `/audit/{id}/logs`), tab "Diagnóstico técnico" con terminal monoespacio y color-coding al finalizar, visualización del informe en Markdown y descarga PDF. |
| `app/admin/` | Panel de administración: gestión de usuarios y roles; `/admin/actividad` con métricas de uso. |
| `context/AuthContext.tsx` | Context global de React que almacena el JWT, el rol y expone `isAdmin`, `isAuthenticated`. Intercepta respuestas 401 para redirigir a login. |
| `lib/api.ts` | Cliente Axios con base URL configurada. Expone `authAPI`, `contractsAPI` y `adminAPI` como objetos con métodos tipados. |

---

## 4. Pipeline de Auditoría — Paso a Paso

```
PDF/DOCX
   │
   ▼
[1] EXTRACCIÓN DE TEXTO
    loader.py → pypdf (página a página, con progreso "Leyendo pág X/N")
              → timeout 15 s por página (ThreadPoolExecutor)
              → OCR fallback por página si pypdf falla (pytesseract, DPI 150)
              → docx2txt para DOCX

   │
   ▼
[1.5] ESCUDO DE SEGURIDAD (v9.9)
    ├── CAPA 1: sanitizer.py
    │   ├── Elimina chars Unicode invisibles (zero-width, BOM, directional)
    │   ├── Normaliza a NFC (previene homoglyphs)
    │   └── Detecta 7 patrones heurísticos de injection (regex bilingüe)
    │       Resultado: (texto_limpio, alertas) — las alertas no bloquean
    │
    └── CAPA 2: security.py
        ├── LLM analiza texto con aislamiento <documento>
        ├── Recibe alertas de Capa 1 como contexto
        ├── Output Pydantic: {es_seguro, evidencia, confianza}
        ├── Diseño FAIL-CLOSED: excepción → documento inseguro
        │
        └── Si es_seguro=False:
            ├── INSERT en prompt_injection_logs (DB)
            ├── Email alerta al admin (thread separado)
            └── Lanza PromptInjectionDetectedError → auditoría abortada

   │
   ▼
[2] SEGMENTACIÓN ESTRUCTURAL (regex, sin LLM)
    segmenter.py
    ├── Detecta CAPÍTULOS y ANEXOS con patrones regex
    ├── Construye índice global de cláusulas (ej: 5.1, 10.3.2)
    ├── Valida secuencias de cláusulas (detecta saltos)
    └── Resultado: lista de secciones con metadata

   │
   ▼
[3] CONSTRUCCIÓN DEL VECTOR STORE RAG
    pipeline.py
    ├── Divide secciones en chunks (1500 chars, overlap 200)
    ├── Genera embeddings con VertexAI text-embedding-004
    ├── Construye índice FAISS en memoria
    └── Crea retriever (similarity search, top-k=1)

   │
   ▼
[4] CONSTRUCCIÓN DEL GRAFO DE CONOCIMIENTO (GraphRAG)
    graph.py + graph_cache.py
    ├── Verifica cache en GCS (SHA256 del texto + prompt)
    │   Bot: pregunta "Reutilizar/Reconstruir" si hay cache
    │   Web-auditoría: siempre reconstruye, actualiza cache
    │   Web-consultas: lee cache si existe
    ├── Para cada sección, llama al LLM para extraer tripletas
    │   (origen, relación, destino, contexto)
    ├── Reporta progreso por sección al panel diagnóstico web (v9.10)
    ├── Relaciones válidas: REFERENCIA_A, SE_RIGE_POR,
    │   ESTABLECE_PLAZO, MODIFICA_A, DEPENDE_DE
    ├── Construye nx.DiGraph con nodos de entidades
    ├── Guarda grafo en GCS para reutilización futura
    └── Permite navegar dependencias entre cláusulas

   │
   ▼
[5] AUDITORÍA MULTI-AGENTE (por cada sección)
    orchestrator.py → auditar_consistencia()
    │
    ├── [PARALELO] AGENTE JURISTA  ──┐
    │   Input:  texto + contexto grafo │ ThreadPoolExecutor(max_workers=3)
    │   Output: {hay_inconsistencias, hallazgos[]} │ (independientes entre sí)
    │                                               │
    ├── [PARALELO] AGENTE AUDITOR  ─────────────────┤
    │   Input:  texto + contexto grafo + índices    │
    │   Output: {hay_inconsistencias, hallazgos[]}  │
    │                                               │
    └── [PARALELO] AGENTE CRONISTA ─────────────────┘
        Input:  texto + contexto grafo
        Output: {hay_errores_logicos, hay_inconsistencia_plazos, hallazgos_procesos[]}

    NOTA (v9.11): RAG y Scout deshabilitados en auditoría — solo GraphRAG provee
    contexto inter-sección. RAG introducía ruido que reducía hallazgos ~35% vs notebook.

    Modelos estables (Gemini 2.5 Pro): 3 workers, 3 reintentos, 10s pausa, 2s entre secciones
    Modelos throttle (Gemini 3.1, Claude): 1 worker, 5 reintentos, 30s pausa, 10s entre secciones

   │
   ▼
[6] GENERACIÓN DEL INFORME
    report.py → Markdown con todos los hallazgos agrupados por cláusula

   │
   ▼
[7] PERSISTENCIA Y ENTREGA
    Bot Telegram → archivo .md adjunto al chat + email con PDF adjunto (v9.10)
                 → registra en tabla auditorias (visible en panel admin, v9.10)
    Web → polling GET /contracts/audit/{id} → informe renderizado en Markdown
        → GET /contracts/audit/{id}/pdf → PDF generado con fpdf2 (descarga directa)
        → GET /contracts/audit/{id}/logs → historial de logs de diagnóstico (JSON)
    Email → notificación automática con PDF adjunto al terminar (web + bot unificado)
    DB  → tabla auditorias (status, informe, n_hallazgos, n_secciones, progress_msg,
                            progress_pct, audit_logs JSONB, modelo_usado)
    GCS → graph-cache/ (grafos GraphRAG cacheados para reutilización, v9.10)
```

### Pausa técnica entre secciones
El orquestador incluye `time.sleep(2)` entre secciones para modelos estables (Gemini 2.5 Pro) y `time.sleep(10)` para modelos con cuota limitada (Gemini 3.1, Claude).

---

## 5. RAG Implementado

**Tipo:** RAG Naive / Standard + GraphRAG como contexto complementario.

| Característica | Valor |
|---|---|
| Estrategia de chunking | `RecursiveCharacterTextSplitter` con separadores legales |
| Tamaño de chunk | 1500 caracteres, overlap 200 |
| Modelo de embeddings | `text-embedding-004` (VertexAI) |
| Vector store | **FAISS** (en memoria, por sesión) |
| Estrategia de búsqueda | **Hybrid RAG + Reranking**: BM25+FAISS/RRF recuperan top-20 candidatos; Cohere `rerank-multilingual-v3.0` reordena a top-K por relevancia real |
| Metadata por chunk | título de sección, tipo, número, índice de chunk |
| Uso del RAG en auditoría | **Deshabilitado (v9.11)** — los agentes solo reciben `texto_seccion` + `contexto_grafo`; RAG introducía ruido que reducía hallazgos en ~35% vs notebook |
| Uso del RAG en consulta | Preguntas libres del usuario vía `/contracts/query` (activo) |
| Persistencia del vector store | No persiste — se reconstruye por cada contrato cargado |

### GraphRAG (v8.6.0+)

| Característica | Valor |
|---|---|
| Tecnología | `networkx.DiGraph` |
| Extracción de tripletas | LLM (Gemini 3.1 Pro Preview) por sección con prompt CoT + Few-Shot |
| Tipos de relación | REFERENCIA_A, SE_RIGE_POR, ESTABLECE_PLAZO, MODIFICA_A, DEPENDE_DE |
| Búsqueda de nodos | Regex con word-boundary (`(?<!\d)cid(?!\d)`) — evita falsos positivos por substring |
| Profundidad de consulta | `nx.ego_graph(radius=2)` — detecta cadenas A→B→C, no solo vecinos directos |
| Aristas CONTIENE | Excluidas del contexto enviado a los agentes (ruido estructural) |
| Uso web | Los 3 agentes reciben `contexto_grafo`; consulta interactiva enriquece prompt si hay grafo en sesión |
| Uso bot | Selector `[🕸️ Sí, con GraphRAG] [⚡ No, solo RAG]` antes de subir el archivo; soportado en auditoría y consulta |
| Cache GCS (v9.10) | Grafos se cachean en `gs://contractia-contracts/graph-cache/{sha256}.pkl`; key = SHA256(texto + prompt); Bot: pregunta "Reutilizar/Reconstruir" si detecta cache; Web-auditoría: siempre reconstruye y actualiza cache; Web-consultas: lee cache |
| Comando `/rebuild_graph` | Permite al usuario del bot reconstruir manualmente el grafo cacheado del contrato activo |
| Persistencia | Cache en GCS (entre sesiones); en memoria por auditoría (web) o por sesión de usuario (bot) |

---

## 6. Sistema Multi-Agente

**Patrón:** Parallel Agents con contexto compartido (GraphRAG). Los 3 agentes son independientes y se ejecutan en paralelo (serie para modelos con cuota limitada). RAG deshabilitado en auditoría desde v9.11 — solo GraphRAG proporciona contexto inter-sección.

| Agente | Rol | Input principal | Output |
|---|---|---|---|
| **Jurista** | Detecta inconsistencias procedimentales y operativas | Texto + contexto grafo + RAG | `SalidaJurista`: hallazgos de tipo `INCONSISTENCIA_PROCEDIMENTAL` |
| **Auditor** | Valida referencias cruzadas internas | Texto + contexto RAG + índices + grafo | `SalidaAuditor`: hallazgos de tipo `REFERENCIA_INEXISTENTE` o `REFERENCIA_ROTA` |
| **Cronista** | Analiza plazos y errores de cálculo temporal | Texto + contexto grafo + RAG | `SalidaCronista`: hallazgos de tipo `ERROR_PLAZOS` o `ERROR_LOGICO` |

**Técnicas de Prompt Engineering aplicadas:**

| Técnica | Agente(s) | Descripción |
|---|---|---|
| **Chain-of-Thought (CoT)** | Jurista, Auditor, Cronista | Bloque `<razonamiento>` con pasos explícitos antes del output; el parser lo ignora en producción |
| **Few-Shot** | Jurista | Ejemplo concreto de referencia externa vs. interna para reducir falsos positivos |
| **Árbol de decisión** | Auditor | Pasos explícitos por cada referencia: VALIDACIÓN DE ÍNDICE → VALIDACIÓN TEMÁTICA → descartar plazos/montos distintos del mismo tema |
| **Severidad dinámica** | Auditor, Cronista | Criterios ALTA/MEDIA/BAJA explícitos en el prompt |
| **Conciencia temporal** | Jurista, Auditor, Cronista | `{fecha_actual}` inyectada como PARÁMETRO TEMPORAL; detecta plazos vencidos y fechas ilógicas |
| **Prohibición de externalidades** | Auditor, Cronista | EXCLUSIÓN LEGAL / EXCLUSIÓN DE LEYES EXTERNAS: no marcar como error las citas a leyes externas |
| **Días = hábiles (por defecto)** | Cronista | CONSTANTES DE TIEMPO: asume `Días`=hábiles, `Días Calendario`=naturales sin exigir definición explícita |
| **Lógica no lineal** | Jurista | LÓGICA NO LINEAL (v9.7.0): cláusulas paralelas/alternativas/preventivas no se marcan como contradictorias |
| **Jerarquía documental** | Auditor | JERARQUÍA DOCUMENTAL (v9.7.0): Apéndices pertenecen a Anexos, no se exigen en el índice global |
| **Suspensión de plazos** | Cronista | SUSPENSIÓN DE PLAZOS (v9.7.0): días de subsanación del Concesionario no se suman al plazo de evaluación del Concedente |

Los agentes usan `LangChain PromptTemplate | LLM.with_structured_output(schema)` (v8.5.0). El schema Pydantic correspondiente (`SalidaJurista`, `SalidaAuditor`, `SalidaCronista`) garantiza salida válida sin parser regex. Si `with_structured_output` no está disponible (ej. backend Ollama), el `AgenteEspecialista` cae a `StrOutputParser` + `parse_json_seguro` como fallback.

---

## 7. Modelo de Roles y Autenticación

**Registro web:** Email → OTP (6 dígitos, 10 min) → contraseña autogenerada → JWT (8h).

**Roles:**

| Rol | Auditorías/día | Preguntas/día | Notas |
|---|---|---|---|
| `pendiente` | 0 | 0 | Espera aprobación del admin |
| `basico` | 0 | 10 | Solo consultas RAG |
| `auditor` | 3 | 30 | Auditorías completas + consultas |
| `admin` | ∞ | ∞ | Panel admin + reportes de actividad |

**Flujo de aprobación:** nuevo usuario → admin recibe notificación en Telegram con botones → asigna rol → usuario notificado por email.

**Seguridad:**
- Passwords hasheados con **bcrypt**
- JWT firmados con **PyJWT>=2.9.0** (reemplazó `python-jose` en v8.5.0 por CVE activo); algoritmo HS256; secreto en GCP Secret Manager
- Tokens en cookies (js-cookie), interceptor axios para inyección automática
- Redirect a `/login` en respuestas 401
- **Defensa contra prompt injection** en 2 capas (v9.9): sanitización programática + escaneo LLM pre-auditoría con diseño fail-closed (ver sección 7.1)

---

## 7.1. Defensa contra Prompt Injection (v9.9)

ContractIA procesa documentos subidos por usuarios que se inyectan directamente en prompts de LLM. Un documento malicioso podría contener instrucciones ocultas para manipular a los agentes. El sistema implementa defensa en 2 capas:

### Capa 1 — Sanitización Programática (`core/sanitizer.py`)

Filtros determinísticos que se ejecutan **sin LLM**, antes de cualquier llamada a IA:

| Filtro | Descripción |
|--------|-------------|
| Chars invisibles | Elimina 15+ tipos de caracteres Unicode invisibles: zero-width spaces (U+200B/C/D), BOM (U+FEFF), soft hyphens (U+00AD), directional marks (U+200E/F, U+202A-E), word joiners (U+2060-64), y todos los caracteres de categoría Unicode "C" (control) excepto `\n`, `\r`, `\t` |
| Normalización NFC | Convierte a forma canónica NFC para prevenir bypass por descomposición Unicode (homoglyphs) |
| Detección heurística | 7 patrones regex bilingües (ES/EN): ignorar instrucciones, cambiar identidad/rol, referencia a system prompt, exfiltración de configuración, modo debug/bypass, omitir análisis, forzar resultado específico |

**Output:** `ResultadoSanitizacion(texto_limpio, alertas, chars_eliminados)`. Las alertas **no bloquean** — se pasan a Capa 2 como contexto.

### Capa 2 — Escaneo LLM Pre-Auditoría (`core/security.py`)

El LLM analiza el texto completo del contrato como **datos**, no como instrucciones:

| Aspecto | Implementación |
|---------|---------------|
| Aislamiento | Texto envuelto en `<documento>...</documento>` con instrucción explícita de no obedecer contenido interno |
| Contexto | Las alertas heurísticas de Capa 1 se pasan al LLM como pistas ("El análisis previo detectó estos patrones sospechosos...") |
| Falsos positivos | Cláusulas imperativas normales ("El Concesionario deberá...") NO son injection; solo se detectan comandos dirigidos a la IA |
| Output | Pydantic: `SalidaSeguridad(es_seguro: bool, evidencia: str, confianza: float)` |
| Diseño | **Fail-closed**: si hay excepción → `es_seguro=False` (a diferencia del notebook que era fail-open) |

### Respuesta ante detección

Cuando `es_seguro=False`:

1. **Registro en DB:** INSERT en tabla dedicada `prompt_injection_logs` con `audit_id`, `user_id`, `filename`, `evidencia_llm`, `alertas_heuristicas` (JSON), `texto_sospechoso`, `confianza`, `detected_at`
2. **Alerta por correo:** Email al `ADMIN_EMAIL` con template rojo/alerta (`email_alerta_injection`); enviado en `threading.Thread` separado (no bloquea el flujo)
3. **Excepción:** `PromptInjectionDetectedError` propagada al caller
4. **API:** Auditoría marcada como `status="error"`, `progress_msg="Bloqueado por seguridad"`
5. **Bot Telegram:** Mensaje de alerta al usuario informando que el documento fue rechazado

### Consulta de historial

```sql
-- Ver todos los intentos de injection
SELECT * FROM prompt_injection_logs ORDER BY detected_at DESC;

-- Filtrar por usuario
SELECT * FROM prompt_injection_logs WHERE user_id = 123456;

-- Contar intentos por archivo
SELECT filename, COUNT(*) FROM prompt_injection_logs GROUP BY filename;
```

---

## 8. LLM y Proveedores

| Proveedor | Modelo | Uso |
|---|---|---|
| `vertexai` | Gemini 2.5 Pro | Producción (default) |
| `vertexai` | Gemini 3.1 Pro Preview | Producción (throttle: agentes serie, 10s pausa, GraphRAG 8s) |
| `vertexai` (Model Garden `us-east5`) | Claude Sonnet 4.6 | Admin — throttle activo; Scout omitido por cuota |
| `vertexai` (Model Garden `us-east5`) | Claude Opus 4.6 | Admin — throttle activo; Scout omitido por cuota |
| `ollama` | deepseek-r1:8b / qwen3:8b | Desarrollo local |

---

## 9. Concurrencia y Persistencia de Auditorías

- **Bot:** single-process, asyncio, webhook mode
- **Auditorías:** limitadas a 1 simultánea por `hay_auditoria_en_progreso()` — check en DB (auto-expira en 20 min), seguro para multi-instancia Cloud Run
- **Estado de auditoría:** persistido en tabla `auditorias` (PostgreSQL), no en memoria; unificado para web y bot desde v9.10
- **Polling web:** frontend hace GET `/contracts/audit/{id}` cada 4s hasta `status=done|error`; `progress_msg` y `progress_pct` actualizados en DB en tiempo real
- **Preguntas RAG:** concurrentes sin límite

---

## 10. Base de Datos — Esquema

```sql
usuarios          (telegram_id PK, email UNIQUE, password_hash, rol, activo, fecha_registro)
codigos_verificacion (id, telegram_id, codigo, expira_en, usado)
uso_diario        (id, telegram_id, fecha, auditorias, preguntas, UNIQUE(telegram_id,fecha))
logs              (id, telegram_id, accion, detalle, timestamp,
                   duracion_segundos, canal TEXT DEFAULT 'bot', n_hallazgos)
auditorias        (audit_id PK, user_id, status, informe, n_hallazgos,
                   n_secciones, error_detail, progress_msg, progress_pct,
                   filename, graph_enabled, texto_contrato,
                   metadata_tecnica TEXT,   -- JSON Fase 0/0.5 (solo admins)
                   graph_data TEXT,         -- JSON nx.node_link_data (solo admins)
                   audit_logs JSONB,        -- [{ts, nivel, msg}] logs de diagnóstico (v9.8)
                   modelo_usado TEXT,       -- modelo LLM seleccionado
                   created_at, updated_at)
prompt_injection_logs (id, audit_id, user_id, filename,   -- v9.9: registro de ataques
                   detected_at TIMESTAMPTZ,
                   evidencia_llm TEXT,          -- descripción del LLM
                   alertas_heuristicas TEXT,    -- JSON array de patrones Capa 1
                   texto_sospechoso TEXT,       -- fragmento detectado
                   confianza FLOAT)             -- score 0.0-1.0
```

---

## 11. CI/CD y Despliegue

```
git push origin main
        │
        ▼
GitHub Actions (.github/workflows/deploy.yml)
        ├── docker build
        ├── docker push → Artifact Registry (us-central1)
        └── gcloud run deploy → Cloud Run (contractia-api · us-central1)

git push frontend → Vercel (deploy automático)
```

**Infraestructura GCP:**
| Servicio | Recurso |
|---|---|
| Compute | Cloud Run (contractia-api · us-central1 · `--no-cpu-throttling`) |
| Base de datos | Cloud SQL PostgreSQL 15 (contractia-db) |
| Almacenamiento | Cloud Storage (contractia-contracts · PDFs + graph-cache) |
| Imágenes Docker | Artifact Registry (us-central1) |
| Secretos | Secret Manager |
| IAM | Service Account contractia-sa (Workload Identity Federation) |

> **`--no-cpu-throttling`** (v8.3.0): mantiene CPU activo entre requests, necesario para que los `BackgroundTasks` de FastAPI (auditorías) se ejecuten sin congelarse.

---

## 12. Preguntas para el Profesor

### Sobre el diseño multi-agente

**P1.** El sistema usa tres agentes especializados que se ejecutan **secuencialmente**. Con la integración de GraphRAG, los agentes ahora tienen acceso a relaciones entre cláusulas. ¿Sería más adecuado un diseño **reflexivo** (agente supervisor que revisa hallazgos) o mantener la secuencia actual? ¿Qué frameworks (LangGraph, CrewAI) considera más pertinente para este dominio?

**P2.** Los agentes no tienen **memoria inter-sección**: cada sección se analiza de forma independiente. ¿Deberíamos acumular hallazgos previos como contexto para secciones siguientes?

### Sobre el RAG y GraphRAG

**P3.** El sistema combina **Hybrid RAG** (BM25 + FAISS/RRF) con **GraphRAG** (networkx + tripletas). ¿Qué peso relativo deberían tener ambos tipos de contexto en los prompts? ¿Existe evidencia de que GraphRAG supera a Hybrid RAG en documentos legales con cláusulas interdependientes, o se complementan de forma aditiva?

**P4.** Los chunks se generan por tamaño con separadores legales. ¿Sería más efectivo un chunking **semántico** por cláusula completa (cada cláusula como chunk unitario)?

**P5.** El vector store FAISS **no persiste entre sesiones**. ¿Tiene sentido persistir vectores para análisis comparativo entre versiones del mismo contrato?

### Sobre escalabilidad

**P6.** El sistema corre en Cloud Run con instancias efímeras. El lock de concurrencia es DB-based (auto-expira). Para auditorías muy largas (> 20 min), ¿se recomienda migrar a una arquitectura de **cola de tareas** (Cloud Tasks + Cloud Run Jobs)?

**P7.** El FAISS vive en memoria RAM por sesión. Con muchos usuarios concurrentes, ¿es más adecuado migrar a un vector store gestionado (Vertex AI Vector Search, pgvector) o limitar el tiempo de vida de la sesión RAG?

### Sobre el dominio legal

**P8.** Los prompts están optimizados para contratos de concesión (infraestructura pública). ¿Qué tan transferible es este diseño a otros tipos (laborales, comerciales)? ¿Debería haber un agente de **clasificación de tipo de contrato** antes del pipeline?

**P9.** El Agente Cronista diferencia "Días" (hábiles) vs "Días Calendario" (marco legal peruano). ¿Debería esta lógica migrar a una **ontología de plazos legales** consultada vía RAG?
