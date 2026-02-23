"""Envío de emails via Gmail SMTP (smtplib, built-in Python)."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from contractia.config import EMAIL_PASSWORD, EMAIL_SENDER


def enviar_email(destinatario: str, asunto: str, cuerpo_html: str, cuerpo_texto: str = "") -> None:
    """
    Envía un email via Gmail SMTP con SSL.

    Requiere en .env:
        EMAIL_SENDER   = tu_correo@gmail.com
        EMAIL_PASSWORD = App Password de Google (no la contraseña de la cuenta)
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"ContractIA <{EMAIL_SENDER}>"
    msg["To"] = destinatario

    if cuerpo_texto:
        msg.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, destinatario, msg.as_string())
