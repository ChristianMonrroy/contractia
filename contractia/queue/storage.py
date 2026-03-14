"""
Utilidades de Cloud Storage para la cola de auditorías.

Cuando AUDIT_QUEUE_BUCKET está configurado, los archivos se suben a GCS
al encolar, lo que garantiza que persistan si Cloud Run reinicia la instancia.
Si la variable no está configurada (desarrollo local), retorna None y el
caller usa el archivo en /tmp como fallback.
"""

import os
from pathlib import Path
from typing import Optional

AUDIT_QUEUE_BUCKET: str = os.getenv("AUDIT_QUEUE_BUCKET", "")


def upload_audit_file(audit_id: str, file_bytes: bytes, ext: str) -> Optional[str]:
    """
    Sube el archivo del contrato a GCS.

    Returns:
        gcs_uri (gs://bucket/path) si la subida fue exitosa, None si
        AUDIT_QUEUE_BUCKET no está configurado o si ocurre un error.
    """
    if not AUDIT_QUEUE_BUCKET:
        return None
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(AUDIT_QUEUE_BUCKET)
        blob_name = f"audit-queue/{audit_id}/contrato{ext}"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(file_bytes, content_type="application/octet-stream")
        return f"gs://{AUDIT_QUEUE_BUCKET}/{blob_name}"
    except Exception as e:
        print(f"[GCS] Error al subir archivo de auditoría {audit_id}: {e}")
        return None


def download_audit_file(gcs_uri: str, dest_dir: Path) -> Optional[Path]:
    """
    Descarga el archivo desde GCS a dest_dir.

    Returns:
        Path del archivo descargado, o None si falla.
    """
    try:
        from google.cloud import storage
        client = storage.Client()
        # Parsear gs://bucket/blob_path
        without_prefix = gcs_uri[5:]  # quitar "gs://"
        bucket_name, blob_path = without_prefix.split("/", 1)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        ext = "." + blob_path.rsplit(".", 1)[-1]
        dest_file = dest_dir / f"contrato{ext}"
        blob.download_to_filename(str(dest_file))
        return dest_file
    except Exception as e:
        print(f"[GCS] Error al descargar archivo {gcs_uri}: {e}")
        return None


def delete_audit_file(gcs_uri: str) -> None:
    """Elimina el archivo de GCS (silencioso si falla o si gcs_uri está vacío)."""
    if not gcs_uri:
        return
    try:
        from google.cloud import storage
        client = storage.Client()
        without_prefix = gcs_uri[5:]
        bucket_name, blob_path = without_prefix.split("/", 1)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.delete()
    except Exception as e:
        print(f"[GCS] Error al eliminar archivo {gcs_uri}: {e}")
