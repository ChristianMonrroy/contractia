"""Generación segura de códigos OTP y contraseñas."""

import random
import secrets
import string


def generar_codigo_verificacion() -> str:
    """Código OTP de 6 dígitos para verificación de email."""
    return "".join(random.choices(string.digits, k=6))


def generar_password(longitud: int = 12) -> str:
    """Contraseña aleatoria segura: letras + dígitos + símbolos."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%&*"
    # Garantizar al menos un carácter de cada tipo
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*"),
    ]
    password += [secrets.choice(alfabeto) for _ in range(longitud - 4)]
    random.shuffle(password)
    return "".join(password)
