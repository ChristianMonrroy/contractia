"""Configuración centralizada. Lee variables desde .env."""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes", "si")

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

OLLAMA_BASE_URL: str        = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str           = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_FALLBACK: str        = os.getenv("OLLAMA_FALLBACK", "qwen3:8b")
OLLAMA_TEMPERATURE: float   = float(os.getenv("OLLAMA_TEMPERATURE", "0.6"))
OLLAMA_NUM_CTX: int         = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_NUM_PREDICT: int     = int(os.getenv("OLLAMA_NUM_PREDICT", "8192"))
OLLAMA_TIMEOUT: int         = int(os.getenv("OLLAMA_TIMEOUT", "600"))

VERTEXAI_PROJECT: str           = os.getenv("VERTEXAI_PROJECT", "")
VERTEXAI_LOCATION: str          = os.getenv("VERTEXAI_LOCATION", "us-central1")
VERTEXAI_MODEL: str             = os.getenv("VERTEXAI_MODEL", "gemini-2.5-pro")
VERTEXAI_FALLBACK: str          = os.getenv("VERTEXAI_FALLBACK", "gemini-2.5-pro")
VERTEXAI_TEMPERATURE: float     = float(os.getenv("VERTEXAI_TEMPERATURE", "0.0"))
VERTEXAI_MAX_TOKENS: int        = int(os.getenv("VERTEXAI_MAX_OUTPUT_TOKENS", "8192"))
VERTEXAI_EMBEDDING_MODEL: str   = os.getenv("VERTEXAI_EMBEDDING_MODEL", "text-embedding-004")

RAG_ENABLED: bool           = _bool(os.getenv("RAG_ENABLED", "true"))
GRAPH_ENABLED: bool         = _bool(os.getenv("GRAPH_ENABLED", "false"))
RAG_EMBEDDING_MODEL: str    = os.getenv("RAG_EMBEDDING_MODEL", "nomic-embed-text")
RAG_CHUNK_SIZE: int         = int(os.getenv("RAG_CHUNK_SIZE", "1500"))
RAG_CHUNK_OVERLAP: int      = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
RAG_TOP_K: int              = int(os.getenv("RAG_TOP_K", "3"))

CONTRACTS_DIR: Path         = PROJECT_ROOT / os.getenv("CONTRACTS_DIR", "contracts")
OUTPUT_DIR: Path            = PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output")
REPORT_FILENAME: str        = os.getenv("REPORT_FILENAME", "informe_auditoria_contrato.md")

ENABLE_LLM: bool            = _bool(os.getenv("ENABLE_LLM", "true"))
LOG_LEVEL: str              = os.getenv("LOG_LEVEL", "INFO")

# ── Telegram Bot ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str         = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_ADMIN_ID: int      = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
SESSION_TIMEOUT_HOURS: int  = int(os.getenv("SESSION_TIMEOUT_HOURS", "8"))

# ── Email (Gmail SMTP) ────────────────────────────────────────────────────────
EMAIL_SENDER: str           = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD: str         = os.getenv("EMAIL_PASSWORD", "")
