# ContractIA v8.5.0

Sistema de auditoría inteligente de contratos, impulsado por IA generativa (Gemini 2.5 Pro), con arquitectura multi-agente, RAG + GraphRAG y acceso via web y Telegram.

**Producción:** [contractia.pe](https://contractia.pe) | **API:** [contractia-api-444429430547.us-central1.run.app](https://contractia-api-444429430547.us-central1.run.app/docs)

---

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
contractia.pe (Next.js 14 · Vercel)
        ↕ HTTPS
api.contractia.pe → Cloud Run (FastAPI · Python)
        ↕
   Cloud SQL (PostgreSQL 15 · us-central1)
        ↕
   Cloud Storage / FAISS (vectores RAG)
        ↕
   VertexAI (Gemini 2.5 Pro · text-embedding-004)
        ↕
   GraphRAG (networkx DiGraph · tripletas extraídas por LLM)
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
│   ├── config.py               ← Variables de entorno
│   ├── orchestrator.py         ← Pipeline de auditoría (RAG + GraphRAG)
│   ├── agents/                 ← Jurista, Auditor, Cronista
│   ├── core/
│   │   ├── graph.py            ← GraphRAG (networkx + extracción LLM)
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
| **Jurista** | Identifica normativa legal aplicable y cláusulas problemáticas |
| **Auditor** | Detecta riesgos, penalidades y condiciones desfavorables |
| **Cronista** | Sintetiza hallazgos y genera el informe final |

**Ejecución:** Jurista y Cronista corren en **paralelo** (ThreadPoolExecutor). Auditor corre después del Jurista (necesita sus referencias externas). Limitado a 1 auditoría concurrente via check en DB (`hay_auditoria_en_progreso`). Cada agente reintenta hasta 3 veces si el LLM falla.

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
| `JWT_SECRET` | Clave secreta para firmar JWT |

---

## Capstone Project II — UTEC

Proyecto de Maestría en Ciencia de Datos e IA · 2025
Dominio: [contractia.pe](https://contractia.pe)
