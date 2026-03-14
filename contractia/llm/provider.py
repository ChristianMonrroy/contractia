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
    VERTEXAI_MODELOS_PERMITIDOS,
    VERTEXAI_PROJECT,
    VERTEXAI_TEMPERATURE,
)


def build_llm(model_override: str | None = None):
    """
    Construye e inicializa el LLM según LLM_PROVIDER.
    Intenta el modelo principal; si falla, usa el fallback.

    Args:
        model_override: ID de modelo VertexAI a usar en lugar del default de config.
                        Debe estar en VERTEXAI_MODELOS_PERMITIDOS.
    """
    if not ENABLE_LLM:
        raise RuntimeError("ENABLE_LLM=false. Actívalo en .env para usar el LLM.")

    if model_override and model_override not in VERTEXAI_MODELOS_PERMITIDOS:
        raise ValueError(
            f"Modelo '{model_override}' no permitido. "
            f"Usa uno de: {VERTEXAI_MODELOS_PERMITIDOS}"
        )

    if LLM_PROVIDER == "ollama":
        return _build_ollama()
    elif LLM_PROVIDER == "vertexai":
        # Claude models go through a different builder (Vertex AI Model Garden)
        if model_override and model_override.startswith("claude-"):
            return _build_claude_vertexai(model_override)
        return _build_vertexai(model_override=model_override)
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


def _build_claude_vertexai(model_name: str):
    """Construye un LLM Claude via Vertex AI Model Garden.

    Claude 4.x (claude-sonnet-4-6, claude-opus-4-6) usa location="global".
    Claude 3.x usa location="us-east5" (única región soportada para esa generación).
    """
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex

    # Claude 4.x models require the global endpoint
    _is_claude4 = any(f"-{v}-" in model_name or model_name.endswith(f"-{v}")
                      for v in ("4-5", "4-6", "4-7"))
    location = "global" if _is_claude4 else "us-east5"

    print(f"ℹ️  Inicializando Claude via Vertex AI: {model_name} (location={location})")
    llm = ChatAnthropicVertex(
        model_name=model_name,
        project=VERTEXAI_PROJECT,
        location=location,
        temperature=VERTEXAI_TEMPERATURE,
        max_tokens=VERTEXAI_MAX_TOKENS,
    )
    print(f"✅ LLM Claude '{model_name}' inicializado.")
    return llm


def _build_vertexai(model_override: str | None = None):
    import vertexai
    from langchain_google_vertexai import ChatVertexAI

    # langchain_google_vertexai 2.x usa `from __future__ import annotations`,
    # convirtiendo todas las anotaciones en forward references (strings).
    # Pydantic v2 resuelve esas referencias con model_rebuild(). Proveer el
    # namespace completo de vertexai.generative_models (SafetySetting,
    # HarmCategory, HarmBlockThreshold, etc.) evita PydanticUserError.
    try:
        import importlib
        _types_ns: dict = {}
        for _mod_path in ("vertexai.generative_models", "vertexai.preview.generative_models"):
            try:
                _mod = importlib.import_module(_mod_path)
                _types_ns.update({k: v for k, v in vars(_mod).items() if not k.startswith("_")})
            except ImportError:
                pass
        ChatVertexAI.model_rebuild(force=True, _types_namespace=_types_ns)
        print("✅ ChatVertexAI model_rebuild OK.")
    except Exception as _e:
        print(f"⚠️  model_rebuild parcial (no crítico): {_e}")

    # Modelos preview recientes (gemini-3.x) requieren el endpoint global
    _candidate = model_override or VERTEXAI_MODEL
    location = "global" if (_candidate and "gemini-3." in _candidate) else VERTEXAI_LOCATION
    vertexai.init(project=VERTEXAI_PROJECT, location=location)
    print(f"✅ Vertex AI inicializado. Proyecto: {VERTEXAI_PROJECT}, Location: {location}")

    # Si hay override, usarlo como primer candidato; fallback al default de config
    modelos_a_intentar = (
        [model_override, VERTEXAI_FALLBACK] if model_override
        else [VERTEXAI_MODEL, VERTEXAI_FALLBACK]
    )
    for model_name in modelos_a_intentar:
        try:
            print(f"ℹ️  Inicializando Vertex AI: {model_name}")
            # Preview models have low quota → more retries with longer backoff
            _max_retries = 6 if model_name == "gemini-3.1-pro-preview" else 3
            llm = ChatVertexAI(
                model_name=model_name,
                temperature=VERTEXAI_TEMPERATURE,
                timeout=180,  # 3 min por llamada; el orquestador reintenta si expira
                max_output_tokens=VERTEXAI_MAX_TOKENS,
                max_retries=_max_retries,
            )
            print(f"✅ LLM '{model_name}' inicializado.")
            return llm
        except Exception as e:
            print(f"⚠️  No se pudo iniciar '{model_name}': {e}")

    raise RuntimeError("No se pudo inicializar ningún modelo de Vertex AI.")
