"""Capa 1 — Sanitización programática contra prompt injection.

Filtros determinísticos (sin LLM) que limpian el texto y detectan
patrones sospechosos antes de que llegue a cualquier modelo de IA.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

# ── Caracteres Unicode invisibles / de control a eliminar ──────────────
_INVISIBLE_CHARS = frozenset([
    "\u200b",  # Zero Width Space
    "\u200c",  # Zero Width Non-Joiner
    "\u200d",  # Zero Width Joiner
    "\ufeff",  # BOM / Zero Width No-Break Space
    "\u00ad",  # Soft Hyphen
    "\u200e",  # Left-to-Right Mark
    "\u200f",  # Right-to-Left Mark
    "\u202a",  # Left-to-Right Embedding
    "\u202b",  # Right-to-Left Embedding
    "\u202c",  # Pop Directional Formatting
    "\u202d",  # Left-to-Right Override
    "\u202e",  # Right-to-Left Override
    "\u2060",  # Word Joiner
    "\u2061",  # Function Application
    "\u2062",  # Invisible Times
    "\u2063",  # Invisible Separator
    "\u2064",  # Invisible Plus
])

# ── Patrones heurísticos de prompt injection (bilingüe ES/EN) ─────────
_INJECTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?i)(ignore|ignora|olvida|descar?ta).{0,30}"
            r"(instrucciones|instructions|anteriores|previous|previas|above)"
        ),
        "Intento de ignorar instrucciones del sistema",
    ),
    (
        re.compile(
            r"(?i)(act[uú]a como|act as|you are now|eres ahora|"
            r"pretend you|finge que|asume el rol)"
        ),
        "Intento de cambiar la identidad/rol de la IA",
    ),
    (
        re.compile(
            r"(?i)(system prompt|system message|hidden instruction|"
            r"instrucciones ocultas|instrucciones del sistema)"
        ),
        "Referencia a instrucciones internas del sistema",
    ),
    (
        re.compile(
            r"(?i)(print|imprime|muestra|revela|output|display)"
            r".{0,20}(json|prompt|instructions|instrucciones|configuraci[oó]n)"
        ),
        "Intento de exfiltrar prompt o configuración interna",
    ),
    (
        re.compile(
            r"(?i)(debug mode|modo debug|override|bypass|"
            r"modo de prueba|test mode|desactiva|disable)"
        ),
        "Intento de activar modo debug o bypass de seguridad",
    ),
    (
        re.compile(
            r"(?i)(do not audit|no audit|skip (the )?analy|"
            r"no analices|salta el an[aá]lisis|omite)"
        ),
        "Intento de omitir el análisis/auditoría",
    ),
    (
        re.compile(
            r"(?i)(respond (only )?with|responde (solo |únicamente )?(con )?|"
            r"return only|devuelve solo).{0,30}"
            r"(true|false|es_seguro|safe|seguro|no findings|sin hallazgos)"
        ),
        "Intento de forzar un resultado específico",
    ),
]


@dataclass
class AlertaSanitizacion:
    """Una alerta heurística detectada por regex."""
    patron: str
    descripcion: str
    fragmento: str  # texto circundante donde se encontró
    posicion: int   # offset en el texto original


@dataclass
class ResultadoSanitizacion:
    """Resultado de sanitizar un texto."""
    texto_limpio: str
    alertas: List[AlertaSanitizacion] = field(default_factory=list)
    chars_eliminados: int = 0

    @property
    def tiene_alertas(self) -> bool:
        return len(self.alertas) > 0


def _eliminar_chars_invisibles(texto: str) -> Tuple[str, int]:
    """Elimina caracteres Unicode invisibles/de control y retorna (texto, n_eliminados)."""
    eliminados = 0
    partes = []
    for ch in texto:
        if ch in _INVISIBLE_CHARS:
            eliminados += 1
        elif unicodedata.category(ch).startswith("C") and ch not in ("\n", "\r", "\t"):
            # Categoría C = control chars, pero preservar saltos de línea y tabs
            eliminados += 1
        else:
            partes.append(ch)
    return "".join(partes), eliminados


def _normalizar_unicode(texto: str) -> str:
    """Normaliza a NFC para evitar homoglyphs por descomposición."""
    return unicodedata.normalize("NFC", texto)


def _detectar_patrones(texto: str) -> List[AlertaSanitizacion]:
    """Busca patrones heurísticos de prompt injection en el texto."""
    alertas: List[AlertaSanitizacion] = []
    for patron_re, descripcion in _INJECTION_PATTERNS:
        for match in patron_re.finditer(texto):
            # Extraer fragmento de contexto (±80 chars)
            start = max(0, match.start() - 80)
            end = min(len(texto), match.end() + 80)
            fragmento = texto[start:end].replace("\n", " ").strip()
            alertas.append(AlertaSanitizacion(
                patron=patron_re.pattern,
                descripcion=descripcion,
                fragmento=f"...{fragmento}...",
                posicion=match.start(),
            ))
    return alertas


def sanitizar_texto(texto: str) -> ResultadoSanitizacion:
    """Sanitiza el texto de un contrato y detecta patrones sospechosos.

    Retorna un ResultadoSanitizacion con:
    - texto_limpio: texto sin caracteres invisibles, normalizado NFC
    - alertas: lista de patrones sospechosos encontrados (no bloquean)
    - chars_eliminados: cantidad de caracteres invisibles removidos
    """
    # Paso 1: eliminar caracteres invisibles
    texto_sin_invisibles, n_eliminados = _eliminar_chars_invisibles(texto)

    # Paso 2: normalizar Unicode (NFC)
    texto_limpio = _normalizar_unicode(texto_sin_invisibles)

    # Paso 3: detectar patrones heurísticos
    alertas = _detectar_patrones(texto_limpio)

    return ResultadoSanitizacion(
        texto_limpio=texto_limpio,
        alertas=alertas,
        chars_eliminados=n_eliminados,
    )
