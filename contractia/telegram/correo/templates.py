"""Templates HTML para los emails del bot."""

_NOMBRES_MODELO = {
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
}


def email_verificacion(codigo: str) -> tuple:
    asunto = "ContractIA — Código de verificación"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8">ContractIA</h2>
      <p>Tu código de verificación es:</p>
      <div style="font-size:36px;font-weight:bold;letter-spacing:10px;
                  color:#1d4ed8;padding:16px;background:#eff6ff;
                  border-radius:8px;text-align:center">{codigo}</div>
      <p style="color:#6b7280;margin-top:16px">Válido por <strong>10 minutos</strong>.
         No compartas este código.</p>
    </div>
    """
    texto = f"Tu código de verificación ContractIA es: {codigo} (válido 10 minutos)."
    return asunto, html, texto


def email_auditoria_lista(filename: str, n_hallazgos: int, n_secciones: int, modelo: str = "gemini-2.5-pro") -> tuple:
    asunto = f"ContractIA — Auditoría completada: {filename}"
    color_hallazgos = "#dc2626" if n_hallazgos > 0 else "#16a34a"
    nombre_modelo = _NOMBRES_MODELO.get(modelo, modelo)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;padding:24px">
      <h2 style="color:#1e3a5f">ContractIA — Auditoría completada</h2>
      <p>Tu auditoría del contrato <strong>{filename}</strong> ha finalizado.</p>
      <table style="border-collapse:collapse;width:100%;margin:16px 0">
        <tr style="background:#f8fafc">
          <td style="padding:10px 12px;border:1px solid #e2e8f0"><strong>Documento</strong></td>
          <td style="padding:10px 12px;border:1px solid #e2e8f0">{filename}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;border:1px solid #e2e8f0"><strong>Secciones analizadas</strong></td>
          <td style="padding:10px 12px;border:1px solid #e2e8f0">{n_secciones}</td>
        </tr>
        <tr style="background:#f8fafc">
          <td style="padding:10px 12px;border:1px solid #e2e8f0"><strong>Hallazgos detectados</strong></td>
          <td style="padding:10px 12px;border:1px solid #e2e8f0;color:{color_hallazgos};font-weight:bold">{n_hallazgos}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;border:1px solid #e2e8f0"><strong>Modelo IA utilizado</strong></td>
          <td style="padding:10px 12px;border:1px solid #e2e8f0">{nombre_modelo}</td>
        </tr>
      </table>
      <p>El informe completo con todos los hallazgos detallados se encuentra
         <strong>adjunto a este correo en formato PDF</strong>.</p>
      <p>También puedes consultarlo en línea en
         <a href="https://contractia.pe/dashboard" style="color:#1d4ed8">contractia.pe/dashboard</a>.</p>
      <p style="color:#6b7280;font-size:13px;margin-top:20px">
        Este mensaje fue generado automáticamente por ContractIA.
      </p>
    </div>
    """
    texto = (
        f"Tu auditoría de '{filename}' ha finalizado.\n"
        f"Secciones analizadas: {n_secciones}\n"
        f"Hallazgos detectados: {n_hallazgos}\n"
        f"Modelo IA utilizado: {nombre_modelo}\n"
        f"El informe completo está adjunto en PDF.\n"
        f"También disponible en: contractia.pe/dashboard"
    )
    return asunto, html, texto


def email_bienvenida(email: str, password: str, rol: str) -> tuple:
    asunto = "ContractIA — Cuenta creada exitosamente"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8">Bienvenido a ContractIA</h2>
      <p>Tu cuenta ha sido creada con éxito.</p>
      <table style="border-collapse:collapse;width:100%">
        <tr>
          <td style="padding:8px;border:1px solid #e5e7eb"><strong>Email</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb">{email}</td>
        </tr>
        <tr>
          <td style="padding:8px;border:1px solid #e5e7eb"><strong>Contraseña</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb;font-family:monospace">{password}</td>
        </tr>
        <tr>
          <td style="padding:8px;border:1px solid #e5e7eb"><strong>Nivel de acceso</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb">{rol.capitalize()}</td>
        </tr>
      </table>
      <p style="color:#dc2626;margin-top:16px">
        <strong>Guarda esta contraseña.</strong> Por seguridad, no te la enviaremos de nuevo.
      </p>
    </div>
    """
    texto = (
        f"Bienvenido a ContractIA.\n"
        f"Email: {email}\n"
        f"Contraseña: {password}\n"
        f"Nivel: {rol.capitalize()}\n"
        f"Guarda esta contraseña. No te la enviaremos de nuevo."
    )
    return asunto, html, texto
