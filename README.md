# ContractIA v8.2.0

Sistema de auditoría inteligente de contratos, impulsado por IA generativa (Gemini 2.5 Pro), con arquitectura multi-agente, RAG + GraphRAG y acceso via web y Telegram.

**Producción:** [contractia.pe](https://contractia.pe) | **API:** [contractia-api-444429430547.us-central1.run.app](https://contractia-api-444429430547.us-central1.run.app/docs)

---

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
| Auth | JWT (8h), bcrypt, OTP por email |
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
│       └── correo/             ← sender.py, templates.py
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
| `POST` | `/contracts/upload` | Sube PDF/DOCX y vectoriza con FAISS |
| `POST` | `/contracts/query` | Consulta RAG sobre el contrato |
| `POST` | `/contracts/audit` | Inicia auditoría multi-agente |
| `GET`  | `/contracts/audit/{id}` | Polling del resultado de auditoría |

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

Los tres agentes corren en paralelo (limitados a 1 auditoría concurrente via `asyncio.Semaphore`).

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
