# ContractIA — Documento de Arquitectura Técnica y Plan de Evolución
**Versión:** 7.0.2 | **Fecha:** Febrero 2026

---

## 1. ¿Qué es ContractIA?

ContractIA es un sistema de **auditoría inteligente de contratos legales** accesible vía bot de Telegram. Permite a usuarios autorizados subir un contrato en PDF o DOCX y obtener:

- **Auditoría completa:** análisis multi-agente que detecta inconsistencias legales, referencias cruzadas rotas y errores en plazos y procesos.
- **Consulta interactiva (RAG):** preguntas en lenguaje natural respondidas con base en el contenido del contrato.

---

## 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT                             │
│                                                                 │
│  Usuario → Telegram API → bot.py → handler.py                  │
│                                        │                        │
│                    ┌───────────────────┤                        │
│                    ▼                   ▼                        │
│             audit_flow.py       query_flow.py                   │
│                    │                   │                        │
└────────────────────┼───────────────────┼────────────────────────┘
                     │                   │
         ┌───────────▼──────┐    ┌───────▼───────────┐
         │   ORQUESTADOR    │    │   RAG PIPELINE    │
         │  orchestrator.py │    │   pipeline.py     │
         │                  │    │                   │
         │  segmenter.py    │    │  FAISS + Embeddings│
         │  (regex engine)  │    │  (VertexAI /       │
         │                  │    │   Ollama)          │
         └────────┬─────────┘    └───────────────────┘
                  │
         ┌────────▼─────────────────────────┐
         │        MULTI-AGENT LAYER         │
         │                                  │
         │  Jurista → Auditor → Cronista    │
         │  (LangChain + PromptTemplate)    │
         └────────┬─────────────────────────┘
                  │
         ┌────────▼─────────┐
         │   LLM PROVIDER   │
         │  provider.py     │
         │                  │
         │  VertexAI        │
         │  (Gemini 2.5 Pro)│
         │  o Ollama (local)│
         └──────────────────┘

┌─────────────────────────────────────┐
│           CAPA DE DATOS             │
│                                     │
│  SQLite (contractia.db)             │
│  ├── usuarios (bcrypt passwords)    │
│  ├── codigos_verificacion (OTP)     │
│  ├── uso_diario (rate limiting)     │
│  └── logs                           │
│                                     │
│  Sesiones en memoria (dict Python)  │
│  Vector store FAISS (en memoria,    │
│  por sesión de usuario)             │
└─────────────────────────────────────┘
```

---

## 3. Estructura de Módulos

```
contractia/
├── config.py                   # Variables de entorno centralizadas
├── orchestrator.py             # Pipeline principal de auditoría
│
├── core/
│   ├── loader.py               # Extracción de texto (PDF/DOCX)
│   ├── segmenter.py            # Motor regex de segmentación estructural
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
    ├── correo/                 # SMTP Gmail (verificación y bienvenida)
    ├── db/
    │   ├── database.py         # SQLite, init_db()
    │   ├── usuarios.py         # CRUD usuarios (bcrypt)
    │   └── uso.py              # Rate limiting diario por rol
    └── flows/
        ├── audit_flow.py       # Flujo de auditoría completa (con semáforo)
        └── query_flow.py       # Flujo de consulta RAG interactiva
```

---

## 4. Pipeline de Auditoría — Paso a Paso

```
PDF/DOCX
   │
   ▼
[1] EXTRACCIÓN DE TEXTO
    loader.py → pypdf / docx2txt

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
[4] AUDITORÍA MULTI-AGENTE (por cada sección)
    orchestrator.py → auditar_consistencia()
    │
    ├── AGENTE JURISTA
    │   Input:  texto de la sección
    │   Tarea:  identifica normativa externa (leyes, códigos, etc.)
    │   Output: lista de referencias externas (JSON)
    │
    ├── AGENTE AUDITOR  ← recibe contexto RAG de otras secciones
    │   Input:  texto + contexto RAG + índices de cláusulas
    │   Tarea:  valida referencias cruzadas internas
    │   Output: {hay_inconsistencias, hallazgos[]} (JSON)
    │
    └── AGENTE CRONISTA
        Input:  texto de la sección
        Tarea:  analiza lógica de procesos y plazos
        Output: {hay_errores_logicos, hallazgos_procesos[]} (JSON)

   │
   ▼
[5] GENERACIÓN DEL INFORME
    report.py → Markdown con todos los hallazgos

   │
   ▼
[6] ENTREGA AL USUARIO
    Telegram → archivo .md adjunto
```

### Pausa técnica entre secciones
El orquestador incluye `time.sleep(2)` entre secciones para no saturar la quota de VertexAI.

---

## 5. Tipo de RAG Implementado

**Tipo:** RAG Naive / Standard con enriquecimiento de metadata estructural.

| Característica | Valor |
|---|---|
| Estrategia de chunking | `RecursiveCharacterTextSplitter` con separadores legales (`\nCAPÍTULO`, `\nArtículo`, `\nCláusula`, etc.) |
| Tamaño de chunk | 1500 caracteres, overlap 200 |
| Modelo de embeddings | `text-embedding-004` (VertexAI) / `nomic-embed-text` (Ollama) |
| Vector store | **FAISS** (en memoria, por sesión) |
| Estrategia de búsqueda | Similarity search (cosine), top-k=3 |
| Metadata por chunk | título de sección, tipo, número, índice de chunk |
| Uso del RAG en auditoría | El Agente Auditor recibe los top-3 fragmentos más similares de **otras secciones** para detectar inconsistencias cruzadas |
| Uso del RAG en consulta | El usuario hace preguntas libres; se recuperan top-k fragmentos y se construye un prompt para el LLM |
| Persistencia del vector store | No persiste — se reconstruye por cada contrato cargado |

**Limitación notable:** el FAISS vive en memoria RAM por sesión. Si el bot se reinicia, todos los vectores se pierden.

---

## 6. Sistema Multi-Agente

**Patrón:** Sequential Agents (no paralelos, no hay comunicación directa entre agentes).

Los tres agentes comparten el mismo LLM pero tienen prompts distintos y se ejecutan en secuencia:

| Agente | Rol | Input principal | Output |
|---|---|---|---|
| **Jurista** | Identifica normativa externa | Texto de sección | Lista de leyes/normas citadas |
| **Auditor** | Valida referencias internas | Texto + contexto RAG + índices | Hallazgos de referencias rotas |
| **Cronista** | Analiza procesos y plazos | Texto de sección | Hallazgos de errores lógicos y de plazos |

Todos los agentes usan `LangChain PromptTemplate | LLM | StrOutputParser` con un parser JSON robusto que maneja errores comunes de salida del LLM (markdown, comas extra, comentarios).

---

## 7. Modelo de Roles y Autenticación

**Registro:** Email OTP (código de 6 dígitos, expira en 10 min) → contraseña autogenerada enviada por email.

**Roles:**

| Rol | Auditorías/día | Preguntas/día | Notas |
|---|---|---|---|
| `pendiente` | 0 | 0 | Recién registrado, espera aprobación del admin |
| `basico` | 0 | 10 | Solo puede hacer preguntas |
| `auditor` | 3 | 30 | Puede auditar y preguntar |
| `admin` | ∞ | ∞ | Panel de administración completo |

**Flujo de aprobación:** nuevo usuario → admin recibe notificación en Telegram con botones → asigna rol → usuario notificado.

**Seguridad actual:**
- Passwords hasheados con **bcrypt** (cost factor por defecto: 12)
- Sesiones en memoria con timeout configurable (default: 8h)
- El mensaje con la contraseña en el login se borra de Telegram inmediatamente
- Secretos en `.env` (nunca en el código)

---

## 8. LLM y Proveedores

El sistema soporta dos proveedores intercambiables vía variable de entorno `LLM_PROVIDER`:

| Proveedor | Modelo principal | Fallback | Uso |
|---|---|---|---|
| `vertexai` | Gemini 2.5 Pro | Gemini 2.5 Pro | Producción |
| `ollama` | deepseek-r1:8b | qwen3:8b | Desarrollo local |

---

## 9. Concurrencia Actual

- **Bot:** single-process, asyncio, polling mode
- **Auditorías:** limitadas a 1 simultánea por `asyncio.Semaphore(1)`
- **Preguntas RAG:** concurrentes sin límite (son más rápidas y ligeras)
- **Base de datos:** SQLite con WAL mode (permite lecturas concurrentes)

---

---

# PARTE II — Plan de Escalabilidad y Seguridad

---

## 10. Plan de Despliegue 24/7 con Auto-Deploy (Corto Plazo)

**Recomendación:** VPS Linux ($6/mes) + GitHub Actions

```
Tu laptop                  GitHub                    Servidor VPS
    │                         │                           │
    │── git push origin main ─►│                           │
    │                         │── GitHub Actions ──────────►│
    │                         │   1. SSH al servidor       │
    │                         │   2. git pull origin main  │
    │                         │   3. systemctl restart     │
    │                         │      contractia            │
```

**Componentes a configurar:**
1. `.github/workflows/deploy.yml` — workflow de CI/CD
2. `systemd` service — mantiene el bot corriendo y lo reinicia si cae
3. GitHub Secrets — `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`
4. Variables de entorno en el servidor (nunca en GitHub)

---

## 11. Plan de Escalabilidad (Mediano Plazo)

### Fase 1 — Ahora: VPS + SQLite (sin cambios de arquitectura)
- Costo: $6/mes
- Capacidad: decenas de usuarios, 1 auditoría simultánea
- Limitación: no escala horizontalmente

### Fase 2 — Migrar a PostgreSQL
- Mismo VPS o Railway
- Cambios en 6 archivos Python (mecánico, ~3h)
- Desbloquea el uso en Railway y futuros despliegues multi-instancia

### Fase 3 — Webhooks en lugar de Polling
- Telegram envía mensajes a tu URL en vez de que el bot pregunte
- Permite múltiples instancias del bot en paralelo
- Requiere HTTPS (certificado SSL)

### Fase 4 — Arquitectura cloud-native (si escala a cientos de usuarios)
```
GitHub ──► Railway/GCP
              ├── Bot instances (webhooks, múltiples pods)
              ├── PostgreSQL (gestionado)
              ├── Redis (sesiones compartidas entre instancias)
              └── VertexAI (ya cloud-native ✓)
```

---

## 12. Plan de Seguridad (Mejoras Pendientes)

| Área | Situación actual | Mejora recomendada | Prioridad |
|---|---|---|---|
| Credenciales | En `.env` local ✓ | Secrets manager (GCP Secret Manager, Railway vars) en producción | Alta |
| Base de datos | Sin cifrado en reposo | Cifrado a nivel de disco del servidor (DigitalOcean lo ofrece) | Media |
| Transporte | Telegram cifra el canal ✓ | Añadir HTTPS si se agregan endpoints web | Media |
| Rate limiting | Por rol y día ✓ | Añadir límite por IP/burst para prevenir abuso | Media |
| Logs | En SQLite sin rotación | Rotar logs, no almacenar texto de contratos | Alta |
| Service account GCP | JSON en disco local | Workload Identity Federation (sin archivos JSON en el servidor) | Alta |
| Sesiones | En memoria Python | Migrar a Redis para persistencia entre reinicios | Baja |
| Auditoría de accesos | Logs básicos ✓ | Alertas al admin si un usuario supera umbrales anómalos | Baja |

---

## 13. Preguntas para el Profesor

Estas preguntas abordan decisiones de arquitectura que tienen implicaciones académicas y de investigación:

---

### Sobre el diseño multi-agente

**P1.** El sistema usa tres agentes especializados (Jurista, Auditor, Cronista) que se ejecutan **secuencialmente** sobre cada sección. ¿Sería más adecuado académicamente un diseño de agentes **paralelos** (con join al final) o un diseño **reflexivo** (donde un agente supervisor revisa y cuestiona los hallazgos de los otros)? ¿Qué frameworks de multi-agente (LangGraph, CrewAI, AutoGen) considera más pertinente para este dominio?

**P2.** Los agentes no tienen **memoria inter-sección**: cada sección se analiza de forma independiente. ¿Deberíamos acumular los hallazgos de secciones anteriores como contexto para las siguientes, y cómo afectaría eso al costo computacional y al riesgo de alucinaciones acumuladas?

---

### Sobre el RAG

**P3.** El sistema usa **RAG Naive** (chunk → embed → similarity search → prompt). Existen variantes más sofisticadas: **HyDE** (Hypothetical Document Embeddings), **RAG-Fusion** (múltiples queries reformuladas), o **GraphRAG** (grafo de entidades). ¿Cuál considera más apropiado para contratos legales donde las cláusulas tienen dependencias explícitas entre sí?

**P4.** Los chunks se generan por tamaño de caracteres con separadores legales. ¿Sería más efectivo un chunking **semántico** basado en la estructura del contrato (cada cláusula como chunk) versus el chunking actual por tamaño? ¿Hay estudios de ablación sobre esto en documentos legales?

**P5.** El vector store FAISS **no persiste entre sesiones**. ¿Tiene sentido académicamente persistir los vectores de contratos ya procesados (para análisis comparativo entre versiones del mismo contrato), o la privacidad del cliente lo contraindica?

---

### Sobre escalabilidad y arquitectura

**P6.** El sistema corre en modo **polling** (single-process). Para escalar a múltiples usuarios concurrentes con auditorías pesadas, ¿se recomienda una arquitectura de **cola de tareas** (Celery + Redis) dentro del mismo servicio, o una separación en microservicios (bot service + worker service)? ¿Cuál es el trade-off en un contexto de MVP de investigación?

**P7.** Las sesiones de usuario (incluyendo el vector store FAISS por sesión) viven en **memoria RAM del proceso Python**. Con 50 usuarios concurrentes con contratos de 200 páginas, esto podría consumir varios GB. ¿Cuál es la estrategia adecuada: serializar y guardar el FAISS en disco por sesión, migrar a un vector store compartido (Pinecone, Weaviate, pgvector), o limitar el tiempo de vida de la sesión RAG?

---

### Sobre el dominio legal

**P8.** Los prompts de los agentes están optimizados para **contratos de concesión** (infraestructura pública). ¿Qué tan transferible es este diseño a otros tipos de contratos (laborales, comerciales, arrendamiento)? ¿Debería haber un agente adicional de **clasificación de tipo de contrato** antes del pipeline, para seleccionar los prompts adecuados?

**P9.** El Agente Cronista diferencia entre "Días" (hábiles) y "Días Calendario", lo cual es específico al marco legal peruano. ¿Debería esta lógica estar en el prompt (como está ahora) o en una **base de conocimiento estructurada** (ej. ontología de plazos legales) consultada vía RAG?
