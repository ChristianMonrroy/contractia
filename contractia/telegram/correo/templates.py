"""Templates HTML para los emails del bot."""


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
