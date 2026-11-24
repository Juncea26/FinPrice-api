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
from app.collectors.tech_normalizer import (
    DEFAULT_NEUTRAL_TOKENS,
    normalize_memory_and_storage,
    normalize_tech_text,
)

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
    "snapdragon",
    "qualcomm",
    "mediatek",
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


def _normalize_plus_variant(text: str) -> str:
    """
    Convierte '+' asociado a modelos/variantes (ej. 'Pro+', 'S24+', 'Note 15 Pro+') en ' plus '
    antes de limpiar signos o tokenizar, preservando combos RAM+Storage (ej. '12+512GB') y resoluciones ('FHD+').
    """
    if not text:
        return ""
    # 1. Expandir combinaciones RAM+Storage antes de sustituir '+'
    normalized = re.sub(
        r"\b(\d{1,2})\s*(?:gb|g)?\s*[+/]\s*(\d{2,4})\s*(gb|g|tb)\b",
        lambda m: f"{m.group(1)}gb {m.group(2)}{'tb' if 'tb' in m.group(3).lower() else 'gb'}",
        str(text),
        flags=re.IGNORECASE,
    )
    # 2. Quitar '+' de siglas de resolución, Copilot+ y conectores de bundle ('+ Funda') para evitar falsos tokens 'plus'
    normalized = re.sub(
        r"(?i)\b(fhd|qhd|uhd|hd|wxga|wqhd|hdr10|hdr|dolby|copilot)\s*\+",
        r"\1",
        normalized,
    )
    normalized = re.sub(
        r"(?i)\+\s*(?=(?:funda|case|folio|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|lapiz|pen|stylus|combo|pack|tags?|regalo|hph|watch|buds)\b)",
        " ",
        normalized,
    )
    # 3. Convertir '+' de modelo/variante a ' plus '
    normalized = re.sub(r"(?i)\b(pro|note|tab|s\d+|a\d+)\s*\+", r"\1 plus ", normalized)
    normalized = re.sub(r"\+", " plus ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


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
            if v_unit == "TB" or (v_num >= 64 and v_num in VALID_STORAGE_GB):
                storage_token = "1TB" if (v_unit == "GB" and v_num == 1024) else f"{v_num}{v_unit}"

    # 2. Pulgadas de pantalla desde el título y tech_specs
    screen_inches_token: Optional[str] = None
    inch_match = re.search(
        r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|''|(?:pulgadas|pulg|inch)\b)",
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

    # Normalizar título eliminando colores, convirtiendo '+' de variante en ' plus ', decimales de pulgadas y unidades pegadas
    cleaned = _strip_accents(_normalize_plus_variant(strip_color_tokens(product_title)))
    cleaned = re.sub(r"\b\d{1,2}\.\d+\s*(?:\"|''|(?:pulgadas|pulg)\b)?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,4}\s*(?:gb|tb|mah|mp|hz|w)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:10ma|11ma|10a|11a)\s*(?:gen|generacion)?\b", " ", cleaned, flags=re.IGNORECASE)

    raw_tokens = re.findall(r"\b[a-zA-Z0-9]+\b", cleaned)
    filtered_tokens: List[str] = []

    for tok in raw_tokens:
        low = tok.lower()
        if low in FORBIDDEN_QUERY_COLORS or low in FORBIDDEN_QUERY_MARKETING_WORDS:
            continue
        if low == "x" and "snapdragon" in cleaned.lower():
            continue
        m_oled_sku = re.match(r"^oled(\d{2})([a-z]\d+)[a-z]*$", low)
        if m_oled_sku:
            if not screen_inches_token:
                screen_inches_token = m_oled_sku.group(1)
            low = m_oled_sku.group(2)
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


def build_short_search_query(
    product: Any,
    tech_specs: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generador Automático de Consulta Corta (máximo 3 a 4 tokens):
    Extrae automáticamente del producto únicamente:
    Familia/Modelo Base + Almacenamiento (o Pulgadas en TVs).
    Ejemplos:
      - "Samsung Galaxy A37 5G 256GB 8GB RAM" -> "Galaxy A37 256"
      - "Tablet Xiaomi Redmi Pad 2 11\" 4GB RAM 128GB" -> "Redmi Pad 2 128"
      - "Tablet Samsung Galaxy Tab A11 8.7\" 64GB 4GB RAM" -> "Tab A11 64"
      - "Apple iPhone 15 128GB" -> "iPhone 15 128"
      - "Laptop Asus Zenbook A14 14\" Snapdragon X 16GB RAM 512GB SSD" -> "Zenbook A14"
    """
    if isinstance(product, str):
        raw_title = product
        specs = tech_specs or {}
        category = ""
    elif isinstance(product, dict):
        raw_title = str(product.get("title") or "")
        specs = tech_specs or product.get("tech_specs") or product.get("raw_tech_specs") or {}
        category = str(product.get("category") or "")
    else:
        raw_title = str(getattr(product, "title", "") or "")
        specs = (
            tech_specs
            or getattr(product, "tech_specs", None)
            or getattr(product, "raw_tech_specs", None)
            or {}
        )
        category = str(getattr(product, "category", "") or "")

    clean_title = _normalize_plus_variant(strip_color_tokens(raw_title))
    if not clean_title:
        return ""

    t_low = _strip_accents(clean_title).lower()
    is_tv = category.lower() == "tvs" or any(
        w in t_low for w in ("oled", "qled", "qned", "nanocell", "smart tv", "televisor", "u8000", "qn85")
    )
    is_laptop = category.lower() == "laptops" or any(
        w in t_low for w in ("laptop", "macbook", "zenbook", "ideapad", "victus", "tuf gaming", "loq", "thinkpad", "vivobook")
    )
    is_printer = category.lower() == "impresoras" or any(
        w in t_low for w in ("impresora", "multifuncional", "ecotank", "pixma", "smart tank", "maxify")
    )

    storage_token, screen_inches_token, _ = _extract_storage_and_inches(clean_title, specs)
    storage_num = re.sub(r"(?:gb|tb)$", "", storage_token, flags=re.IGNORECASE) if storage_token else None

    if is_tv:
        qs = build_search_queries(clean_title, {})
        if qs:
            toks = [t for t in qs[0].split() if t.lower() not in {"tizen", "neo"}]
            if screen_inches_token and screen_inches_token not in toks:
                if len(toks) >= 2 and toks[1].upper() in {"OLED", "QLED", "QNED"}:
                    toks.insert(2, screen_inches_token)
                elif len(toks) >= 1:
                    toks.insert(1, screen_inches_token)
                else:
                    toks.append(screen_inches_token)
            return " ".join(toks[:4])

    if is_printer:
        if "smart tank" in t_low:
            m_num = re.search(r"\b(\d{3,4})\b", t_low)
            return f"Smart Tank {m_num.group(1)}" if m_num else "Smart Tank"
        qs = build_search_queries(clean_title, specs)
        if qs:
            toks = [t for t in qs[0].split() if t.lower() not in {"pixma", "ecotank"}]
            return " ".join(toks[:3]) if toks else " ".join(qs[0].split()[:3])

    if is_laptop:
        cleaned_lap = re.sub(r"\b\d{1,4}\s*(?:gb|tb|ssd|mah|hz)\b", " ", _strip_accents(clean_title), flags=re.IGNORECASE)
        raw_tokens = re.findall(r"\b[a-zA-Z0-9\.]+\b", cleaned_lap)
        l_tokens: List[str] = []
        redundant_brands = set()
        if any(w in t_low for w in ("zenbook", "tuf", "vivobook", "rog")):
            redundant_brands.add("asus")
        if "macbook" in t_low:
            redundant_brands.add("apple")
        if any(w in t_low for w in ("ideapad", "thinkpad")):
            redundant_brands.add("lenovo")
        for tok in raw_tokens:
            low = tok.lower().strip(".")
            if not low or low in FORBIDDEN_QUERY_COLORS or low in FORBIDDEN_QUERY_MARKETING_WORDS or low in redundant_brands:
                continue
            if low in {"gamer", "amd", "ryzen", "intel", "core", "snapdragon", "rtx", "geforce", "4050", "3050", "5050", "210h", "7520u", "x"}:
                continue
            if low == "15.6" and any(x.lower() in {"victus", "loq"} for x in l_tokens):
                l_tokens.append("15")
                continue
            if re.match(r"^\d{2}(?:\.\d)?$", low) and float(low) in {13.0, 13.3, 13.6, 14.0, 15.6, 16.0}:
                continue
            if low in {"5", "7", "i5", "i7", "i9"} and len(l_tokens) >= 2:
                continue
            fmt = _format_token(low) if low != "ideapad" else "IdeaPad"
            if fmt.lower() not in [x.lower() for x in l_tokens]:
                l_tokens.append(fmt)
        return " ".join(l_tokens[:3])

    # Smartphones / Tablets / Otros: Familia/Modelo Base + Almacenamiento (sin GB), máx 3 a 4 tokens
    qs = build_search_queries(clean_title, specs)
    base_str = qs[1] if len(qs) >= 2 else (qs[0] if qs else clean_title)
    base_tokens = base_str.split()
    # Si tiene 'Galaxy' y 'Tab' juntos (ej. 'Galaxy Tab A11'), acortar a 'Tab A11'
    if len(base_tokens) >= 3 and base_tokens[0].lower() == "galaxy" and base_tokens[1].lower() == "tab":
        base_tokens = base_tokens[1:]
    # En 'Lenovo Idea Tab', si tiene '11"' en el título, conservar 'Idea Tab 11'
    if "idea" in t_low and "tab" in t_low:
        base_tokens = [t for t in base_tokens if t.lower() != "lenovo"]
        if "11" in t_low and "11" not in base_tokens:
            base_tokens.append("11")

    has_plus = any(t.lower() == "plus" for t in base_tokens)
    max_base = 5 if (has_plus and len(base_tokens) >= 4) else 3
    base_tokens = base_tokens[:max_base]
    if storage_num and storage_num not in [t.lower() for t in base_tokens]:
        base_tokens.append(storage_num)
    return " ".join(base_tokens[: (6 if has_plus else 4)])


def _unpack_product_input(
    product: Any,
    tech_specs: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], str, str]:
    if isinstance(product, str):
        return product, dict(tech_specs or {}), "", ""
    if isinstance(product, dict):
        return (
            str(product.get("title") or ""),
            dict(tech_specs or product.get("tech_specs") or product.get("raw_tech_specs") or {}),
            str(product.get("category") or ""),
            str(product.get("brand") or ""),
        )
    return (
        str(getattr(product, "title", "") or ""),
        dict(
            tech_specs
            or getattr(product, "tech_specs", None)
            or getattr(product, "raw_tech_specs", None)
            or {}
        ),
        str(getattr(product, "category", "") or ""),
        str(getattr(product, "brand", "") or ""),
    )


CLEAN_QUERY_CPU_NOISE: Set[str] = {
    "amd",
    "intel",
    "ryzen",
    "core",
    "qualcomm",
    "snapdragon",
    "exynos",
    "mediatek",
    "dimensity",
    "nvidia",
    "geforce",
    "rtx",
    "gtx",
    "3050",
    "4050",
    "4060",
    "5050",
    "210h",
    "7520u",
    "copilot",
    "pc",
    "tizen",
    "webos",
    "evo",
}


def build_clean_catalog_queries(
    product: Any,
    tech_specs: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Genera consultas limpias genéricas basadas en `tech_normalizer.py` preservando la marca,
    familia/modelo, pulgadas clave (tablets/TVs) y almacenamiento, eliminando tokens de relleno
    (`5G`, `Chip`, `RAM`, `Wi-Fi`, `Smart TV`, `Celular`, `Laptop`, colores, etc.).

    Ejemplos:
      - "Samsung Galaxy S26 Ultra 5G 512GB 12GB RAM" -> ["Samsung Galaxy S26 Ultra 512GB", "Samsung Galaxy S26 Ultra"]
      - 'Apple iPad 11" Chip A16 Wi-Fi 128GB' -> ["Apple iPad 11 128GB", "Apple iPad 11"]
    """
    raw_title, specs, category, explicit_brand = _unpack_product_input(product, tech_specs)
    if not raw_title:
        return []

    storage_token, screen_inches_token, cap_tokens = _extract_storage_and_inches(raw_title, specs)
    cleaned_norm = normalize_tech_text(
        raw_title,
        expand_abbrevs=True,
        strip_colors=True,
        strip_neutral=True,
    )
    # Remover capacidades de memoria/almacenamiento y decimales de pantalla del núcleo de tokens
    cleaned_core = re.sub(r"\b\d{1,4}(?:gb|tb|mah|mp|hz|w)\b", " ", cleaned_norm)
    cleaned_core = re.sub(r"\b\d{1,2}\.\d+\b", " ", cleaned_core)

    cat_low = category.lower()
    is_tv = cat_low == "tvs" or any(w in cleaned_norm for w in ("oled", "qled", "qned", "nanocell", "u8000"))
    is_tablet = cat_low == "tablets" or any(w in cleaned_norm for w in ("ipad", "tab", "pad"))
    is_laptop = cat_low == "laptops" or any(
        w in cleaned_norm for w in ("macbook", "zenbook", "ideapad", "victus", "tuf", "loq", "thinkpad", "vivobook")
    )

    extra_drop = (
        set(FORBIDDEN_QUERY_COLORS)
        | set(FORBIDDEN_QUERY_MARKETING_WORDS)
        | DEFAULT_NEUTRAL_TOKENS
        | CLEAN_QUERY_CPU_NOISE
        | cap_tokens
    )

    tokens = re.findall(r"\b[a-z0-9]+\b", cleaned_core)
    model_tokens: List[str] = []

    if explicit_brand:
        b_norm = _strip_accents(explicit_brand).lower().strip()
        if b_norm and b_norm not in extra_drop:
            model_tokens.append(_format_token(b_norm))

    # Detectar si hay sufijo de tamaño decimal como 15.6" en Victus/LOQ que suelen nombrarse "15"
    has_15_6 = bool(re.search(r"\b15\.6\b", raw_title))

    for i, tok in enumerate(tokens):
        if tok in extra_drop:
            continue
        # Omitir año de modelo salvo si no hay otros números
        if tok in {"2023", "2024", "2025", "2026", "2027"}:
            continue
        # En iPad / Tablet con diagonal en pulgadas explícita, omitir token de chip SoC (a16, a17, a15)
        # para encontrar títulos retail como 'Apple iPad 11" 128GB Plata' sin 'Chip A16'
        if is_tablet and screen_inches_token and re.match(r"^a1[4-9]$", tok):
            continue
        # En laptops, omitir número suelto de tier CPU (3/5/7/9) o 'x' después de AMD/Intel/Snapdragon
        if is_laptop and tok in {"3", "5", "7", "9", "i3", "i5", "i7", "i9", "x"}:
            prev_tok = tokens[i - 1] if i > 0 else ""
            if prev_tok in CLEAN_QUERY_CPU_NOISE or tok in {"i3", "i5", "i7", "i9", "x"}:
                continue
        if is_laptop and tok in {"13", "14", "15", "16"} and not any(x in tokens for x in ("victus", "loq")):
            # En laptops como IdeaPad Slim 3 / Zenbook A14 / MacBook Air 13: conservar '13' en MacBook Air 13, omitir '14'/'15' redundante
            if "macbook" not in tokens:
                continue

        # Expandir códigos OLED55C6PSA -> OLED 55 C6
        m_oled = re.match(r"^oled(\d{2})([a-z]\d+)[a-z]*$", tok)
        if m_oled:
            if not screen_inches_token:
                screen_inches_token = m_oled.group(1)
            tok = m_oled.group(2)

        fmt = _format_token(tok) if tok != "ideapad" else "IdeaPad"
        if tok == "macbook":
            fmt = "MacBook"
        if fmt.lower() not in [m.lower() for m in model_tokens]:
            model_tokens.append(fmt)

    # Insertar pulgadas enteras donde aporta valor de búsqueda (tablets como iPad 11 / Idea Tab 11 y TVs 55 / 65)
    if screen_inches_token:
        if is_tv and screen_inches_token not in [m.lower() for m in model_tokens]:
            insert_idx = 2 if len(model_tokens) >= 2 and model_tokens[1].upper() in {"OLED", "QLED", "QNED", "UHD", "NEO"} else min(len(model_tokens), 1)
            model_tokens.insert(insert_idx, screen_inches_token)
        elif is_tablet and screen_inches_token in {"10", "11", "12", "13"} and screen_inches_token not in [m.lower() for m in model_tokens]:
            model_tokens.append(screen_inches_token)
    elif is_laptop and has_15_6 and any(m.lower() in {"victus", "loq"} for m in model_tokens) and "15" not in model_tokens:
        model_tokens.append("15")

    broad_clean = " ".join(model_tokens).strip()
    queries: List[str] = []
    if storage_token and broad_clean:
        with_stor = f"{broad_clean} {storage_token}".strip()
        queries.append(with_stor)
    if broad_clean and broad_clean not in queries:
        queries.append(broad_clean)

    return queries


def build_clean_catalog_query(
    product: Any,
    tech_specs: Optional[Dict[str, Any]] = None,
) -> str:
    """Retorna la consulta limpia principal generada con `tech_normalizer.py`."""
    qs = build_clean_catalog_queries(product, tech_specs=tech_specs)
    return qs[0] if qs else ""
