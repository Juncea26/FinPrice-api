"""
Generador Automático de Consultas en Cascada (query_builder.py).
Transforma cualquier título y diccionario de especificaciones técnicas en 2 consultas
escalonadas de alta precisión para los buscadores de las 8 tiendas retail del Perú:
1. specific_query: "{marca_o_linea} {modelo_y_chip} {almacenamiento_o_pulgadas}"
   (ej. "iPad A16 128GB", "LG OLED 55 C6", "Redmi Note 15 Pro 512GB", "Galaxy Tab S10 FE 128GB")
2. broad_model_query: "{marca_o_linea} {modelo_y_chip}"
   (ej. "iPad A16", "LG OLED C6", "Redmi Note 15 Pro", "Galaxy Tab S10 FE")
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from app.collectors.color_stripper import SINGLE_COLOR_TOKENS, strip_color_tokens

# Colores prohibidos en queries de búsqueda para nunca perder variantes de otro color del mismo SKU
FORBIDDEN_QUERY_COLORS: Set[str] = set(SINGLE_COLOR_TOKENS) | {
    "azul",
    "plata",
    "plateado",
    "gris",
    "negro",
    "blanco",
    "rosa",
    "rosado",
    "amarillo",
    "moca",
    "cafe",
    "estelar",
    "espacial",
    "natural",
    "silver",
    "gray",
    "grey",
    "black",
    "white",
    "blue",
    "pink",
    "yellow",
    "brown",
    "titanio",
    "titanium",
    "cielo",
    "oro",
    "dorado",
    "gold",
    "verde",
    "green",
    "morado",
    "purple",
    "lilac",
    "rojo",
    "red",
    "grafito",
    "graphite",
    "medianoche",
    "midnight",
}

# Unidades verbosas y palabras de marketing prohibidas en queries de búsqueda
FORBIDDEN_QUERY_MARKETING_WORDS: Set[str] = {
    "pulgadas",
    "pulgada",
    "pulg",
    "inch",
    "inches",
    "con",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "en",
    "y",
    "para",
    "por",
    "nuevo",
    "nueva",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027",
    "smart",
    "tv",
    "uhd",
    "fhd",
    "hd",
    "4k",
    "8k",
    "dolby",
    "atmos",
    "vision",
    "celular",
    "libre",
    "smartphone",
    "tablet",
    "televisor",
    "laptop",
    "notebook",
    "portatil",
    "impresora",
    "multifuncional",
    "ecotank",
    "tinta",
    "continua",
    "disco",
    "solido",
    "ssd",
    "ram",
    "rom",
    "memoria",
    "interna",
    "unificada",
    "wi",
    "fi",
    "wifi",
    "bluetooth",
    "chip",
    "procesador",
    "bionic",
    "silicon",
    "evo",
    "ai",
    "thinq",
    "gen",
    "generacion",
    "5g",
    "4g",
    "lte",
}

# Mapa de líneas de producto que ya implican la marca (para no duplicar "Apple iPad" -> "iPad")
SUBBRAND_LINE_TO_PARENT_BRAND: Dict[str, str] = {
    "ipad": "apple",
    "iphone": "apple",
    "macbook": "apple",
    "imac": "apple",
    "airpods": "apple",
    "galaxy": "samsung",
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "thinkpad": "lenovo",
    "ideapad": "lenovo",
    "legion": "lenovo",
    "yoga": "lenovo",
    "vivobook": "asus",
    "zenbook": "asus",
    "tuf": "asus",
    "rog": "asus",
    "pavilion": "hp",
    "victus": "hp",
    "omen": "hp",
}

# Capitalización canónica de tokens en queries de búsqueda
CANONICAL_TOKEN_CASE: Dict[str, str] = {
    "ipad": "iPad",
    "iphone": "iPhone",
    "macbook": "MacBook",
    "imac": "iMac",
    "airpods": "AirPods",
    "apple": "Apple",
    "samsung": "Samsung",
    "galaxy": "Galaxy",
    "xiaomi": "Xiaomi",
    "redmi": "Redmi",
    "poco": "Poco",
    "lg": "LG",
    "oled": "OLED",
    "qled": "QLED",
    "qned": "QNED",
    "nanocell": "NanoCell",
    "fe": "FE",
    "pro": "Pro",
    "max": "Max",
    "ultra": "Ultra",
    "plus": "Plus",
    "air": "Air",
    "mini": "Mini",
    "lite": "Lite",
    "note": "Note",
    "tab": "Tab",
    "asus": "Asus",
    "tuf": "TUF",
    "rog": "ROG",
    "lenovo": "Lenovo",
    "hp": "HP",
    "sony": "Sony",
    "honor": "Honor",
    "motorola": "Motorola",
    "epson": "Epson",
    "canon": "Canon",
    "brother": "Brother",
    "jvc": "JVC",
    "hisense": "Hisense",
    "tcl": "TCL",
}

VALID_STORAGE_GB: Set[int] = {32, 64, 128, 256, 512, 1024, 2048}
VALID_RAM_GB: Set[int] = {2, 3, 4, 6, 8, 12, 16, 18, 24, 32, 36, 48, 64}
TV_SCREEN_INCHES: Set[int] = {32, 40, 42, 43, 48, 50, 55, 58, 60, 65, 70, 75, 77, 83, 85, 86, 98}


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _format_token(tok: str) -> str:
    low = tok.lower()
    if low in CANONICAL_TOKEN_CASE:
        return CANONICAL_TOKEN_CASE[low]
    if re.match(r"^[a-z]\d+[a-z]*$", low):
        return low.upper()
    return tok.title()


def _extract_storage_and_inches(
    product_title: str, tech_specs: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[str], Optional[str], Set[str]]:
    """
    Extrae:
    - storage_token (ej. '128GB', '512GB', '1TB')
    - screen_inches_token (ej. '55', '11')
    - tokens_to_exclude (capacidades RAM/Storage y pulgadas que deben separarse del núcleo del modelo)
    """
    specs = tech_specs or {}
    norm_title = _strip_accents(product_title).lower()
    excluded: Set[str] = set()

    # 1. Almacenamiento y RAM desde el título y tech_specs
    storage_token: Optional[str] = None
    for m_num, m_unit in re.findall(r"\b(\d{1,4})\s*(gb|tb)\b", norm_title):
        val = int(m_num)
        unit = m_unit.upper()
        excluded.add(f"{val}{m_unit.lower()}")
        excluded.add(str(val))
        if unit == "TB":
            if storage_token is None:
                storage_token = f"{val}TB"
        elif val >= 64 and val in VALID_STORAGE_GB:
            if storage_token is None:
                storage_token = "1TB" if val == 1024 else f"{val}GB"

    if storage_token is None:
        raw_stor = str(
            specs.get("Almacenamiento")
            or specs.get("Capacidad de almacenamiento")
            or specs.get("Memoria interna")
            or ""
        )
        m_st = re.search(r"\b(\d{1,4})\s*(GB|TB)\b", raw_stor, flags=re.IGNORECASE)
        if m_st:
            v_num = int(m_st.group(1))
            v_unit = m_st.group(2).upper()
            storage_token = "1TB" if (v_unit == "GB" and v_num == 1024) else f"{v_num}{v_unit}"

    # 2. Pulgadas de pantalla desde el título y tech_specs
    screen_inches_token: Optional[str] = None
    inch_match = re.search(
        r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|''|pulgadas|pulg|inch)\b",
        _strip_accents(product_title),
        flags=re.IGNORECASE,
    )
    if inch_match:
        raw_inch = inch_match.group(1)
        excluded.add(raw_inch.lower())
        if "." in raw_inch:
            excluded.update(raw_inch.split("."))
        else:
            screen_inches_token = raw_inch

    if screen_inches_token is None:
        raw_scr = str(
            specs.get("Pantalla")
            or specs.get("Tamaño de la pantalla")
            or specs.get("Tamaño de pantalla")
            or ""
        )
        m_scr = re.search(r"\b(\d{2})\b", raw_scr)
        if m_scr and int(m_scr.group(1)) in TV_SCREEN_INCHES:
            screen_inches_token = m_scr.group(1)
            excluded.add(screen_inches_token)

    return storage_token, screen_inches_token, excluded


def build_search_queries(
    product_title: str, tech_specs: Optional[Dict[str, Any]] = None
) -> List[str]:
    """
    Genera 2 consultas en cascada limpias de colores y palabras de marketing:
    1. specific_query: "{marca_o_linea} {modelo_y_chip} {almacenamiento_o_pulgadas}"
       (ej. "iPad A16 128GB", "LG OLED 55 C6", "Redmi Note 15 Pro 512GB", "Galaxy Tab S10 FE 128GB")
    2. broad_model_query: "{marca_o_linea} {modelo_y_chip}"
       (ej. "iPad A16", "LG OLED C6", "Redmi Note 15 Pro", "Galaxy Tab S10 FE")
    """
    if not product_title:
        return []

    specs = tech_specs or {}
    storage_token, screen_inches_token, capacity_and_inch_tokens = _extract_storage_and_inches(
        product_title, specs
    )

    # Normalizar título eliminando colores, decimales de pulgadas (ej. '13.6 Pulgadas') y unidades pegadas ('512GB', '12GB')
    cleaned = _strip_accents(strip_color_tokens(product_title))
    cleaned = re.sub(r"\b\d{1,2}\.\d+\s*(?:pulgadas|pulg|\"|'')?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,4}\s*(?:gb|tb|mah|mp|hz|w)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:10ma|11ma|10a|11a)\s*(?:gen|generacion)?\b", " ", cleaned, flags=re.IGNORECASE)

    raw_tokens = re.findall(r"\b[a-zA-Z0-9]+\b", cleaned)
    filtered_tokens: List[str] = []

    for tok in raw_tokens:
        low = tok.lower()
        if low in FORBIDDEN_QUERY_COLORS or low in FORBIDDEN_QUERY_MARKETING_WORDS:
            continue
        if low in capacity_and_inch_tokens:
            continue
        # Ignorar si es la medida en pulgadas de una tablet/laptop acompañada de modelo explícito (ej. 'iPad 11 A16')
        if low in {"10", "11", "12", "13", "14", "15", "16"} and storage_token is not None:
            # Conservar solo si es el número de generación de un iPhone/Redmi/Note/Galaxy S (ej. 'iPhone 16', 'Note 15')
            prev_low = filtered_tokens[-1].lower() if filtered_tokens else ""
            if prev_low not in {"iphone", "note", "redmi", "galaxy", "s", "a", "magic", "honor"}:
                continue
        if low not in [t.lower() for t in filtered_tokens]:
            filtered_tokens.append(low)

    # Si hay una sub-marca/línea que ya identifica inequívocamente la marca (ej. iPad -> Apple, Redmi -> Xiaomi, Galaxy -> Samsung),
    # omitir la marca padre redundante al inicio para construir queries idénticas a las que usan los buscadores retail
    parent_brands_to_drop: Set[str] = set()
    for low_tok in filtered_tokens:
        if low_tok in SUBBRAND_LINE_TO_PARENT_BRAND:
            parent_brands_to_drop.add(SUBBRAND_LINE_TO_PARENT_BRAND[low_tok])

    core_tokens = [
        _format_token(t) for t in filtered_tokens if t not in parent_brands_to_drop
    ]
    if not core_tokens and filtered_tokens:
        core_tokens = [_format_token(t) for t in filtered_tokens]

    broad_model_query = " ".join(core_tokens).strip()

    # Construir specific_query añadiendo almacenamiento (o pulgadas cuando no hay almacenamiento, ej. TVs)
    specific_parts = list(core_tokens)
    if storage_token:
        if storage_token not in specific_parts:
            specific_parts.append(storage_token)
    elif screen_inches_token:
        if screen_inches_token not in specific_parts:
            # En TVs OLED/QLED/QNED (ej. LG OLED 55 C6), ubicar las pulgadas después del tipo de panel
            panel_indices = [
                i
                for i, p in enumerate(specific_parts)
                if p.upper() in {"OLED", "QLED", "QNED", "NANOCELL"}
            ]
            if panel_indices and len(specific_parts) > panel_indices[0] + 1:
                specific_parts.insert(panel_indices[0] + 1, screen_inches_token)
            else:
                specific_parts.append(screen_inches_token)

    specific_query = " ".join(specific_parts).strip()

    queries: List[str] = []
    if specific_query:
        queries.append(specific_query)
    if broad_model_query and broad_model_query not in queries:
        queries.append(broad_model_query)

    return queries
