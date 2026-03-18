"""
Cache de grafos de conocimiento en Google Cloud Storage.

Persiste grafos construidos para evitar reconstruirlos (~30-40 min)
cuando el mismo contrato se sube de nuevo. La clave de cache combina:
  - Hash SHA256 del contenido del contrato
  - Hash del prompt de extracción (si el prompt cambia, el cache se invalida)

Estructura en GCS:
  gs://{bucket}/graph-cache/{doc_hash}_{prompt_hash}.pkl
"""

import hashlib
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import networkx as nx

AUDIT_QUEUE_BUCKET: str = os.getenv("AUDIT_QUEUE_BUCKET", "")
_CACHE_PREFIX = "graph-cache"


def _hash_texto(texto: str) -> str:
    """SHA256 del texto del contrato (primeros 12 chars)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def _hash_prompt(prompt_template: str) -> str:
    """SHA256 del prompt de extracción (primeros 8 chars)."""
    return hashlib.sha256(prompt_template.encode("utf-8")).hexdigest()[:8]


def cache_key(texto_contrato: str, prompt_template: str) -> str:
    """Genera la clave de cache para un contrato + prompt."""
    return f"{_hash_texto(texto_contrato)}_{_hash_prompt(prompt_template)}"


def guardar_grafo(
    key: str,
    grafo: nx.DiGraph,
    mapa_textos: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Serializa y sube el grafo + mapa_textos a GCS.
    Retorna True si se guardó correctamente.
    """
    if not AUDIT_QUEUE_BUCKET:
        return False
    try:
        from google.cloud import storage

        data = {"grafo": grafo, "mapa_textos": mapa_textos}
        blob_name = f"{_CACHE_PREFIX}/{key}.pkl"

        client = storage.Client()
        bucket = client.bucket(AUDIT_QUEUE_BUCKET)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL),
            content_type="application/octet-stream",
        )
        print(f"[GraphCache] Grafo guardado en gs://{AUDIT_QUEUE_BUCKET}/{blob_name}", flush=True)
        return True
    except Exception as e:
        print(f"[GraphCache] Error al guardar grafo: {e}", flush=True)
        return False


def borrar_grafo(key: str) -> bool:
    """Elimina el grafo cacheado en GCS. Retorna True si se borró."""
    if not AUDIT_QUEUE_BUCKET:
        return False
    try:
        from google.cloud import storage

        blob_name = f"{_CACHE_PREFIX}/{key}.pkl"
        client = storage.Client()
        bucket = client.bucket(AUDIT_QUEUE_BUCKET)
        blob = bucket.blob(blob_name)

        if blob.exists():
            blob.delete()
            print(f"[GraphCache] Grafo eliminado: gs://{AUDIT_QUEUE_BUCKET}/{blob_name}", flush=True)
            return True
        return False
    except Exception as e:
        print(f"[GraphCache] Error al borrar grafo: {e}", flush=True)
        return False


def cargar_grafo(key: str) -> Optional[Tuple[nx.DiGraph, Optional[Dict[str, Any]]]]:
    """
    Descarga y deserializa el grafo desde GCS.
    Retorna (grafo, mapa_textos) o None si no existe o falla.
    """
    _bucket = os.getenv("AUDIT_QUEUE_BUCKET", "")
    if not _bucket:
        print(f"[GraphCache] cargar_grafo: AUDIT_QUEUE_BUCKET vacío (module={AUDIT_QUEUE_BUCKET!r}, env={_bucket!r})", flush=True)
        return None
    try:
        from google.cloud import storage

        blob_name = f"{_CACHE_PREFIX}/{key}.pkl"
        client = storage.Client()
        bucket = client.bucket(_bucket)
        blob = bucket.blob(blob_name)

        if not blob.exists():
            print(f"[GraphCache] Blob no existe: gs://{_bucket}/{blob_name}", flush=True)
            return None

        raw = blob.download_as_bytes()
        data = pickle.loads(raw)
        grafo = data.get("grafo")
        mapa_textos = data.get("mapa_textos")

        if grafo is None or not isinstance(grafo, nx.DiGraph):
            return None

        print(
            f"[GraphCache] Grafo cargado desde cache: {grafo.number_of_nodes()} nodos, "
            f"{grafo.number_of_edges()} relaciones",
            flush=True,
        )
        return grafo, mapa_textos
    except Exception as e:
        print(f"[GraphCache] Error al cargar grafo: {e}", flush=True)
        return None
