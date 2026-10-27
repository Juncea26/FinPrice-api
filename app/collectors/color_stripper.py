"""
Módulo Utilitario de Eliminación Universal de Colores (color_stripper.py).
REGLA DE NEGOCIO INQUEBRANTABLE: NO IMPORTA EL COLOR.
FinPrice compara exactamente el mismo producto técnico (misma marca, mismo modelo exacto y mismas
especificaciones técnicas de capacidad/RAM/pulgadas) al PRECIO MÁS BARATO disponible en cada una
de las 8 tiendas, sin importar si es Negro, Blanco, Azul, Plata, Gris, Rosa, Verde o Café Moca.
"""
import re
import unicodedata
from typing import Set, Tuple

# Frases compuestas de color (se eliminan primero para no dejar adjetivos huérfanos)
COMPOUND_COLOR_PHRASES: Tuple[str, ...] = (
    "titanio negro",
    "titanio blanco",
    "titanio natural",
    "titanio gris",
    "titanio desierto",
    "titanio azul",
    "negro titanio",
    "blanco titanio",
    "gris titanio",
    "azul titanio",
    "gris espacial",
    "gris grafito",
    "azul estelar",
    "azul cielo",
    "azul medianoche",
    "azul ultramarino",
    "blanco estelar",
    "negro medianoche",
    "negro espacial",
    "cafe moca",
    "café moca",
    "verde menta",
    "oro rosa",
    "rosa dorado",
    "space gray",
    "space grey",
    "natural titanium",
    "desert titanium",
    "black titanium",
    "white titanium",
    "gray titanium",
    "grey titanium",
    "blue titanium",
    "midnight black",
    "starlight white",
    "sky blue",
    "rose gold",
)

# Diccionario completo de tokens de color individuales (Español + Inglés, con y sin tilde)
SINGLE_COLOR_TOKENS: Set[str] = {
    # Español
    "negro",
    "negra",
    "blanco",
    "blanca",
    "azul",
    "plata",
    "plateado",
    "plateada",
    "gris",
    "rosa",
    "rosado",
    "rosada",
    "amarillo",
    "amarilla",
    "verde",
    "morado",
    "morada",
    "violeta",
    "dorado",
    "dorada",
    "oro",
    "rojo",
    "roja",
    "celeste",
    "naranja",
    "crema",
    "beige",
    "cafe",
    "café",
    "moca",
    "grafito",
    "espacial",
    "estelar",
    "medianoche",
    "ultramarino",
    "azulado",
    "natural",
    "desierto",
    "cosmico",
    "cósmico",
    "borgona",
    "borgoña",
    "arandano",
    "arándano",
    "arena",
    "lavanda",
    "menta",
    "coral",
    "perla",
    "cielo",
    "titanio",
    # Inglés
    "black",
    "white",
    "blue",
    "silver",
    "gray",
    "grey",
    "pink",
    "yellow",
    "green",
    "purple",
    "violet",
    "gold",
    "red",
    "orange",
    "midnight",
    "starlight",
    "ultramarine",
    "teal",
    "graphite",
    "titanium",
    "mocha",
    "brown",
    # Abreviaturas de color de catálogo retail (ej. Efe/Curacao)
    "blk",
    "wht",
    "slv",
    "blu",
    "grn",
    "pnk",
}


def _strip_accents(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Pre-compilar patrones de frases compuestas y tokens individuales
_COMPOUND_PATTERNS = [
    re.compile(rf"\b{re.escape(phrase)}\b", flags=re.IGNORECASE)
    for phrase in sorted(COMPOUND_COLOR_PHRASES, key=len, reverse=True)
]

_NORMALIZED_SINGLE_COLORS: Set[str] = {
    _strip_accents(tok.lower()) for tok in SINGLE_COLOR_TOKENS
}


def is_color_token(token: str) -> bool:
    """Indica si una palabra individual corresponde a un color del diccionario universal."""
    if not token:
        return False
    norm = _strip_accents(token.strip().lower())
    return norm in _NORMALIZED_SINGLE_COLORS


def strip_color_tokens(text: str) -> str:
    """
    Elimina todos los tokens y frases compuestas de color (en español e inglés)
    de un título o cadena de texto, limpiando guiones o separadores residuales
    sin alterar el modelo, chip, pulgadas ni capacidades técnicas.

    Ejemplos:
    - "Apple iPhone 16 128GB Negro" -> "Apple iPhone 16 128GB"
    - "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca" -> "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM"
    - "Samsung Galaxy Tab S10 FE 128GB Wi-Fi - Gris Grafito" -> "Samsung Galaxy Tab S10 FE 128GB Wi-Fi"
    """
    if not text or not str(text).strip():
        return ""

    cleaned = str(text).strip()

    # 1. Eliminar frases compuestas de color (con y sin tilde)
    for pat in _COMPOUND_PATTERNS:
        cleaned = pat.sub(" ", cleaned)

    # Eliminar también la etiqueta "Color:" si antecede a un color
    cleaned = re.sub(r"\bcolor\s*:\s*", " ", cleaned, flags=re.IGNORECASE)

    # 2. Filtrar palabras individuales cuyo equivalente sin tilde esté en _NORMALIZED_SINGLE_COLORS
    # Conservando intactos signos como 11", 55", Wi-Fi, etc.
    raw_parts = cleaned.split()
    kept_parts = []
    for part in raw_parts:
        # Limpiar puntuación lateral solo para evaluar si la palabra es un color
        word_core = re.sub(r"^[^\w]+|[^\w]+$", "", part, flags=re.UNICODE)
        if word_core and is_color_token(word_core):
            continue
        kept_parts.append(part)

    result = " ".join(kept_parts)

    # 3. Limpiar guiones, barras o comas sueltas al final o duplicadas (ej. "Wi-Fi - " -> "Wi-Fi")
    result = re.sub(r"\s+[-–—,/:]+\s*$", "", result)
    result = re.sub(r"\s+[-–—]\s+[-–—]\s+", " - ", result)
    result = re.sub(r"\(\s*\)", "", result)
    result = re.sub(r"\s+", " ", result).strip(" ,;-–—/")
    return result
