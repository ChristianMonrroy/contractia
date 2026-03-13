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

    vertexai.init(project=VERTEXAI_PROJECT, location=VERTEXAI_LOCATION)
    print(f"✅ Vertex AI inicializado. Proyecto: {VERTEXAI_PROJECT}")

    # Si hay override, usarlo como primer candidato; fallback al default de config
    modelos_a_intentar = (
        [model_override, VERTEXAI_FALLBACK] if model_override
        else [VERTEXAI_MODEL, VERTEXAI_FALLBACK]
    )
    for model_name in modelos_a_intentar:
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
