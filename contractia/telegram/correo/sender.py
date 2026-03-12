"""Envío de emails via Gmail SMTP (smtplib, built-in Python)."""

import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from contractia.config import EMAIL_PASSWORD, EMAIL_SENDER


def _adjuntar_pdf(msg: MIMEMultipart, pdf_bytes: bytes, nombre: str) -> None:
    """Adjunta un PDF al mensaje MIME dado."""
    parte = MIMEBase("application", "pdf")
    parte.set_payload(pdf_bytes)
    encoders.encode_base64(parte)
    parte.add_header("Content-Disposition", "attachment", filename=nombre)
    msg.attach(parte)


def enviar_email(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: str = "",
    adjunto_pdf: Optional[bytes] = None,
    adjunto_nombre: str = "informe_auditoria.pdf",
    adjunto_pdf_tecnico: Optional[bytes] = None,
    adjunto_nombre_tecnico: str = "informe_tecnico.pdf",
) -> None:
    """
    Envía un email via Gmail SMTP con SSL.

    Args:
        adjunto_pdf:            Bytes del PDF de auditoría (None = sin adjunto).
        adjunto_nombre:         Nombre del primer adjunto.
        adjunto_pdf_tecnico:    Bytes del PDF técnico admin (None = no se adjunta).
        adjunto_nombre_tecnico: Nombre del segundo adjunto.

    Requiere en .env:
        EMAIL_SENDER   = tu_correo@gmail.com
        EMAIL_PASSWORD = App Password de Google (no la contraseña de la cuenta)
    """
    msg = MIMEMultipart("mixed")
    msg["Subject"] = asunto
    msg["From"] = f"ContractIA <{EMAIL_SENDER}>"
    msg["To"] = destinatario

    # Parte de texto alternativo (plain + html)
    alternativa = MIMEMultipart("alternative")
    if cuerpo_texto:
        alternativa.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
    alternativa.attach(MIMEText(cuerpo_html, "html", "utf-8"))
    msg.attach(alternativa)

    if adjunto_pdf:
        _adjuntar_pdf(msg, adjunto_pdf, adjunto_nombre)

    if adjunto_pdf_tecnico:
        _adjuntar_pdf(msg, adjunto_pdf_tecnico, adjunto_nombre_tecnico)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, destinatario, msg.as_string())
