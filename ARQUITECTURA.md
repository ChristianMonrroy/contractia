# ContractIA — Documento de Arquitectura Técnica
**Versión:** 8.7.0 | **Fecha:** Marzo 2026

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
         │  segmenter.py    │    │  BM25 + FAISS     │
         │  graph.py        │    │  EnsembleRetriever│
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
    └── Crea retriever (similarity search, top-k=3)

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
| Estrategia de búsqueda | **Hybrid RAG**: BM25 (exacto, peso 0.4) + FAISS cosine (semántico, peso 0.6) fusionados con RRF |
| Metadata por chunk | título de sección, tipo, número, índice de chunk |
| Uso del RAG en auditoría | Agente Auditor recibe top-3 fragmentos de otras secciones |
| Uso del RAG en consulta | Preguntas libres del usuario vía `/contracts/query` |
| Persistencia del vector store | No persiste — se reconstruye por cada contrato cargado |

### GraphRAG (v8.6.0+)

| Característica | Valor |
|---|---|
| Tecnología | `networkx.DiGraph` |
| Extracción de tripletas | LLM (Gemini 2.5 Pro) por sección con prompt CoT + Few-Shot |
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
| `vertexai` | Gemini 2.5 Pro | Producción |
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
