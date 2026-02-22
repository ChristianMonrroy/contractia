# ContractIA v6

Sistema multi-agente de auditoría contractual con RAG para contratos de Asociaciones Público-Privadas (APP).

## Arquitectura

```
contractia/
├── main.py                     ← Punto de entrada
├── .env                        ← Configuración (crear desde .env.example)
├── requirements.txt
├── contracts/                  ← Colocar PDFs/DOCX aquí
├── output/                     ← Informes generados
└── contractia/
    ├── config.py               ← Lee .env, expone constantes
    ├── orchestrator.py         ← Pipeline principal
    ├── core/
    │   ├── loader.py           ← Carga de documentos PDF/DOCX
    │   ├── segmenter.py        ← Motor regex de segmentación
    │   └── report.py           ← Generador de informe Markdown
    ├── agents/
    │   ├── base.py             ← Clase AgenteEspecialista + parser JSON
    │   ├── schemas.py          ← Modelos Pydantic de salida
    │   ├── prompts.py          ← Templates de prompts
    │   └── factory.py          ← Fábrica de agentes
    ├── rag/
    │   └── pipeline.py         ← Vector store FAISS + retriever
    └── llm/
        └── provider.py         ← Construcción del LLM (Ollama/VertexAI)
```

## Setup rápido

```bash
# 1. Clonar y entrar al proyecto
cd contractia

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar
cp .env.example .env
# Editar .env según tu proveedor (ollama o vertexai)

# 5. Colocar contrato
# Copiar archivos PDF/DOCX a la carpeta contracts/

# 6. Ejecutar
python main.py
```

## Configuración

Edita `.env` para cambiar entre proveedores:

### Ollama (local, offline)
```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=deepseek-r1:8b
RAG_ENABLED=true
```

Requiere Ollama corriendo: `ollama serve`

### Vertex AI (Google Cloud)
```env
LLM_PROVIDER=vertexai
VERTEXAI_PROJECT=tu-proyecto-gcp
VERTEXAI_MODEL=gemini-2.5-pro
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

Descomentar `langchain-google-vertexai` en `requirements.txt`.

## Uso desde CLI

```bash
# Configuración por defecto (.env)
python main.py

# Forzar proveedor
python main.py --provider vertexai

# Carpeta personalizada
python main.py --contracts-dir ./mis_contratos

# Desactivar RAG
python main.py --no-rag
```

## Pipeline de Auditoría

```
PDF/DOCX → Carga → Segmentación Regex → [RAG: Vectorización]
                         ↓
              Para cada sección:
                Jurista → normativa externa
                Auditor → referencias cruzadas (+RAG)
                Cronista → plazos y procesos
                         ↓
                  Informe Markdown
```

## Agentes

| Agente | Rol | Tipo de hallazgo |
|--------|-----|-----------------|
| **Jurista** | Identifica normativa externa (leyes, decretos) | Contexto legal |
| **Auditor** | Valida referencias cruzadas entre cláusulas | `REFERENCIA_ROTA` |
| **Cronista** | Analiza flujos de proceso y consistencia de plazos | `LOGICA_PROCESO`, `ERROR_PLAZOS` |

## Capstone Project II — UTEC

Proyecto de Maestría en Ciencia de Datos e IA.
