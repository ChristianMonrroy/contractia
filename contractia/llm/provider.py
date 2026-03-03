"""
Construcción del LLM según el proveedor configurado en .env.
Soporta: Ollama (local) y Vertex AI (Google Cloud).
"""

from contractia.config import (
    ENABLE_LLM,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_FALLBACK,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT,
    VERTEXAI_FALLBACK,
    VERTEXAI_LOCATION,
    VERTEXAI_MAX_TOKENS,
    VERTEXAI_MODEL,
    VERTEXAI_PROJECT,
    VERTEXAI_TEMPERATURE,
)


def build_llm():
    """
    Construye e inicializa el LLM según LLM_PROVIDER.
    Intenta el modelo principal; si falla, usa el fallback.
    """
    if not ENABLE_LLM:
        raise RuntimeError("ENABLE_LLM=false. Actívalo en .env para usar el LLM.")

    if LLM_PROVIDER == "ollama":
        return _build_ollama()
    elif LLM_PROVIDER == "vertexai":
        return _build_vertexai()
    else:
        raise ValueError(f"LLM_PROVIDER no reconocido: '{LLM_PROVIDER}'. Usa 'ollama' o 'vertexai'.")


def _build_ollama():
    from langchain_ollama import ChatOllama

    for model_name in [OLLAMA_MODEL, OLLAMA_FALLBACK]:
        try:
            print(f"ℹ️  Inicializando Ollama: {model_name}")
            llm = ChatOllama(
                model=model_name,
                base_url=OLLAMA_BASE_URL,
                temperature=OLLAMA_TEMPERATURE,
                num_ctx=OLLAMA_NUM_CTX,
                num_predict=OLLAMA_NUM_PREDICT,
                timeout=OLLAMA_TIMEOUT,
            )
            llm.invoke("test")  # Verificar conexión
            print(f"✅ LLM '{model_name}' inicializado.")
            return llm
        except Exception as e:
            print(f"⚠️  No se pudo iniciar '{model_name}': {e}")
            if model_name == OLLAMA_MODEL:
                print(f"ℹ️  Intentando fallback '{OLLAMA_FALLBACK}'...")

    raise RuntimeError("No se pudo inicializar ningún modelo Ollama.")


def _build_vertexai():
    import vertexai
    from langchain_google_vertexai import ChatVertexAI

    vertexai.init(project=VERTEXAI_PROJECT, location=VERTEXAI_LOCATION)
    print(f"✅ Vertex AI inicializado. Proyecto: {VERTEXAI_PROJECT}")

    for model_name in [VERTEXAI_MODEL, VERTEXAI_FALLBACK]:
        try:
            print(f"ℹ️  Inicializando Vertex AI: {model_name}")
            llm = ChatVertexAI(
                model_name=model_name,
                temperature=VERTEXAI_TEMPERATURE,
                timeout=180,  # 3 min por llamada; el orquestador reintenta si expira
                max_output_tokens=VERTEXAI_MAX_TOKENS,
            )
            print(f"✅ LLM '{model_name}' inicializado.")
            return llm
        except Exception as e:
            print(f"⚠️  No se pudo iniciar '{model_name}': {e}")

    raise RuntimeError("No se pudo inicializar ningún modelo de Vertex AI.")
