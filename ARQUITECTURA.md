# ContractIA — Documento de Arquitectura Técnica
**Versión:** 9.1.0 | **Fecha:** Marzo 2026

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
         │  Jurista → Auditor → Cronista    │
         │  (LangChain + PromptTemplate)    │
         │  + contexto RAG + GraphRAG       │
         └────────┬─────────────────────────┘
                  │
         ┌────────▼─────────┐
         │   LLM PROVIDER   │
         │  provider.py     │
         │                  │
         │  VertexAI        │
         │  (Gemini 2.5 Pro)│
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
│  └── auditorias (estado, informe)   │
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
│   ├── loader.py               # Extracción de texto (PDF/DOCX)
│   ├── segmenter.py            # Motor regex de segmentación estructural
│   ├── graph.py                # GraphRAG: extracción de tripletas + networkx DiGraph
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
    │   ├── sender.py           # Envío vía Gmail SMTP con soporte adjunto PDF
    │   ├── templates.py        # HTML templates (verificación, bienvenida, auditoría)
    │   └── pdf_report.py       # Markdown → PDF (fpdf2, pure Python)
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
    └── admin_router.py         # /admin/* (usuarios, roles, actividad)

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
    │       └── actividad/      # /admin/actividad (reportes de uso)
    ├── components/Navbar.tsx
    ├── context/AuthContext.tsx  # JWT + roles (isAdmin, isAuthenticated)
    └── lib/api.ts               # Axios client (authAPI, contractsAPI, adminAPI)
```

---

## 3.1. Responsabilidades de Cada Módulo

### `contractia/config.py`
Punto único de configuración. Lee todas las variables de entorno (`.env` o Secret Manager) y las expone como atributos tipados. Cualquier módulo que necesite un parámetro (modelo LLM, tamaño de chunk, token de Telegram, etc.) lo importa desde aquí. Centralizar la configuración evita valores hardcodeados dispersos en el código.

---

### `contractia/orchestrator.py`
**Cerebro del pipeline de auditoría.** Coordina la ejecución completa:
1. Recibe el texto extraído y lo segmenta en secciones.
2. Construye el vector store RAG y (opcionalmente) el grafo GraphRAG.
3. Itera sobre cada sección llamando a `auditar_consistencia()`, que ejecuta los tres agentes y consolida sus hallazgos.
4. Devuelve el diccionario de resultados completo que luego se convierte en informe.

---

### `contractia/core/`

| Archivo | Responsabilidad |
|---------|----------------|
| `loader.py` | Extrae texto plano de archivos PDF (pypdf, con OCR por página como fallback vía pytesseract) y DOCX (docx2txt). Aplica timeout por página para evitar bloqueos en PDFs grandes. |
| `segmenter.py` | Divide el texto en secciones estructurales usando regex (capítulos, cláusulas, anexos). Construye el índice global de cláusulas numeradas y detecta saltos en la secuencia (ej. pasa de cláusula 5 a 7 sin la 6). No usa LLM. |
| `graph.py` | Construye el grafo de conocimiento GraphRAG. Para cada sección llama al LLM con un prompt CoT+Few-Shot que extrae tripletas (origen, relación, destino). Las almacena en un `nx.DiGraph`. Expone `obtener_contexto_grafo()` para que los agentes consulten relaciones entre cláusulas. |
| `report.py` | Transforma el diccionario de resultados del orquestador en un informe Markdown legible, agrupando hallazgos por sección y añadiendo resumen ejecutivo. |

---

### `contractia/agents/`

| Archivo | Responsabilidad |
|---------|----------------|
| `base.py` | Define `AgenteEspecialista`: wrapper que combina un `PromptTemplate` con el LLM y devuelve la salida parseada. Incluye `parse_json_seguro()` para manejar JSON malformado del LLM (comas extra, bloques markdown, comentarios). |
| `prompts.py` | Contiene los tres `PromptTemplate` de los agentes (Jurista, Auditor, Cronista). Aquí se concentra todo el prompt engineering: CoT, Few-Shot, árbol de decisión, criterios de severidad y conciencia temporal (`{fecha_actual}`). |
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
| `correo/templates.py` | HTML templates de los correos (verificación OTP, bienvenida, notificación de auditoría). |
| `correo/pdf_report.py` | Convierte el informe Markdown a PDF usando fpdf2 (Python puro, sin dependencias nativas). |
| `db/database.py` | Wrapper de psycopg2 con `get_conn()` como context manager. Expone `init_db()` (crea tablas si no existen) y CRUD de auditorías. |
| `db/usuarios.py` | CRUD de la tabla `usuarios`: crear, buscar por email/telegram_id, actualizar rol, hashear/verificar contraseñas con bcrypt. |
| `db/uso.py` | Rate limiting diario: registra y consulta el número de auditorías/preguntas por usuario por día según su rol. |
| `flows/audit_flow.py` | Orquesta el flujo completo de auditoría en el bot: descarga el archivo, extrae texto, llama al orquestador, guarda y envía el informe `.md` como adjunto al chat. |
| `flows/query_flow.py` | Maneja la consulta RAG interactiva en el bot: indexa el contrato en la sesión del usuario (si aún no está), recupera contexto, llama al LLM con el prompt de consulta y responde al usuario en el chat. |

---

### `api/`

| Archivo | Responsabilidad |
|---------|----------------|
| `main.py` | Entry point de FastAPI. Registra los routers, configura CORS, monta el endpoint de webhook de Telegram y arranca la inicialización de la DB al levantar. |
| `auth.py` | Generación y verificación de tokens JWT (HS256, 8h). Dependencia `get_current_user()` usada en todas las rutas protegidas. |
| `routers/auth_router.py` | Endpoints `/auth/*`: registro con OTP por email, verificación, login, reset de contraseña. |
| `routers/contracts_router.py` | Endpoints `/contracts/*`: subir contrato, abrir sesión RAG, consulta interactiva, lanzar auditoría (como `BackgroundTask`), polling de progreso, descarga PDF. |
| `routers/admin_router.py` | Endpoints `/admin/*`: listar usuarios, cambiar roles, ver logs de actividad y resumen de uso. Solo accesible con rol `admin`. |

---

### `frontend/`

| Archivo/Carpeta | Responsabilidad |
|-----------------|----------------|
| `app/page.tsx` | Landing pública con descripción del producto. |
| `app/login/` · `app/register/` · `app/forgot-password/` | Flujos de autenticación: formularios que llaman a `authAPI`. |
| `app/dashboard/` | Vista principal post-login: acceso rápido a auditoría y consulta. |
| `app/audit/` | Página central: subida de archivo, selector de modo (RAG/GraphRAG), polling de progreso en tiempo real, visualización del informe en Markdown y descarga PDF. |
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
    graph.py
    ├── Para cada sección, llama al LLM para extraer tripletas
    │   (origen, relación, destino, contexto)
    ├── Relaciones válidas: REFERENCIA_A, SE_RIGE_POR,
    │   ESTABLECE_PLAZO, MODIFICA_A, DEPENDE_DE
    ├── Construye nx.DiGraph con nodos de entidades
    └── Permite navegar dependencias entre cláusulas

   │
   ▼
[5] AUDITORÍA MULTI-AGENTE (por cada sección)
    orchestrator.py → auditar_consistencia()
    │
    ├── [PARALELO] AGENTE JURISTA  ──┐
    │   Input:  texto + contexto grafo │ ThreadPoolExecutor(max_workers=2)
    │   Output: lista de referencias   │ (independientes entre sí)
    │                                   │
    ├── [PARALELO] AGENTE CRONISTA ──┘
    │   Input:  texto + contexto grafo
    │   Output: {hay_errores_logicos, hallazgos_procesos[]}
    │
    └── [SECUENCIAL] AGENTE AUDITOR  ← espera resultado Jurista
        Input:  texto + contexto RAG + índices + refs_externas del Jurista + grafo
        Output: {hay_inconsistencias, hallazgos[]}

    Cada agente: hasta 3 reintentos automáticos con 10 s de pausa si el LLM falla
    Pausa entre secciones: 0.5 s (antes 2 s)

   │
   ▼
[6] GENERACIÓN DEL INFORME
    report.py → Markdown con todos los hallazgos agrupados por cláusula

   │
   ▼
[7] PERSISTENCIA Y ENTREGA
    Bot Telegram → archivo .md adjunto al chat
    Web → polling GET /contracts/audit/{id} → informe renderizado en Markdown
        → GET /contracts/audit/{id}/pdf → PDF generado con fpdf2 (descarga directa)
    Email → notificación automática con PDF adjunto al terminar
    DB  → tabla auditorias (status, informe, n_hallazgos, n_secciones, progress_msg, progress_pct)
```

### Pausa técnica entre secciones
El orquestador incluye `time.sleep(0.5)` entre secciones para no saturar la quota de VertexAI (reducido desde 2 s en v8.3.0).

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
| Uso del RAG en auditoría | Agente Auditor recibe top-1 fragmento de otras secciones |
| Uso del RAG en consulta | Preguntas libres del usuario vía `/contracts/query` |
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
| Persistencia | En memoria por auditoría (web) o por sesión de usuario (bot) |

---

## 6. Sistema Multi-Agente

**Patrón:** Sequential Agents con contexto compartido (RAG + GraphRAG).

| Agente | Rol | Input principal | Output |
|---|---|---|---|
| **Jurista** | Identifica normativa externa | Texto + contexto grafo | `SalidaJurista`: lista de leyes/normas citadas |
| **Auditor** | Valida referencias internas | Texto + contexto RAG + índices + grafo | `SalidaAuditor`: hallazgos de referencias rotas |
| **Cronista** | Analiza procesos y plazos | Texto + contexto grafo | `SalidaCronista`: hallazgos de errores lógicos y de plazos |

**Técnicas de Prompt Engineering aplicadas (v8.5.0):**

| Técnica | Agente(s) | Descripción |
|---|---|---|
| **Chain-of-Thought (CoT)** | Jurista, Auditor, Cronista | Bloque `<razonamiento>` con pasos explícitos antes del output; el parser lo ignora en producción |
| **Few-Shot** | Jurista | Ejemplo concreto de referencia externa vs. interna para reducir falsos positivos |
| **Árbol de decisión** | Auditor | 4 pasos explícitos por cada referencia: check en refs_externas → idx_glob → coherencia semántica → descartar |
| **Severidad dinámica** | Auditor, Cronista | Criterios ALTA/MEDIA/BAJA explícitos en el prompt; antes hardcodeado a ALTA |
| **Conciencia temporal** | Jurista, Auditor, Cronista | `{fecha_actual}` inyectada en cada prompt (v9.1.0); permite detectar plazos vencidos y fechas contractuales ilógicas respecto al día de hoy |

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

---

## 8. LLM y Proveedores

| Proveedor | Modelo principal | Uso |
|---|---|---|
| `vertexai` | Gemini 3.1 Pro Preview | Producción |
| `ollama` | deepseek-r1:8b / qwen3:8b | Desarrollo local |

---

## 9. Concurrencia y Persistencia de Auditorías

- **Bot:** single-process, asyncio, webhook mode
- **Auditorías:** limitadas a 1 simultánea por `hay_auditoria_en_progreso()` — check en DB (auto-expira en 20 min), seguro para multi-instancia Cloud Run
- **Estado de auditoría:** persistido en tabla `auditorias` (PostgreSQL), no en memoria
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
                   filename, created_at, updated_at)
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
