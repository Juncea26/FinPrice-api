"""
Capa Genérica y Escalable de Normalización, Guardrails y Extracción de Códigos
de Producto para Tecnología (tech_normalizer.py).

Diseñada sin reglas hardcodeadas por producto individual para soportar tanto el catálogo
actual como miles de productos futuros de retail peruano:
1. Normalización unificada de RAM/Almacenamiento (12 GB -> 12gb, 12/512GB -> 12gb 512gb, 1 TB -> 1tb).
2. Diccionario genérico de abreviaturas del retail peruano (r5 -> ryzen 5, ci5/c5 -> core i5,
   ips3 -> ideapad slim 3, rtx4050 -> rtx 4050, + -> plus, etc.).
3. Tokens neutros configurables (celular, smartphone, libre, 5g, chip, wi-fi, ram, smart tv, colores).
4. Guardrails estrictos (capacidad, modificadores Pro/Pro+/Plus/Ultra/Air/FE/Lite/Max/Essential,
   pulgadas en TVs vs tablets/laptops, CPU/GPU, bloqueo de accesorios/tintas).
5. Extractor genérico de EAN / GTIN / MPN desde JSON-LD, __NEXT_DATA__, metadatos HTML y fichas técnicas.
"""
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from app.collectors.color_stripper import SINGLE_COLOR_TOKENS, strip_color_tokens

# ==============================================================================
# 1. DICCIONARIOS Y CONSTANTES GENÉRICAS DE RETAIL PERÚ
# ==============================================================================

VALID_STORAGE_NUMS_GB: Set[int] = {
    32, 64, 128, 256, 480, 500, 512, 960, 1000, 1024, 2000, 2048, 4000, 4096, 6000, 6144, 8000, 8192
}
VALID_RAM_NUMS_GB: Set[int] = {2, 3, 4, 6, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96, 128}
STANDARD_STORAGE_TOKENS: Set[str] = {
    "32gb",
    "64gb",
    "128gb",
    "256gb",
    "480gb",
    "500gb",
    "512gb",
    "960gb",
    "1000gb",
    "1024gb",
    "2000gb",
    "2048gb",
    "4000gb",
    "4096gb",
    "6000gb",
    "6144gb",
    "8000gb",
    "8192gb",
    "1tb",
    "2tb",
    "4tb",
    "6tb",
    "8tb",
}

TV_STANDARD_INCHES: Set[int] = {
    32, 40, 42, 43, 48, 50, 55, 58, 60, 65, 70, 75, 77, 83, 85, 86, 98
}

MONITOR_STANDARD_INCHES: Set[str] = {
    "15.6", "18.5", "19", "19.5", "20", "21.5", "22", "23.8", "24", "24.5",
    "25", "27", "28", "29", "31.5", "32", "34", "35", "38", "40", "43", "45", "49",
}

COMMERCIAL_SCREEN_GROUPS: Tuple[Set[str], ...] = (
    {"8.3", "8.4"},
    {"8.7", "8.8"},
    {"10.1"},
    {"10.8", "10.9", "11", "11.0"},
    {"12.4", "12.7", "12.9"},
    {"13", "13.0", "13.3", "13.6"},
    {"14", "14.0", "14.2"},
    {"15", "15.0", "15.3", "15.6"},
    {"16", "16.0", "16.1", "16.2"},
    {"17", "17.0", "17.3"},
)

ALL_TABLET_LAPTOP_SCREEN_SIZES: Set[str] = {
    "8.3", "8.7", "10.1", "10.9", "11", "12.4", "12.7", "12.9",
    "13", "13.3", "13.6", "14", "15", "15.3", "15.6", "16", "17",
}

# Abreviaturas estándar del retail peruano (Magento, VTEX, Falabella, Ripley)
RETAIL_ABBREVIATIONS: Dict[str, str] = {
    "r3": "ryzen 3",
    "r5": "ryzen 5",
    "r7": "ryzen 7",
    "r9": "ryzen 9",
    "ci3": "core i3",
    "c3": "core i3",
    "ci5": "core i5",
    "c5": "core i5",
    "ci7": "core i7",
    "c7": "core i7",
    "ci9": "core i9",
    "c9": "core i9",
    "cu5": "core ultra 5",
    "cu7": "core ultra 7",
    "cu9": "core ultra 9",
    "ips1": "ideapad slim 1",
    "ip1": "ideapad slim 1",
    "ips3": "ideapad slim 3",
    "ip3": "ideapad slim 3",
    "ips5": "ideapad slim 5",
    "ip5": "ideapad slim 5",
    "ps5": "playstation 5",
    "ps4": "playstation 4",
    "lapg": "laptop gamer",
}

# Tokens neutros descriptivos que pueden omitirse al comparar identidad
COLOR_NEUTRAL_TOKENS: Set[str] = (
    set(SINGLE_COLOR_TOKENS)
    | {
        "".join(
            c for c in unicodedata.normalize("NFKD", tok.lower()) if not unicodedata.combining(c)
        )
        for tok in SINGLE_COLOR_TOKENS
    }
    | {
        "plata",
        "plateado",
        "negro",
        "blanco",
        "azul",
        "gris",
        "plomo",
        "rosa",
        "rosado",
        "amarillo",
        "moca",
        "cafe",
        "marron",
        "estelar",
        "espacial",
        "natural",
        "titanio",
        "titanium",
        "cielo",
        "oro",
        "dorado",
        "verde",
        "morado",
        "purpura",
        "violeta",
        "rojo",
        "grafito",
        "medianoche",
        "indigo",
        "bone",
        "sand",
        "cream",
        "hueso",
        "ivory",
        "marfil",
        "beige",
        "mint",
        "menta",
        "teal",
        "coral",
        "peach",
        "durazno",
        "blush",
        "lavender",
        "lavanda",
        "sage",
        "olive",
        "oliva",
        "slate",
        "obsidian",
        "starlight",
        "champagne",
        "cobalt",
        "cobalto",
        "cyan",
        "aqua",
        "turquoise",
        "turquesa",
        "sierra",
        "burgundy",
        "vino",
        "guinda",
        "mostaza",
        "fucsia",
        "nude",
        "cobre",
        "copper",
        "bronce",
        "bronze",
        "rose",
        "tidal",
        "meteor",
        "sunrise",
        "misty",
        "lunar",
        "glaciar",
        "oscuro",
        "claro",
        "deep",
        "stellar",
        "nebula",
        "luna",
        "polar",
        "eclipse",
        "arena",
        "celeste",
        "naranja",
        "orange",
        "silver",
        "black",
        "white",
        "blue",
        "gray",
        "grey",
        "pink",
        "yellow",
        "brown",
        "gold",
        "green",
        "purple",
        "lilac",
        "red",
        "graphite",
        "midnight",
        "navy",
        "slv",
        "blk",
        "wht",
        "gry",
        "blu",
        "pnk",
        "ylw",
        "gld",
    }
)

DEFAULT_NEUTRAL_TOKENS: Set[str] = COLOR_NEUTRAL_TOKENS | {
    "celular",
    "celulares",
    "smartphone",
    "smartphones",
    "movil",
    "telefono",
    "libre",
    "liberado",
    "liberada",
    "desbloqueado",
    "desbloqueada",
    "dual",
    "sim",
    "esim",
    "5g",
    "chip",
    "procesador",
    "wi-fi",
    "wifi",
    "wi",
    "fi",
    "wlan",
    "bluetooth",
    "bt",
    "ram",
    "rom",
    "memoria",
    "interna",
    "unificada",
    "disco",
    "solido",
    "unidad",
    "estado",
    "ssd",
    "smart",
    "tv",
    "televisor",
    "tablet",
    "tableta",
    "laptop",
    "notebook",
    "portatil",
    "impresora",
    "multifuncional",
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
    "gen",
    "generacion",
    "ai",
    "thinq",
    "dolby",
    "atmos",
    "vision",
    "4k",
    "uhd",
    "fhd",
    "hd",
    "wuxga",
    "oled",
    "amoled",
    "cla",
    "bes",
    "lep",
    "ltp",
}

# Modificadores estrictos de gama/modelo que NUNCA pueden diferir entre objetivo y candidato
# Nota: 'pro+' se representa como {'pro', 'plus'} tras la normalización de '+' -> ' plus '.
STRICT_MODEL_MODIFIERS: Tuple[str, ...] = (
    "pro",
    "plus",
    "ultra",
    "air",
    "fe",
    "lite",
    "max",
    "essential",
    "mini",
    "fold",
    "flip",
    "16e",
    "15e",
)

# Palabras de accesorios, consumibles y reacondicionados (excluye falsos positivos con impresoras reales)
NON_INK_ACCESSORY_KEYWORDS: Tuple[str, ...] = (
    "funda",
    "fundas",
    "case",
    "cases",
    "protector",
    "protectores",
    "mica",
    "micas",
    "cargador",
    "cargadores",
    "cable",
    "cables",
    "adaptador",
    "adaptadores",
    "audifono",
    "audifonos",
    "reloj",
    "relojes",
    "band",
    "correa",
    "correas",
    "carcasa",
    "carcasas",
    "estuche",
    "estuches",
    "soporte",
    "soportes",
    "holder",
    "glass",
    "templado",
    "teclado",
    "keyboard",
    "trackpad",
    "folio",
    "pencil",
    "stylus",
    "lapiz",
    "botella",
    "botellas",
    "cartucho",
    "cartuchos",
    "toner",
    "cabezal",
    "recarga",
    "reacondicionado",
    "reacondicionados",
    "reacondicionada",
    "refurbished",
    "renovado",
    "renovada",
    "seminuevo",
    "openbox",
)

NON_MPN_TECH_WORDS: Set[str] = {
    "64gb", "128gb", "256gb", "512gb", "1024gb", "2048gb", "1tb", "2tb", "4tb",
    "4gb", "6gb", "8gb", "12gb", "16gb", "18gb", "24gb", "32gb", "64gb",
    "wifi6", "wifi6e", "wifi7", "hdr10", "1080p", "1440p", "2160p", "4kuhd",
    "ryzen3", "ryzen5", "ryzen7", "ryzen9", "corei3", "corei5", "corei7", "corei9",
    "rtx3050", "rtx4050", "rtx4060", "rtx4070", "rtx5050", "rtx5060",
    "android14", "android15", "android16", "ios17", "ios18", "ios19",
    "ipados18", "win11", "windows11", "usb30", "usb32", "mpn000",
}


def strip_accents_lower(text: str) -> str:
    if not text:
        return ""
    cleaned = (
        str(text)
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2033", '"')
        .replace("\u201f", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2032", "'")
        .replace("\u2122", " ")
        .replace("\u00ae", " ")
    )
    decomposed = unicodedata.normalize("NFKD", cleaned.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _word_in_text(token: str, normalized_text: str) -> bool:
    if not token or not normalized_text:
        return False
    return bool(re.search(rf"\b{re.escape(token.lower())}\b", normalized_text))


# ==============================================================================
# 2. NORMALIZACIÓN DE MEMORIA / ALMACENAMIENTO Y ABREVIATURAS RETAIL
# ==============================================================================

def _strip_gpu_vram_tokens(text: str) -> str:
    """Elimina la capacidad VRAM pegada tras GPU dedicada (ej. 'RTX 3050 6GB' -> 'RTX 3050')."""
    if not text:
        return ""
    return re.sub(
        r"\b((?:rtx|gtx)\s*\d{4}(?:\s*(?:ti|super))?)\s+\d{1,2}\s*(?:gb|g)\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )


def normalize_memory_and_storage(text: str) -> str:
    """
    Unifica notaciones de RAM y almacenamiento:
    - '12 GB' -> '12gb', '512 GB' -> '512gb', '1 TB' -> '1tb'
    - '12/512GB', '12+512 GB', '12Gb Ram + 512Gb Rom' -> '12gb 512gb'
    - '16/1TB', '16+1 TB' -> '16gb 1tb'
    - '256SSD', '512SSD', '1TBSSD' -> '256gb ssd', '512gb ssd', '1tb ssd'
    - '8RAM', '16RAM', '8G RAM 256G ROM' -> '8gb ram', '16gb ram', '8gb ram 256gb rom'
    """
    if not text:
        return ""
    out = strip_accents_lower(text)

    # 1. Combos RAM/Storage con '+', '/' o '-' antes de expandir '+' a 'plus'
    out = re.sub(
        r"\b(\d{1,2})\s*(?:gb|g)?(?:\s*ram)?\s*[+/]\s*(\d{2,4})\s*(gb|g|tb)(?:\s*(?:rom|ssd|ufs))?\b",
        lambda m: f" {m.group(1)}gb {m.group(2)}{'tb' if 'tb' in m.group(3) else 'gb'} ",
        out,
    )
    out = re.sub(
        r"\b(\d{1,2})\s*(?:gb|g)?(?:\s*ram)?\s*[+/]\s*(\d)\s*(tb)(?:\s*(?:rom|ssd))?\b",
        lambda m: f" {m.group(1)}gb {m.group(2)}tb ",
        out,
    )
    out = re.sub(
        r"\b(2|3|4|6|8|12|16|24|32)\s*[+/]\s*(32|64|128|256|512|1024|2048)\b",
        r" \1gb \2gb ",
        out,
    )
    out = re.sub(
        r"\b(2|3|4|6|8|12|24|32)\s*-\s*(32|64|128|256|512|1024|2048)\b",
        r" \1gb \2gb ",
        out,
    )

    # 2. Notación compacta SSD y RAM ('256SSD', '1TBSSD', '8RAM', '16RAM', '8G RAM 256G ROM')
    out = re.sub(
        r"\b(32|64|128|256|480|500|512|960|1000|1024|2048)\s*(?:gb|g)?\s*ssd\b",
        r"\1gb ssd",
        out,
    )
    out = re.sub(r"\b([1248])\s*(?:tb|t)?\s*ssd\b", r"\1tb ssd", out)
    out = re.sub(
        r"\b(2|3|4|6|8|12|16|18|24|32|36|48|64)\s*(?:gb|g)?\s*ram\b",
        r"\1gb ram",
        out,
    )
    out = re.sub(
        r"\b(2|3|4|6|8|12|16|24|32|64|128|256|512|1024)\s*g\b(?=\s*(?:ram|rom|ssd|blue|black|green|white|gray|gris|negro|azul|plata)\b)",
        r"\1gb",
        out,
    )
    # Capacidades estándar abreviadas como '/8G' o '512G' sin confundir '4G'/'5G' móviles
    out = re.sub(
        r"\b(8|12|16|24|32|64|128|256|512|1024)g\b",
        r"\1gb",
        out,
    )

    # 3. Quitar espacios entre número y unidad ('12 gb' -> '12gb', '1 tb' -> '1tb')
    out = re.sub(r"\b(\d{1,4})\s*(gb|tb)\b", r"\1\2", out)

    # 4. Separar capacidad pegada a sufijo ('512gbram' -> '512gb ram', '512gbssd' -> '512gb ssd')
    out = re.sub(r"\b(\d{1,4}(?:gb|tb))(ram|rom|ssd|nvme)\b", r"\1 \2", out)

    return re.sub(r"\s+", " ", out).strip()


def normalize_plus_tokens(text: str) -> str:
    """
    Convierte '+' de variante de modelo ('Pro+', 'A11+', 'S24+') en ' plus ',
    preservando resoluciones ('FHD+', 'Copilot+') y regalos de bundle ('+ Funda').
    Nota: debe llamarse después de normalize_memory_and_storage para no alterar '12+512GB'.
    """
    if not text:
        return ""
    out = str(text)
    out = re.sub(r"(?i)\b(fhd|qhd|uhd|hd|wxga|wqhd|hdr10|hdr|dolby|copilot)\s*\+", r"\1 ", out)
    out = re.sub(
        r"(?i)\+\s*(?=(?:funda|case|folio|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|lapiz|pen|stylus|combo|pack|tags?|regalo|hph|watch|buds)\b)",
        " ",
        out,
    )
    out = re.sub(r"(?i)\b(pro|note|tab|pad|s\d+|a\d+|g\d+|moto|magic|fold|flip)\s*\+", r"\1 plus ", out)
    out = re.sub(r"\+", " plus ", out)
    return re.sub(r"\s+", " ", out).strip()


def expand_retail_abbreviations(text: str) -> str:
    """
    Expande abreviaturas estándar del retail peruano y tokens alfanuméricos pegados:
    - r5 -> ryzen 5, r7 -> ryzen 7, ci5/c5 -> core i5, ci7/c7 -> core i7
    - ips3/ip3 -> ideapad slim 3, ips5/ip5 -> ideapad slim 5
    - rtx4050 -> rtx 4050, proplus -> pro plus, note15pro -> note 15 pro
    Evita expandir c3/c5/c7 si el contexto corresponde a televisores OLED/QLED/Smart TV.
    """
    if not text:
        return ""
    out = strip_accents_lower(text)
    out = normalize_memory_and_storage(out)
    out = normalize_plus_tokens(out)

    # Conservar decimales de pulgadas antes de limpiar signos de puntuación
    out = re.sub(r"(\d{1,2})\.(\d)\b", r"\1_DEC_\2", out)
    out = re.sub(r"[/\-_\.+%=&?,:;()\[\]\"'{}]+", " ", out)
    out = out.replace(" DEC ", ".")

    # Separar GPU pegadas (rtx4050 -> rtx 4050, gtx1650 -> gtx 1650)
    out = re.sub(r"\b(rtx|gtx)\s*(\d{4})(ti|super)?\b", r"\1 \2 \3", out)

    # Separar prefijos y sufijos comunes en slugs de tiendas
    out = re.sub(r"\b(pro)(plus)\b", r"\1 \2", out)
    out = re.sub(
        r"\b(oled|qned|nanocell)(\d{2})([bcgmrwz]\d)([a-z0-9]*)\b",
        r"\1 \2 \3 \4",
        out,
    )
    out = re.sub(
        r"\b(note|magic|pad|loq|tab|victus)(\d+)(pro|lite|ultra|plus|fe)?(plus)?(5g)?\b",
        r"\1 \2 \3 \4 \5",
        out,
    )
    out = re.sub(r"\b([a-z]\d+)(pro|plus|ultra|max|fe|lite)\b", r"\1 \2", out)
    out = re.sub(r"\b(\d+)(pro|plus|ultra|max|fe|lite)(5g)?\b", r"\1 \2 \3", out)

    is_tv_context = any(
        _word_in_text(tok, out)
        for tok in ("tv", "televisor", "smart tv", "oled", "qled", "qned", "nanocell", "uhd")
    )

    tokens = out.split()
    expanded_tokens: List[str] = []
    for tok in tokens:
        if tok in {"c3", "c5", "c7", "c9"} and is_tv_context:
            expanded_tokens.append(tok)
            continue
        if tok in RETAIL_ABBREVIATIONS:
            expanded_tokens.extend(RETAIL_ABBREVIATIONS[tok].split())
        else:
            expanded_tokens.append(tok)

    return re.sub(r"\s+", " ", " ".join(expanded_tokens)).strip()


def strip_neutral_tokens(
    text: str,
    extra_neutral: Optional[Iterable[str]] = None,
) -> str:
    """Elimina tokens descriptivos neutros (colores, 5g, chip, wi-fi, ram, smart tv, etc.)."""
    if not text:
        return ""
    neutral_set: Set[str] = set(DEFAULT_NEUTRAL_TOKENS)
    if extra_neutral:
        neutral_set.update(strip_accents_lower(str(t)).strip() for t in extra_neutral if t)

    tokens = str(text).split()
    kept = [t for t in tokens if t.lower() not in neutral_set]
    return " ".join(kept).strip()


def normalize_tech_text(
    text: str,
    expand_abbrevs: bool = True,
    strip_colors: bool = False,
    strip_neutral: bool = False,
    extra_neutral: Optional[Iterable[str]] = None,
) -> str:
    """
    Pipeline completo de normalización genérica de texto técnico.
    """
    if not text:
        return ""
    raw = str(text)
    # Preservar decimales de pantalla al limpiar unidades tipo pulgadas
    raw = re.sub(
        r"\b(\d{1,3}(?:\.\d{1,2})?)\s*(?:\"|''|pulgadas|pulg|inch|inches)\b",
        r"\1 ",
        raw,
        flags=re.IGNORECASE,
    )
    if strip_colors:
        # Normalizar capacidades primero para que color_stripper no pierda unidades pegadas
        raw = normalize_memory_and_storage(raw)
        raw = strip_color_tokens(raw)

    if expand_abbrevs:
        out = expand_retail_abbreviations(raw)
    else:
        out = normalize_plus_tokens(normalize_memory_and_storage(raw))
        out = re.sub(r"(\d{1,2})\.(\d)\b", r"\1_DEC_\2", out)
        out = re.sub(r"[/\-_\.+%=&?,:;()\[\]\"'{}]+", " ", out)
        out = re.sub(r"\s+", " ", out.replace(" DEC ", ".")).strip()

    if strip_neutral:
        out = strip_neutral_tokens(out, extra_neutral=extra_neutral)

    return re.sub(r"\s+", " ", out).strip()


# ==============================================================================
# 3. EXTRACTORES DE ATRIBUTOS ESTRICTOS Y GUARDRAILS DE SEGURIDAD
# ==============================================================================

_STORAGE_TB_EQUIV: Dict[str, str] = {
    "1000gb": "1tb",
    "1024gb": "1tb",
    "2000gb": "2tb",
    "2048gb": "2tb",
    "4000gb": "4tb",
    "4096gb": "4tb",
    "6000gb": "6tb",
    "6144gb": "6tb",
    "8000gb": "8tb",
    "8192gb": "8tb",
}


def extract_storage_tokens(normalized_text: str, allow_small_external: bool = False) -> Set[str]:
    """Devuelve capacidades de almacenamiento presentes ('32gb'..'8tb'), unificando '1024gb' == '1tb'."""
    if not normalized_text:
        return set()
    found: Set[str] = set()
    for m in re.findall(r"\b(\d{1,4}(?:gb|tb))\b", normalized_text):
        if m in _STORAGE_TB_EQUIV:
            found.add(_STORAGE_TB_EQUIV[m])
        elif m in STANDARD_STORAGE_TOKENS or (allow_small_external and m in {"8gb", "16gb"}):
            found.add(m)
    return found


def extract_ram_tokens(normalized_text: str) -> Set[str]:
    """Devuelve capacidades de RAM (< 64GB) presentes ('4gb', '8gb', '12gb', '16gb', etc.)."""
    if not normalized_text:
        return set()
    found: Set[str] = set()
    for m_num in re.findall(r"\b(\d{1,2})gb\b", normalized_text):
        val = int(m_num)
        if val in VALID_RAM_NUMS_GB and val < 64:
            found.add(f"{val}gb")
    return found


def extract_screen_inches_from_text(raw_text: str) -> Optional[float]:
    """Extrae diagonal principal en pulgadas si se declara con comillas o contexto de pantalla."""
    if not raw_text:
        return None
    clean = strip_accents_lower(raw_text)
    m = re.search(
        r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|''|(?:pulgadas|pulg|inch|inches)\b)",
        clean,
    )
    if m:
        return float(m.group(1))
    return None


def _get_tablet_laptop_screen_group(inches: float) -> Set[str]:
    clean_s = f"{inches:.1f}".rstrip("0").rstrip(".")
    for grp in COMMERCIAL_SCREEN_GROUPS:
        if clean_s in grp:
            return grp
    return {clean_s, str(int(round(inches)))}


def extract_cpu_and_gpu_signatures(normalized_text: str) -> Dict[str, Optional[str]]:
    """
    Extrae arquitectura/nivel de CPU, SKU de procesador y GPU de forma genérica:
    - cpu_vendor: 'amd' | 'intel' | 'apple' | 'qualcomm'
    - cpu_tier: e.g. 'ryzen_5', 'ryzen_ai_7', 'intel_3', 'intel_5', 'intel_ultra_7', 'apple_m5', 'apple_a18_pro'
    - cpu_sku: e.g. '304', '120u', '7520u', '205h'
    - gpu_model: e.g. 'rtx_4050', 'rtx_5050'
    """
    if not normalized_text:
        return {"cpu_vendor": None, "cpu_tier": None, "cpu_sku": None, "gpu_model": None}

    t = normalized_text
    cpu_vendor: Optional[str] = None
    cpu_tier: Optional[str] = None
    cpu_sku: Optional[str] = None
    gpu_model: Optional[str] = None

    m_ryzen_ai = re.search(r"\bryzen\s+(?:ai|ia)\s*([579])\b", t)
    m_ryzen = re.search(r"\bryzen\s*([3579])\b", t)
    m_intel_ultra = re.search(r"\bcore\s+(?:ultra|u)\s*([579])\b", t)
    m_intel = re.search(r"\b(?:intel\s+)?core\s*i?([3579])\b", t) or re.search(r"\bi([3579])\b", t)
    m_athlon = re.search(r"\bathlon\b", t)
    m_celeron = re.search(r"\bceleron\b", t)
    m_apple_m = re.search(r"\b(m[1-5])\b", t)
    m_apple_a18_pro = re.search(r"\ba18\s*pro\b", t)
    m_apple_a = re.search(r"\b(a1[4-9])\b", t)
    m_snap = re.search(r"\bsnapdragon\b", t)

    if m_ryzen_ai:
        cpu_vendor = "amd"
        cpu_tier = f"ryzen_ai_{m_ryzen_ai.group(1)}"
    elif m_ryzen or _word_in_text("ryzen", t) or _word_in_text("amd", t):
        cpu_vendor = "amd"
        if m_ryzen:
            cpu_tier = f"ryzen_{m_ryzen.group(1)}"
        elif m_athlon:
            cpu_tier = "amd_athlon"
    elif m_intel_ultra:
        cpu_vendor = "intel"
        cpu_tier = f"intel_ultra_{m_intel_ultra.group(1)}"
    elif m_intel or _word_in_text("intel", t) or m_celeron:
        cpu_vendor = "intel"
        if m_intel:
            cpu_tier = f"intel_{m_intel.group(1)}"
        elif m_celeron:
            cpu_tier = "intel_celeron"
    elif m_apple_m:
        cpu_vendor = "apple"
        cpu_tier = f"apple_{m_apple_m.group(1)}"
    elif m_apple_a18_pro:
        cpu_vendor = "apple"
        cpu_tier = "apple_a18_pro"
    elif m_apple_a:
        cpu_vendor = "apple"
        cpu_tier = f"apple_{m_apple_a.group(1)}"
    elif m_snap:
        cpu_vendor = "qualcomm"

    m_sku = (
        re.search(r"\bcore\s+(?:ultra\s+|u\s+|i)?[3579]\s+(\d{3}[uh]?\b|\d{4,5}[a-z]{1,2}\b)", t)
        or re.search(r"\bi[3579]\s+(\d{3,5}[a-z]{1,2})\b", t)
        or re.search(r"\bryzen\s+(?:(?:ai|ia)\s+)?[3579]\s+(\d{3,4}[a-z]{0,2})\b", t)
    )
    if m_sku and m_sku.group(1) not in {"8gb", "12gb", "16gb", "32gb", "256gb", "512gb", "1000", "2024", "2025", "2026"}:
        cpu_sku = m_sku.group(1).lower()

    m_gpu = re.search(r"\b(rtx|gtx)\s*(\d{4})\b", t)
    if m_gpu:
        gpu_model = f"{m_gpu.group(1)}_{m_gpu.group(2)}"

    return {
        "cpu_vendor": cpu_vendor,
        "cpu_tier": cpu_tier,
        "cpu_sku": cpu_sku,
        "gpu_model": gpu_model,
    }


def _has_forbidden_accessory_or_ink(
    canonical_norm: str,
    cand_title_norm: str,
    cand_url_norm: str,
) -> bool:
    """
    Bloquea accesorios, fundas, protectores, reacondicionados y botellas/cartuchos de tinta,
    permitiendo impresoras reales de tinta continua cuando el título corresponde a una impresora.
    """
    check_text = cand_title_norm or cand_url_norm
    if not check_text:
        return False

    if "open box" in check_text or "open box" in cand_url_norm:
        return True

    is_audio_target = any(
        tok in canonical_norm
        for tok in ("airpods", "headphone", "earphone", "audifono", "auricular")
    )

    for kw in NON_INK_ACCESSORY_KEYWORDS:
        if kw in {"audifono", "audifonos"} and is_audio_target:
            continue
        if _word_in_text(kw, check_text) and not _word_in_text(kw, canonical_norm):
            return True

    # Protección especial para tintas/consumibles vs impresoras multifuncionales
    cand_mentions_ink = _word_in_text("tinta", check_text) or _word_in_text("tintas", check_text)
    if cand_mentions_ink and not (_word_in_text("tinta", canonical_norm) or _word_in_text("tintas", canonical_norm)):
        is_actual_printer = any(
            _word_in_text(p_tok, check_text)
            for p_tok in ("impresora", "multifuncional", "ecotank", "pixma", "smart tank", "sistema continuo")
        ) or ("tinta continua" in check_text)
        has_consumable_marker = any(
            _word_in_text(c_tok, check_text)
            for c_tok in ("botella", "botellas", "cartucho", "cartuchos", "pack", "recarga", "repuesto")
        )
        if has_consumable_marker or not is_actual_printer:
            return True

    return False


_PERIPHERAL_COMBO_PREFIX_TOKENS: Tuple[str, ...] = (
    "teclado",
    "keyboard",
    "mouse",
    "raton",
    "combo",
    "kit",
    "set",
)

_BUNDLE_PAT_RE = re.compile(
    r"\s*(?P<conn>\+|\bcon\b|\bincluye\b)\s*"
    r"(?P<item>funda|case|folio|book\s*cover|cargador|audifonos?(?:\s+inalambricos?)?|mochila|mouse|cover|"
    r"soundbar|maletin|teclado|lapiz|pen|stylus|combo|pack|tags?|regalo|hph|watch|buds)\b(?P<tail>.*)$",
    flags=re.IGNORECASE,
)


def _strip_bundles_and_colors(text: str, category: str = "") -> str:
    """
    Recorta regalos de bundle agregados (`+ Funda`, `con Audífonos`, etc.), pero preserva
    combos reales de periféricos (`Teclado Logitech + Mouse MK470`) y packs (`+ Pack 3`).
    """
    if not text:
        return ""
    raw = str(text)
    cat_low = strip_accents_lower(category or "").strip()

    for m in _BUNDLE_PAT_RE.finditer(raw):
        item_low = strip_accents_lower(m.group("item"))
        prefix_low = strip_accents_lower(raw[: m.start()])
        tail_low = strip_accents_lower(m.group("tail") or "")

        # Preservar combos reales de teclado + mouse (`Teclado Logitech + Mouse MK470`)
        if item_low in {"mouse", "teclado"}:
            if cat_low == "accesorios_pc" or any(
                _word_in_text(pw, prefix_low) for pw in _PERIPHERAL_COMBO_PREFIX_TOKENS
            ):
                continue

        # Preservar packs numéricos explícitos y kits en redes / domótica / periféricos
        if item_low in {"pack", "combo"}:
            if cat_low in {"accesorios_pc", "almacenamiento_redes", "smart_home"} or re.match(
                r"^\s*(?:de\s+|x\s*)?\d+\b", tail_low
            ):
                continue

        return raw[: m.start()].strip()

    return raw.strip()


_URL_BUNDLE_GIFT_TOKENS: Set[str] = {
    "funda",
    "fundas",
    "case",
    "cases",
    "folio",
    "book",
    "cover",
    "cargador",
    "cargadores",
    "audifono",
    "audifonos",
    "inalambrico",
    "inalambricos",
    "mochila",
    "mouse",
    "soundbar",
    "maletin",
    "teclado",
    "keyboard",
    "lapiz",
    "pen",
    "stylus",
    "combo",
    "pack",
    "tags",
    "tag",
    "regalo",
    "gratis",
    "hph",
    "watch",
    "buds",
}

_URL_BUNDLE_STANDALONE_ACC_NOUNS: Set[str] = {
    "funda",
    "fundas",
    "case",
    "cases",
    "protector",
    "protectores",
    "mica",
    "micas",
    "cargador",
    "cargadores",
    "cable",
    "cables",
    "adaptador",
    "adaptadores",
    "carcasa",
    "estuche",
    "soporte",
    "holder",
    "cover",
    "teclado",
    "keyboard",
    "pencil",
    "stylus",
    "lapiz",
    "folio",
}


def strip_url_bundle_tail(url_norm: str) -> str:
    """
    Elimina de forma genérica sufijos promocionales/regalos encadenados al final del slug de URL
    (ej. '-folio-case-lapiz', '-audifono-inalambrico/20261891', '-modelo-ux3407qa-qd289w-funda'),
    protegiendo URLs que corresponden realmente a un accesorio independiente
    (como 'funda-tablet-lenovo-idea-tab-11' o 'samsung-galaxy-s26-ultra-case').
    """
    if not url_norm:
        return ""
    tokens = str(url_norm).split()
    if len(tokens) < 3:
        return url_norm

    trailing_sku: Optional[str] = None
    work = list(tokens)
    if re.match(r"^\d{5,15}p?$", work[-1]):
        trailing_sku = work.pop()

    if len(work) < 3:
        return url_norm

    stripped_tail: List[str] = []
    while len(work) >= 3:
        last_tok = work[-1].lower()
        if last_tok in _URL_BUNDLE_GIFT_TOKENS:
            stripped_tail.append(work.pop())
        elif stripped_tail and last_tok in {"con", "incluye", "mas", "plus"}:
            work.pop()
        else:
            break

    if not stripped_tail or len(work) < 2:
        return url_norm

    # Si en el prefijo restante ya existe una palabra de accesorio o 'para', es un accesorio independiente
    if any(w in NON_INK_ACCESSORY_KEYWORDS or w == "para" for w in work):
        return url_norm

    # Si solo se quitó un sustantivo típico de accesorio suelto (ej. '...-case' o '...-funda')
    # sin que el prefijo tenga capacidad (GB/TB), MPN alfanumérico, conector de regalo o color,
    # asumir que es accesorio y NO recortar.
    if len(stripped_tail) == 1 and stripped_tail[0] in _URL_BUNDLE_STANDALONE_ACC_NOUNS:
        has_device_spec_or_mpn = any(
            bool(re.match(r"^\d+(?:gb|tb)$", w))
            or bool(re.match(r"^[a-z]{2,}\d+[a-z0-9]*$", w) and len(w) >= 5)
            or w in COLOR_NEUTRAL_TOKENS
            for w in work
        )
        if not has_device_spec_or_mpn:
            return url_norm

    if trailing_sku:
        work.append(trailing_sku)
    return " ".join(work).strip()


def evaluate_strict_guardrails(
    canonical_title: str,
    scraped_title: str,
    scraped_url: str = "",
    cand_specs: Optional[Dict[str, Any]] = None,
    cand_description: str = "",
    target_specs: Optional[Dict[str, Any]] = None,
    exact_code_matched: bool = False,
) -> bool:
    """
    Evalúa los guardrails estrictos genéricos de identidad entre el producto canónico
    y un candidato:
    - Accesorios / tintas / reacondicionados -> False
    - Modificadores de modelo (Pro, Plus, Ultra, Air, FE, Lite, Max, Essential, Mini, Fold, Flip) -> bidireccional
    - Capacidad de almacenamiento (256gb vs 512gb, 1tb == 1024gb) y RAM explícita conflictiva -> False
    - Pulgadas de pantalla exactas en TVs (55" vs 65") y grupos comerciales en tablets/laptops (11" vs 12.7") -> False
    - Arquitectura/tier de CPU y GPU -> False si difieren
    - Conectividad: tablet Wi-Fi rechaza Cellular/5G/LTE; smartphone 5G rechaza 4G/LTE explícito
    """
    if not canonical_title:
        return False

    specs_dict = cand_specs if isinstance(cand_specs, dict) else {}
    t_specs_dict = target_specs if isinstance(target_specs, dict) else {}

    canon_clean = _strip_bundles_and_colors(canonical_title)
    canon_norm = normalize_tech_text(canon_clean, expand_abbrevs=True, strip_colors=True)

    cand_title_clean = _strip_bundles_and_colors(scraped_title)
    cand_title_norm = normalize_tech_text(cand_title_clean, expand_abbrevs=True, strip_colors=True)

    parsed_u = urlparse(scraped_url or "")
    raw_url_path = f"{parsed_u.path} {parsed_u.query}".strip() if parsed_u.path or parsed_u.query else (scraped_url or "")
    cand_url_clean = re.sub(r"\.(html?|php|aspx?)\b", " ", raw_url_path, flags=re.IGNORECASE)
    cand_url_norm = normalize_tech_text(cand_url_clean, expand_abbrevs=True, strip_colors=False)
    cand_url_norm = strip_url_bundle_tail(cand_url_norm)

    specs_norm = normalize_tech_text(
        " ".join(f"{k} {v}" for k, v in specs_dict.items()),
        expand_abbrevs=True,
        strip_colors=False,
    )
    desc_norm = normalize_tech_text(cand_description, expand_abbrevs=True, strip_colors=True)
    full_cand_norm = f"{cand_title_norm} {cand_url_norm} {specs_norm} {desc_norm}".strip()

    # 1. Bloqueo de accesorios, tintas y reacondicionados
    if _has_forbidden_accessory_or_ink(canon_norm, cand_title_norm, cand_url_norm):
        return False

    # 2. Modificadores estrictos de gama/modelo (bidireccional)
    mod_cand_zone = f"{cand_title_norm} {cand_url_norm}".strip()
    for mod in STRICT_MODEL_MODIFIERS:
        in_canon = _word_in_text(mod, canon_norm)
        in_cand_title = _word_in_text(mod, cand_title_norm)
        in_cand_url = _word_in_text(mod, cand_url_norm)
        in_cand_zone = in_cand_title or in_cand_url
        if in_canon and not in_cand_zone:
            if (
                mod == "plus"
                and not cand_title_norm
                and _word_in_text("pro", canon_norm)
                and _word_in_text("pro", cand_url_norm)
            ):
                continue
            return False
        if not in_canon:
            # Si el título existe y declara otro modificador (ej. iPad Air 11 vs iPad 11, S26 Ultra vs S26, Tab A11+ vs Tab A11)
            # o si la URL lo declara y corresponde a sub-modelo intruso -> rechazar
            if in_cand_title or in_cand_url:
                return False

    # 3. Almacenamiento y RAM
    target_storage_text = f"{canon_norm} {normalize_tech_text(json.dumps(t_specs_dict, ensure_ascii=False))}"
    req_storages = extract_storage_tokens(canon_norm) or extract_storage_tokens(target_storage_text)
    if req_storages:
        title_stors = extract_storage_tokens(cand_title_norm)
        url_stors = extract_storage_tokens(cand_url_norm)
        spec_stors_raw = " ".join(
            str(v)
            for k, v in specs_dict.items()
            if any(sk in str(k).lower() for sk in ("almacenamiento", "memoria interna", "disco", "ssd", "rom", "capacidad"))
            and "ram" not in str(k).lower()
            and "bater" not in str(k).lower()
        )
        spec_stors = extract_storage_tokens(normalize_tech_text(spec_stors_raw))
        all_stors = extract_storage_tokens(full_cand_norm)

        if title_stors and not (title_stors & req_storages):
            return False
        if url_stors and not (url_stors & req_storages):
            return False
        if spec_stors and not (spec_stors & req_storages):
            return False
        # Requerir que la capacidad aparezca en el corpus si el candidato tiene contenido sustantivo
        if not (all_stors & req_storages):
            if cand_title_norm or specs_norm or desc_norm or url_stors:
                if not exact_code_matched:
                    return False

    # RAM (solo si el candidato declara otra RAM explícita en título o URL o campo Memoria RAM)
    req_rams = extract_ram_tokens(_strip_gpu_vram_tokens(canon_norm))
    if req_rams:
        title_rams = extract_ram_tokens(_strip_gpu_vram_tokens(cand_title_norm))
        url_rams = extract_ram_tokens(_strip_gpu_vram_tokens(cand_url_norm))
        if title_rams and not (title_rams & req_rams):
            return False
        if url_rams and not (url_rams & req_rams):
            return False

    # 4. Pulgadas de pantalla
    canon_inches = extract_screen_inches_from_text(canonical_title)
    is_tv = any(
        _word_in_text(w, canon_norm)
        for w in ("tv", "televisor", "smart tv", "oled", "qled", "qned", "nanocell", "uhd")
    )
    if is_tv and canon_inches is None:
        for sz in TV_STANDARD_INCHES:
            if _word_in_text(str(sz), canon_norm):
                canon_inches = float(sz)
                break

    if canon_inches is not None:
        if is_tv:
            req_tv_sz = str(int(round(canon_inches)))
            for other_sz in TV_STANDARD_INCHES - {int(round(canon_inches))}:
                if _word_in_text(str(other_sz), cand_title_norm) or _word_in_text(str(other_sz), cand_url_norm):
                    return False
            if not (_word_in_text(req_tv_sz, full_cand_norm) or exact_code_matched):
                return False
        else:
            allowed_grp = _get_tablet_laptop_screen_group(canon_inches)
            conflicting = ALL_TABLET_LAPTOP_SCREEN_SIZES - allowed_grp
            cand_screen_explicit = extract_screen_inches_from_text(scraped_title)
            if cand_screen_explicit is not None:
                cand_sz_s = f"{cand_screen_explicit:.1f}".rstrip("0").rstrip(".")
                if cand_sz_s not in allowed_grp and str(int(round(cand_screen_explicit))) not in allowed_grp:
                    return False

            screen_specs_txt = normalize_tech_text(
                " ".join(
                    str(v)
                    for k, v in specs_dict.items()
                    if any(sk in str(k).lower() for sk in ("pantalla", "tamano", "tamaño", "diagonal", "pulgadas"))
                )
            )
            for bad_sz in conflicting:
                if "." in bad_sz and (_word_in_text(bad_sz, cand_title_norm) or _word_in_text(bad_sz, screen_specs_txt)):
                    return False
                if _word_in_text(bad_sz, screen_specs_txt):
                    return False

    # 5. Arquitectura/tier de CPU y GPU
    target_hw = extract_cpu_and_gpu_signatures(canon_norm)
    cand_hw_primary = extract_cpu_and_gpu_signatures(f"{cand_title_norm} {cand_url_norm}")
    cand_hw_full = extract_cpu_and_gpu_signatures(full_cand_norm)

    if target_hw["cpu_vendor"]:
        cand_vendor = cand_hw_primary["cpu_vendor"] or cand_hw_full["cpu_vendor"]
        if cand_vendor and cand_vendor != target_hw["cpu_vendor"]:
            return False

    if target_hw["cpu_tier"]:
        cand_tier = cand_hw_primary["cpu_tier"] or cand_hw_full["cpu_tier"]
        if cand_tier and cand_tier != target_hw["cpu_tier"]:
            return False

    if target_hw["gpu_model"] and cand_hw_full["gpu_model"]:
        if cand_hw_full["gpu_model"] != target_hw["gpu_model"]:
            return False

    # 6. Conectividad (Wi-Fi tablet vs Cellular/5G; Smartphone 5G rechaza 4G explícito)
    is_tablet_or_ipad = any(
        _word_in_text(w, canon_norm) for w in ("ipad", "tablet", "tableta", "tab")
    )
    if is_tablet_or_ipad:
        target_is_cellular = any(
            _word_in_text(w, canon_norm) for w in ("cellular", "lte", "5g", "4g")
        )
        if not target_is_cellular:
            if any(_word_in_text(w, f"{cand_title_norm} {cand_url_norm}") for w in ("cellular", "lte", "5g", "4g")):
                return False
    else:
        if _word_in_text("5g", canon_norm):
            cand_primary_net = f"{cand_title_norm} {cand_url_norm}"
            has_4g_or_lte = _word_in_text("4g", cand_primary_net) or _word_in_text("lte", cand_primary_net)
            has_5g = _word_in_text("5g", cand_primary_net) or _word_in_text("5g", specs_norm)
            if has_4g_or_lte and not has_5g:
                return False

    # 7. Guardrails multi-categoría (consolas, monitores, smartwatches, packs)
    cand_check_src = cand_title_clean if scraped_title else ""
    if not _check_extended_category_guardrails(
        canonical_title=canonical_title,
        cand_title=cand_check_src,
        cand_url=scraped_url or "",
    ):
        return False

    return True


# ==============================================================================
# 4. EXTRACTOR GENÉRICO DE EAN / GTIN / MPN
# ==============================================================================

def _normalize_gtin(raw_val: Any) -> Optional[str]:
    if raw_val is None or isinstance(raw_val, bool):
        return None
    digits = re.sub(r"\D", "", str(raw_val))
    if len(digits) not in {8, 12, 13, 14}:
        return None
    if len(set(digits)) <= 1:
        return None
    return digits


def _normalize_mpn(raw_val: Any) -> Optional[str]:
    if raw_val is None or isinstance(raw_val, bool):
        return None
    s = str(raw_val).strip()
    if not s or len(s) < 5 or len(s) > 32:
        return None
    low = s.lower()
    # Excluir IDs de marketplace de Ripley/ConectaRetail o URLs/HTML
    if low.startswith("pmp") or "http" in low or " " in s.strip():
        return None
    if re.search(r"ip3\d{10,}", low):
        return None
    compact = re.sub(r"[^a-z0-9]", "", low)
    if len(compact) < 5 or len(compact) > 24:
        return None
    # Un MPN válido debe combinar letras y dígitos (evitar SKUs numéricos internos de tienda y palabras sueltas)
    if not (re.search(r"[a-z]", compact) and re.search(r"\d", compact)):
        return None
    if compact in NON_MPN_TECH_WORDS:
        return None
    if re.match(r"^(?:rtx|gtx)\d{3,4}[a-z0-9]*$", compact):
        return None
    if re.match(r"^(?:19|20)\d{2}[a-z]*$", compact):
        return None
    # Evitar tokens puramente descriptivos como 128gb, 60hz, 5000mah, 108mp
    if re.match(r"^\d+(?:gb|tb|mb|mah|mp|hz|w|cm|mm|kg|pulg)$", compact):
        return None
    return compact


_INLINE_MPN_PATTERNS: Tuple[str, ...] = (
    r"\bmodelo\s*[:#]?\s*([a-z0-9]{2,8}(?:-[a-z0-9]{2,8}){1,3}|8[0-9][a-z0-9]{8})\b",
    r"\b([a-z]{1,3}\d{3,4}[a-z]{1,3}-[a-z]{2}\d{3,4}[a-z]?)\b",
    r"\b((?:al|an|sf|phn?)\d{2,3}-\d{2}[a-z]?-[a-z0-9]{4})\b",
    r"\b((?:\d{2}[a-z]{3}\d{2}-)?8[0-9][a-z0-9]{6}(?:lm|pe|us|sp))\b",
    r"\b(zaf\d{5}[a-z]{2})\b",
    r"\b(1[34567]-[a-z]{2}\d{4}la)\b",
    r"\b((?:lbu|lab|alt|rea|brp|any|crt|rmo|mgk|bvl)-lx\d)\b",
    r"\b(sm-[a-z]\d{3}[a-z0-9]{2,8})\b",
    r"\b(tb\d{3}[a-z]{2})\b",
)

_URL_TRAILING_GIFT_OR_SKU_RE = re.compile(
    r"(?:-(?:mochila|mouse|funda|maletin|backpack|intel|amd|cover|keyboard|\d{6,}p?))+/?$",
    flags=re.IGNORECASE,
)


def extract_inline_manufacturer_mpns(title: str, url: str = "") -> List[str]:
    """
    Extrae códigos de fabricante/SKU largos presentes en título o URL (ej. 'X1504MA-BQ523W',
    '82XQ00LTLM', '15-FB3021LA', 'AL15-46P-R4UJ') normalizados para `mpn` sin colas de regalo.
    """
    found: List[str] = []
    for raw_src in (title or "", url or ""):
        if not raw_src:
            continue
        clean_src = re.sub(r"\.(html?|php|aspx?)\b", " ", str(raw_src), flags=re.IGNORECASE)
        if "://" in clean_src or clean_src.startswith("/"):
            clean_src = _URL_TRAILING_GIFT_OR_SKU_RE.sub("", clean_src)
        for pat in _INLINE_MPN_PATTERNS:
            for match in re.findall(pat, clean_src, flags=re.IGNORECASE):
                cand = match if isinstance(match, str) else match[0]
                cand = _URL_TRAILING_GIFT_OR_SKU_RE.sub("", cand)
                norm = _normalize_mpn(cand)
                if norm and norm not in found:
                    found.append(norm)
    return found


def _walk_json_for_codes(node: Any, gtin_out: List[str], mpn_out: List[str], depth: int = 0) -> None:
    if depth > 7:
        return
    if isinstance(node, list):
        for item in node:
            _walk_json_for_codes(item, gtin_out, mpn_out, depth + 1)
        return
    if not isinstance(node, dict):
        return

    gtin_keys = ("gtin13", "gtin14", "gtin12", "gtin8", "gtin", "ean", "ean13", "barcode", "codigobarras")
    mpn_keys = (
        "mpn",
        "manufacturerpartnumber",
        "partnumber",
        "productreference",
        "productreferencecode",
        "manufacturercode",
        "codigofabricante",
        "model",
        "modelo",
    )

    is_ld_product = str(node.get("@type") or "").lower() == "product"
    for k, v in node.items():
        k_low = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_low in gtin_keys:
            if isinstance(v, list):
                for sub_v in v:
                    g = _normalize_gtin(sub_v)
                    if g and g not in gtin_out:
                        gtin_out.append(g)
            else:
                g = _normalize_gtin(v)
                if g and g not in gtin_out:
                    gtin_out.append(g)
        elif k_low in mpn_keys or (is_ld_product and k_low == "sku"):
            if isinstance(v, str):
                m = _normalize_mpn(v)
                if m and m not in mpn_out:
                    mpn_out.append(m)
        elif isinstance(v, (dict, list)):
            _walk_json_for_codes(v, gtin_out, mpn_out, depth + 1)

    # VTEX referenceId: [{"Key": "RefId", "Value": "..."}]
    if str(node.get("Key") or node.get("key") or node.get("name") or "").strip().lower() in {
        "refid", "ean", "gtin", "mpn", "modelo", "model", "partnumber", "numero de parte", "número de parte", "codigo de barras", "código de barras"
    }:
        val = node.get("Value") or node.get("value")
        k_name = str(node.get("Key") or node.get("key") or node.get("name") or "").strip().lower()
        if any(gk in k_name for gk in ("ean", "gtin", "barras")):
            g = _normalize_gtin(val)
            if g and g not in gtin_out:
                gtin_out.append(g)
        else:
            m = _normalize_mpn(val)
            if m and m not in mpn_out:
                mpn_out.append(m)


def extract_product_codes(
    html_or_json: str = "",
    tech_specs: Optional[Dict[str, Any]] = None,
    title: str = "",
    url: str = "",
) -> Dict[str, List[str]]:
    """
    Extrae códigos oficiales normalizados de fabricante:
    - 'gtin': lista de códigos EAN/GTIN numéricos válidos (8, 12, 13 o 14 dígitos).
    - 'mpn': lista de códigos de fabricante normalizados alfanuméricos (ej. 'md3y4cla', 'ux3407qaqd289w').
    Inspecciona JSON-LD, __NEXT_DATA__, __PRELOADED_STATE__, meta tags HTML, tech_specs y URL/título.
    """
    gtins: List[str] = []
    mpns: List[str] = []

    def _add_gtin(val: Any) -> None:
        g = _normalize_gtin(val)
        if g and g not in gtins:
            gtins.append(g)

    def _add_mpn(val: Any) -> None:
        m = _normalize_mpn(val)
        if m and m not in mpns:
            mpns.append(m)

    # 1. Desde tech_specs proporcionados
    if isinstance(tech_specs, dict):
        for k, v in tech_specs.items():
            k_low = strip_accents_lower(str(k))
            if any(gk in k_low for gk in ("ean", "gtin", "codigo de barras", "barcode")):
                _add_gtin(v)
            elif any(mk in k_low for mk in ("mpn", "part number", "numero de parte", "codigo fabricante", "modelo", "model", "referencia")):
                for token in re.split(r"[,;\s]+", str(v or "")):
                    _add_mpn(token)

    # 2. Desde HTML o JSON crudo
    raw = (html_or_json or "").strip()
    if raw:
        if raw.startswith(("{", "[")):
            try:
                _walk_json_for_codes(json.loads(raw), gtins, mpns)
            except Exception:
                pass
        else:
            soup = BeautifulSoup(raw, "lxml")

            # JSON-LD
            for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
                if not sc.string:
                    continue
                try:
                    _walk_json_for_codes(json.loads(sc.string), gtins, mpns)
                except Exception:
                    pass

            # __NEXT_DATA__
            nd = soup.find("script", id="__NEXT_DATA__")
            if nd and nd.string:
                try:
                    _walk_json_for_codes(json.loads(nd.string), gtins, mpns)
                except Exception:
                    pass

            # window.__PRELOADED_STATE__
            preloaded_m = re.search(
                r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*(?:;|</script>)",
                raw,
                flags=re.DOTALL,
            )
            if preloaded_m:
                try:
                    _walk_json_for_codes(json.loads(preloaded_m.group(1)), gtins, mpns)
                except Exception:
                    pass

            # Meta tags y atributos itemprop
            for meta in soup.find_all("meta"):
                key_attr = strip_accents_lower(
                    str(meta.get("property") or meta.get("name") or meta.get("itemprop") or "")
                )
                content = meta.get("content")
                if not content:
                    continue
                if any(gk in key_attr for gk in ("ean", "gtin")):
                    _add_gtin(content)
                elif any(mk in key_attr for mk in ("mpn", "sku", "model", "partnumber")):
                    _add_mpn(content)

            for el in soup.select("[itemprop='gtin13'], [itemprop='gtin14'], [itemprop='gtin12'], [itemprop='gtin8'], [itemprop='gtin'], [itemprop='mpn'], [itemprop='sku']"):
                prop = str(el.get("itemprop") or "").lower()
                val = el.get("content") or el.get_text(" ", strip=True)
                if "gtin" in prop:
                    _add_gtin(val)
                else:
                    _add_mpn(val)

    # 3. Patrones inequívocos de MPN de fabricante en título o URL
    #    (ej. Samsung 'SM-S938B...', Apple 'MD3Y4CL/A' / 'md3y4cl-a', Asus/Lenovo 'UX3407QA-QD289W', 'FX607VU-RL030W',
    #     TV part codes 'OLED55B6PSA', '55QN85D')
    for m_in in extract_inline_manufacturer_mpns(title=title, url=url):
        if m_in not in mpns:
            mpns.append(m_in)

    high_conf_mpn_patterns = (
        r"\b(SM-[A-Z0-9]{5,14})\b",
        r"\b([A-Z]{2,3}\d[A-Z0-9]{3,5}[/-][A-Z]{1,2})\b",
        r"\b([A-Z]{2,4}\d{3,5}[A-Z]{0,4}-[A-Z0-9]{4,8})\b",
        r"\b((?:OLED|QNED|NANO)\d{2}[A-Z0-9]{3,10})\b",
    )
    for text_src in (title or "", url or ""):
        if not text_src:
            continue
        clean_src = re.sub(r"\.(html?|php|aspx?)\b", " ", str(text_src), flags=re.IGNORECASE)
        if "://" in clean_src or clean_src.startswith("/"):
            clean_src = _URL_TRAILING_GIFT_OR_SKU_RE.sub("", clean_src)
        for pat in high_conf_mpn_patterns:
            for match in re.findall(pat, clean_src, flags=re.IGNORECASE):
                cand = match if isinstance(match, str) else match[0]
                cand = _URL_TRAILING_GIFT_OR_SKU_RE.sub("", cand)
                if not re.match(r"^ip3\d+$", cand, flags=re.IGNORECASE):
                    _add_mpn(cand)

    return {"gtin": gtins, "mpn": mpns}


def has_exact_code_match(
    target_codes: Optional[Dict[str, Sequence[str]]],
    candidate_codes: Optional[Dict[str, Sequence[str]]],
) -> bool:
    """Retorna True si objetivo y candidato comparten al menos un GTIN/EAN o MPN exacto."""
    if not target_codes or not candidate_codes:
        return False

    t_gtin = {str(x).strip() for x in (target_codes.get("gtin") or []) if x}
    c_gtin = {str(x).strip() for x in (candidate_codes.get("gtin") or []) if x}
    if t_gtin & c_gtin:
        return True

    t_mpn = {str(x).strip().lower() for x in (target_codes.get("mpn") or []) if x}
    c_mpn = {str(x).strip().lower() for x in (candidate_codes.get("mpn") or []) if x}
    if t_mpn & c_mpn:
        return True

    return False


# ==============================================================================
# 5. VALIDACIÓN SOLO-CONTRADICCIÓN PARA URLs PERSISTIDAS EN BD (TÍTULO VACÍO)
# ==============================================================================

_PERSISTED_BRAND_ALIASES: Dict[str, str] = {
    "apple": "apple",
    "iphone": "apple",
    "ipad": "apple",
    "macbook": "apple",
    "app": "apple",
    "samsung": "samsung",
    "galaxy": "samsung",
    "sam": "samsung",
    "xiaomi": "xiaomi",
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "lenovo": "lenovo",
    "ideapad": "lenovo",
    "thinkpad": "lenovo",
    "legion": "lenovo",
    "loq": "lenovo",
    "len": "lenovo",
    "asus": "asus",
    "zenbook": "asus",
    "vivobook": "asus",
    "tuf": "asus",
    "rog": "asus",
    "hp": "hp",
    "victus": "hp",
    "omen": "hp",
    "pavilion": "hp",
    "canon": "canon",
    "pixma": "canon",
    "epson": "epson",
    "ecotank": "epson",
    "lg": "lg",
    "sony": "sony",
    "playstation": "sony",
    "honor": "honor",
    "motorola": "motorola",
    "moto": "motorola",
    "brother": "brother",
    "hisense": "hisense",
    "tcl": "tcl",
    "jbl": "jbl",
    "acer": "acer",
    "dell": "dell",
    "msi": "msi",
    "huawei": "huawei",
    "matepad": "huawei",
    "oster": "oster",
    "belkin": "belkin",
    "ugreen": "ugreen",
    "baseus": "baseus",
    "nillkin": "nillkin",
}

_KNOWN_URL_PRODUCT_ALIASES: Dict[str, Tuple[str, ...]] = {
    "tb336fu": ("lenovo", "idea", "tab", "11"),
    "ux3407qa": ("asus", "zenbook", "a14"),
    "fx607": ("asus", "tuf", "f16", "intel"),
    "82xq": ("lenovo", "ideapad", "slim", "3", "ryzen", "5"),
    "83je": ("lenovo", "loq", "15", "intel", "i7"),
    "fb3049": ("hp", "victus", "15", "ryzen", "7", "rtx", "4050"),
    "sm s721": ("samsung", "galaxy", "s24", "fe"),
    "sm s938": ("samsung", "galaxy", "s25", "ultra"),
    "sm x133": ("samsung", "galaxy", "tab", "a11"),
    "sm a576": ("samsung", "galaxy", "a57"),
    "sm a376": ("samsung", "galaxy", "a37"),
    "md3y4cl": ("apple", "ipad", "11", "a16"),
    "mye73be": ("apple", "iphone", "16"),
}

_NON_TECH_OTHER_CATEGORIES: Set[str] = {
    "vitrina",
    "exhibidora",
    "refrigeradora",
    "congeladora",
    "lavadora",
    "secadora",
    "cocina",
    "microondas",
    "horno",
    "licuadora",
    "freidora",
    "aspiradora",
    "parlante",
    "parlantes",
    "audifono",
    "audifonos",
    "silla",
    "escritorio",
    "maletin",
    "mochila",
    "smartwatch",
    "reloj",
    "hub",
    "router",
}

_FAMILY_NUMBER_NOUNS: Tuple[str, ...] = (
    "iphone",
    "note",
    "pad",
    "slim",
    "tank",
    "victus",
    "loq",
)


def _detect_canon_device_kind(canon_norm: str) -> str:
    if any(_word_in_text(w, canon_norm) for w in ("tablet", "tableta", "ipad", "tab", "pad", "matepad")):
        return "tablet"
    if any(_word_in_text(w, canon_norm) for w in ("impresora", "multifuncional", "ecotank", "pixma", "smart tank")):
        return "printer"
    if any(_word_in_text(w, canon_norm) for w in ("televisor", "tv", "smart tv", "oled", "qled", "qned", "nanocell")):
        return "tv"
    if any(_word_in_text(w, canon_norm) for w in ("laptop", "notebook", "macbook", "ideapad", "zenbook", "vivobook", "victus", "tuf", "loq", "thinkpad")):
        return "laptop"
    if any(_word_in_text(w, canon_norm) for w in ("celular", "smartphone", "iphone", "galaxy", "redmi", "poco", "honor", "moto")):
        return "phone"
    return "other"


def _extract_model_code_shapes(tokens: Sequence[str], is_apple_or_tablet: bool = False) -> Dict[str, List[str]]:
    """
    Agrupa códigos de modelo alfanuméricos tipo 's25', 'a57', 'f16', 'c6', 'b6', 'l3250', 'g3170'
    por (prefijo_letras, longitud_digitos) para detectar contradicciones explícitas entre generaciones.
    """
    grouped: Dict[str, List[str]] = {}
    ignored_prefixes = {"r", "i", "c"}  # r5/r7/i5/i7/c5 pueden corresponder a CPU si aparecen
    for tok in tokens:
        if tok in STANDARD_STORAGE_TOKENS or tok in {"4g", "5g", "4k", "8k", "6e", "5w", "20w", "40w", "60w", "65w", "100w"}:
            continue
        m = re.match(r"^([a-z]{1,4})(\d{1,4})$", tok)
        if not m:
            continue
        prefix, digits = m.group(1), m.group(2)
        if prefix in ignored_prefixes and tok not in {"c6", "c5", "c4", "c3", "r1", "i1"}:
            continue
        if is_apple_or_tablet and prefix in {"a", "m"} and len(digits) <= 2:
            # Chips de Apple (a16, m3, m5) se evalúan aparte en CPU/GPU, no como prefijo genérico con dígitos sueltos
            continue
        shape_key = f"{prefix}:{len(digits)}"
        grouped.setdefault(shape_key, []).append(tok)
    return grouped


def validate_persisted_url_no_contradiction(
    canonical_title: str,
    scraped_url: str,
    store_id: str = "unknown",
    target_specs: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Valida una oferta persistida en BD cuando no se dispone de título scrapeado (`received_title == ""`),
    comprobando EXCLUSIVAMENTE que el slug de la URL no contradiga de forma directa el producto
    (marca, categoría, serie/modelo, modificador no solicitado, capacidad RAM/storage/pulgadas, CPU/GPU o accesorio).
    Nunca descarta una URL corta válida solo porque omita tokens como `ryzen`, `snapdragon`, `ultra` o `wi-fi`.
    """
    from app.collectors.url_utils import is_marketplace_url

    if not canonical_title or not scraped_url:
        return False

    if is_marketplace_url(store_id, scraped_url):
        return False

    specs_dict = target_specs if isinstance(target_specs, dict) else {}
    canon_clean = _strip_bundles_and_colors(canonical_title)
    canon_norm = normalize_tech_text(canon_clean, expand_abbrevs=True, strip_colors=True)

    parsed_u = urlparse(scraped_url or "")
    raw_url_path = f"{parsed_u.path} {parsed_u.query}".strip() if (parsed_u.path or parsed_u.query) else (scraped_url or "")
    if not raw_url_path or raw_url_path == "/":
        return False

    cand_url_clean = re.sub(r"\.(html?|php|aspx?)\b", " ", raw_url_path, flags=re.IGNORECASE)
    url_norm_raw = normalize_tech_text(cand_url_clean, expand_abbrevs=True, strip_colors=False)
    clean_url_norm = strip_url_bundle_tail(url_norm_raw)
    if not clean_url_norm:
        return False

    # Enriquecer vista de tokens del slug con prefijos MPN oficiales conocidos presentes en URL
    augmented_tokens: List[str] = list(clean_url_norm.split())
    for alias_key, expanded_words in _KNOWN_URL_PRODUCT_ALIASES.items():
        if alias_key in clean_url_norm:
            for w in expanded_words:
                if w not in augmented_tokens:
                    augmented_tokens.append(w)
    augmented_url_norm = " ".join(augmented_tokens)

    # 1. Bloqueo de accesorios, botellas/cartuchos de tinta y reacondicionados
    if _has_forbidden_accessory_or_ink(canon_norm, "", clean_url_norm):
        return False

    # 2. Contradicción explícita de categoría (ej. vitrina/parlante/refrigeradora o tablet vs celular)
    canon_kind = _detect_canon_device_kind(canon_norm)
    if canon_kind in {"phone", "tablet", "laptop", "tv", "printer"}:
        if any(_word_in_text(non_tech, clean_url_norm) for non_tech in _NON_TECH_OTHER_CATEGORIES):
            return False
        url_has_tablet = any(_word_in_text(w, augmented_url_norm) for w in ("tablet", "tableta", "ipad", "tab", "matepad"))
        url_has_laptop = any(_word_in_text(w, augmented_url_norm) for w in ("laptop", "notebook", "macbook", "ideapad", "zenbook", "vivobook", "victus", "loq"))
        url_has_tv = any(_word_in_text(w, augmented_url_norm) for w in ("televisor", "oled", "qled", "qned", "nanocell", "smart tv"))
        url_has_printer = any(_word_in_text(w, augmented_url_norm) for w in ("impresora", "multifuncional", "ecotank", "pixma", "smart tank"))
        url_has_phone = any(_word_in_text(w, augmented_url_norm) for w in ("celular", "smartphone", "iphone"))

        if canon_kind == "phone" and (url_has_tablet or url_has_laptop or url_has_tv or url_has_printer):
            return False
        if canon_kind == "tablet" and (url_has_phone or url_has_laptop or url_has_tv or url_has_printer):
            return False
        if canon_kind == "laptop" and (url_has_phone or url_has_tablet or url_has_tv or url_has_printer):
            return False
        if canon_kind == "tv" and (url_has_phone or url_has_tablet or url_has_laptop or url_has_printer):
            return False
        if canon_kind == "printer" and (url_has_phone or url_has_tablet or url_has_laptop or url_has_tv):
            return False

    # 3. Contradicción explícita de marca
    canon_brands: Set[str] = set()
    for w in canon_norm.split():
        if w in _PERSISTED_BRAND_ALIASES:
            canon_brands.add(_PERSISTED_BRAND_ALIASES[w])
    spec_brand = strip_accents_lower(str(specs_dict.get("Marca") or "")).strip()
    if spec_brand in _PERSISTED_BRAND_ALIASES:
        canon_brands.add(_PERSISTED_BRAND_ALIASES[spec_brand])

    url_brands: Set[str] = set()
    for w in augmented_url_norm.split():
        if w in _PERSISTED_BRAND_ALIASES:
            url_brands.add(_PERSISTED_BRAND_ALIASES[w])

    if canon_brands and url_brands and not (canon_brands & url_brands):
        return False

    # 4. Contradicción explícita de modificador de gama NO pedido (solo unidireccional hacia intrusos)
    for mod in STRICT_MODEL_MODIFIERS:
        if not _word_in_text(mod, canon_norm) and _word_in_text(mod, clean_url_norm):
            return False

    # 5. Contradicción explícita de almacenamiento o RAM (solo cuando el slug sí declara capacidad)
    target_stor_src = f"{canon_norm} {normalize_tech_text(json.dumps(specs_dict, ensure_ascii=False))}"
    req_storages = extract_storage_tokens(canon_norm) or extract_storage_tokens(target_stor_src)
    url_storages = extract_storage_tokens(clean_url_norm)
    if req_storages and url_storages and not (req_storages & url_storages):
        return False

    req_rams = extract_ram_tokens(canon_norm)
    url_rams = extract_ram_tokens(clean_url_norm)
    if req_rams and url_rams and not (req_rams & url_rams):
        return False

    # 6. Contradicción explícita de pulgadas en TVs o decimales de pantalla en tablets/laptops
    canon_inches = extract_screen_inches_from_text(canonical_title)
    is_tv = canon_kind == "tv"
    if is_tv and canon_inches is None:
        for sz in TV_STANDARD_INCHES:
            if _word_in_text(str(sz), canon_norm):
                canon_inches = float(sz)
                break
    if canon_inches is not None:
        if is_tv:
            for other_sz in TV_STANDARD_INCHES - {int(round(canon_inches))}:
                if _word_in_text(str(other_sz), augmented_url_norm):
                    return False
        else:
            allowed_grp = _get_tablet_laptop_screen_group(canon_inches)
            for bad_sz in ALL_TABLET_LAPTOP_SCREEN_SIZES - allowed_grp:
                if "." in bad_sz and _word_in_text(bad_sz, clean_url_norm):
                    return False

    # 7. Contradicción explícita de arquitectura / tier de CPU o GPU (solo si la URL la declara)
    target_hw = extract_cpu_and_gpu_signatures(canon_norm)
    url_hw = extract_cpu_and_gpu_signatures(clean_url_norm)
    if target_hw["cpu_vendor"] and url_hw["cpu_vendor"] and target_hw["cpu_vendor"] != url_hw["cpu_vendor"]:
        return False
    if target_hw["cpu_tier"] and url_hw["cpu_tier"] and target_hw["cpu_tier"] != url_hw["cpu_tier"]:
        return False
    if target_hw["gpu_model"] and url_hw["gpu_model"] and target_hw["gpu_model"] != url_hw["gpu_model"]:
        return False

    # 8. Contradicción explícita de serie/generación o código de modelo
    canon_words = canon_norm.split()
    url_words = augmented_url_norm.split()
    canon_shapes = _extract_model_code_shapes(canon_words, is_apple_or_tablet=(canon_kind == "tablet" or "apple" in canon_brands))
    url_shapes = _extract_model_code_shapes(url_words, is_apple_or_tablet=(canon_kind == "tablet" or "apple" in canon_brands))
    for shape_key, c_toks in canon_shapes.items():
        u_toks = url_shapes.get(shape_key)
        if u_toks:
            # Permitir coincidencia de prefijo (ej. s25 en s25ul)
            has_match = any(
                c == u or u.startswith(c) or c.startswith(u)
                for c in c_toks
                for u in u_toks
            )
            if not has_match:
                return False

    # Series OLED/QLED LG tipo C6 vs B6/G6
    if is_tv:
        canon_oled_series = {t for t in canon_words if re.match(r"^[bcgmrwz]\d$", t)}
        url_oled_series = {t for t in url_words if re.match(r"^[bcgmrwz]\d$", t)}
        if canon_oled_series and url_oled_series and not (canon_oled_series & url_oled_series):
            return False

    # Conflicto familia + número directo (ej. iphone 15 vs iphone 16, slim 3 vs slim 5, smart tank 515 vs 580)
    for fam in _FAMILY_NUMBER_NOUNS:
        if not (_word_in_text(fam, canon_norm) and _word_in_text(fam, augmented_url_norm)):
            continue
        c_nums = set(re.findall(rf"\b{fam}\s+(\d{{1,3}})\b", canon_norm))
        u_nums = set(re.findall(rf"\b{fam}\s+(\d{{1,3}})\b", augmented_url_norm))
        if c_nums and u_nums and not (c_nums & u_nums):
            return False

    # Sub-línea Redmi Note vs Redmi A/C/Pad (ej. redmi-a7pro contra Redmi Note 15 Pro+)
    if _word_in_text("redmi", canon_norm) and _word_in_text("note", canon_norm) and _word_in_text("redmi", augmented_url_norm):
        if not _word_in_text("note", augmented_url_norm):
            return False

    # 9. Ancla positiva mínima o coincidencia exacta MPN/GTIN para rechazar URLs completamente ajenas
    target_codes = extract_product_codes(tech_specs=specs_dict, title=canonical_title)
    url_codes = extract_product_codes(title="", url=scraped_url)
    if has_exact_code_match(target_codes, url_codes):
        return True

    canon_anchors = {
        tok
        for tok in strip_neutral_tokens(canon_norm).split()
        if (len(tok) >= 3 or re.search(r"\d", tok)) and tok not in STANDARD_STORAGE_TOKENS
    }
    url_anchor_tokens = {
        tok
        for tok in augmented_url_norm.split()
        if (len(tok) >= 3 or re.search(r"\d", tok))
    }
    # Permitir coincidencia exacta o prefijo de MPN/modelo (ej. s25 <-> s25ul, u8000h <-> u8000)
    has_positive_anchor = bool(canon_anchors & url_anchor_tokens) or any(
        (len(ca) >= 3 and len(ua) >= 3 and (ua.startswith(ca) or ca.startswith(ua)))
        for ca in canon_anchors
        for ua in url_anchor_tokens
        if re.search(r"\d", ca) and re.search(r"\d", ua)
    )
    return has_positive_anchor


# ==============================================================================
# 6. NORMALIZACIÓN Y GUARDRAILS MULTI-CATEGORÍA (14 CATEGORÍAS TECH — FASE 2B)
# ==============================================================================

_MONITOR_INCH_GROUP_MAP: Dict[str, str] = {
    "21.5": "22",
    "22": "22",
    "22.0": "22",
    "23.8": "24",
    "24": "24",
    "24.0": "24",
    "31.5": "32",
    "32": "32",
    "32.0": "32",
}

_CONSOLE_BUNDLE_GAMES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("mario_kart", ("mario kart", "mariokart")),
    ("ea_fc", ("ea sports fc", "fc 25", "fc 26", "fc 27", "fifa")),
    ("spider_man", ("spider man", "spiderman", "spider-man")),
    ("call_of_duty", ("call of duty", "black ops", "modern warfare")),
    ("god_of_war", ("god of war", "ragnarok")),
    ("astro_bot", ("astro bot", "astrobot")),
    ("horizon", ("horizon zero", "horizon forbidden")),
    ("gran_turismo", ("gran turismo", "gt7")),
    ("fortnite", ("fortnite",)),
    ("minecraft", ("minecraft",)),
    ("zelda", ("zelda",)),
    ("pokemon", ("pokemon",)),
    ("splatoon", ("splatoon",)),
    ("smash", ("super smash", "smash bros")),
    ("nba_2k", ("nba 2k",)),
    ("extra_controller", ("2 controles", "2 mandos", "mando adicional", "control adicional")),
)

_SIGNATURE_COLOR_TRAILING_SUFFIX_RE = re.compile(r"\b([a-z0-9]*\d[a-z0-9]{2,})[-/](b|w|s|k)\b", re.IGNORECASE)

_GLOBAL_SIGNATURE_FILLER_TOKENS: Set[str] = COLOR_NEUTRAL_TOKENS | {
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
    "pulgadas",
    "pulgada",
    "pulg",
    "inch",
    "inches",
    "pantalla",
    "libre",
    "liberado",
    "liberada",
    "desbloqueado",
    "desbloqueada",
    "dual",
    "sim",
    "esim",
    "ram",
    "rom",
    "memoria",
    "interna",
    "unificada",
    "almacenamiento",
    "estado",
    "solido",
    "solide",
    "disco",
    "duro",
    "unidad",
    "orig",
    "original",
    "garantia",
    "sellado",
    "sellada",
    "peru",
    "modelo",
    "version",
    "edicion",
    "color",
    "ia",
    "ai",
    "copilot",
    "windows",
    "w11",
    "win11",
    "freedos",
    "espanol",
    "cla",
    "bes",
    "lep",
    "ltp",
}

_CATEGORY_SIGNATURE_FILLER_TOKENS: Dict[str, Set[str]] = {
    "celulares": {
        "celular", "celulares", "smartphone", "smartphones", "movil", "telefono",
        "5g", "4g", "lte", "chip", "procesador", "amoled", "oled", "ips", "fhd", "hd",
        "ram", "rom", "ssd", "bundle",
    },
    "laptops": {
        "laptop", "laptops", "notebook", "notebooks", "portatil", "gamer", "gaming",
        "wuxga", "fhd", "hd", "ips", "ssd", "ram", "disco", "procesador",
        "home", "single", "language", "pc", "teclado", "nvidia", "geforce",
        "qualcomm", "lpddr5", "lpddr4x", "ddr4", "ddr5", "by", "games", "lenvo",
    },
    "tablets": {
        "tablet", "tablets", "tableta", "wifi", "wi", "fi", "wlan", "wuxga", "fhd",
        "hd", "ips", "ufs", "emmc", "octa", "core", "mediatek", "helio", "qualcomm",
    },
    "televisores": {
        "tv", "televisor", "televisores", "smart", "ai", "thinq", "dolby", "atmos",
        "vision", "hdr", "hdr10", "uhd", "nanocell", "4k", "fhd", "hd",
        "crystal", "google", "android", "tizen", "webos", "vidaa",
    },
    "impresoras": {
        "impresora", "impresoras", "multifuncional", "tintas", "tinta", "continua",
        "sistema", "continuo", "todo", "uno", "app", "impresion", "copia",
        "escanea", "escaner", "multifuncion", "wifi", "wi", "fi", "usb", "tanque",
    },
    "consolas": {"consola", "consolas", "videojuego", "videojuegos", "lectora", "lector", "estandar", "standard", "disc", "disco", "solus", "chassis"},
    "monitores": {"monitor", "monitores", "gamer", "gaming", "pantalla", "display", "frameless", "antireflejo"},
    "audifonos": {"audifono", "audifonos", "auricular", "auriculares", "headset", "headsets", "headphone", "headphones", "inalambrico", "inalambricos", "inalambrica", "bluetooth", "bt", "wireless", "true", "earbuds", "gamer", "gaming", "microfono", "micro", "usbc", "usb", "estuche", "carga", "on", "ear", "diadema", "vincha"},
    "smartwatches": {"smartwatch", "smartwatches", "reloj", "relojes", "inteligente", "wearable", "bluetooth", "bt", "gps", "correa", "deportivo", "sport"},
    "audio": {"parlante", "parlantes", "speaker", "speakers", "altavoz", "altavoces", "bocina", "inalambrico", "inalambricos", "bluetooth", "bt", "portatil", "portable", "equipo", "sonido", "sistema", "wireless"},
    "camaras": {"camara", "camaras", "fotografica", "digital", "mirrorless", "reflex", "instantanea", "kit", "lente"},
    "almacenamiento_redes": {"almacenamiento", "externo", "externa", "disco", "unidad", "memoria", "tarjeta", "router", "rompemuros", "dual", "band", "tri", "alta", "velocidad"},
    "accesorios_pc": {"accesorio", "accesorios", "periferico", "perifericos", "inalambrico", "inalambricos", "wireless", "bluetooth", "bt", "combo", "kit", "set", "gamer", "gaming"},
    "smart_home": {"smart", "home", "domotica", "inteligente", "asistente", "voz", "wifi", "wi", "fi", "control", "remoto"},
}

_SPEC_BUCKET_EXACT_TOKENS: Set[str] = {
    "fhd", "qhd", "wqhd", "uwqhd", "4k", "8k", "hd",
    "ips", "va", "tn", "oled", "miniled", "amoled",
    "wifi5", "wifi6", "wifi6e", "wifi7", "mesh", "cellular", "lte",
    "nvme", "sata", "ssd", "hdd",
    "anc", "tws", "overear", "inear",
}


def extract_monitor_inches(raw_text: str, allow_implicit: bool = False) -> Optional[str]:
    """Extrae el tamaño comercial normalizado de monitor ('22', '24', '27', '32', '34', etc.)."""
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)

    explicit_matches = re.findall(
        r"\b(\d{2}(?:\.\d)?)\s*(?:\"|''|”|(?:pulgadas|pulg|inch|inches)\b)",
        low,
    )
    candidates: List[str] = list(explicit_matches)
    if allow_implicit or _word_in_text("monitor", low) or _word_in_text("ultragear", low) or _word_in_text("odyssey", low):
        for m in re.finditer(r"\b(\d{2}(?:\.\d)?)\b(?!\s*(?:hz|gb|tb|mm|w|watts?|ms|fps|bits?|cm|kg|mah|mp|cuotas|meses)\b)", low):
            tok = m.group(1)
            prefix_ctx = low[max(0, m.start() - 16) : m.start()]
            if re.search(r"\b(?:serie|series|gen|windows|win|top|g|x|s|pro|tier)\s*$", prefix_ctx):
                continue
            if tok in MONITOR_STANDARD_INCHES and tok not in candidates:
                candidates.append(tok)

    for raw_sz in candidates:
        clean_sz = raw_sz.rstrip("0").rstrip(".") if "." in raw_sz else raw_sz
        if clean_sz in _MONITOR_INCH_GROUP_MAP:
            return _MONITOR_INCH_GROUP_MAP[clean_sz]
        if clean_sz in MONITOR_STANDARD_INCHES:
            return clean_sz
    return None


def extract_refresh_rate_hz(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)
    m = re.search(
        r"\b(60|75|100|120|144|165|170|175|180|200|240|280|300|360|480|500)\s*hz\b",
        low,
    )
    return f"{m.group(1)}hz" if m else None


def extract_panel_and_resolution(raw_text: str) -> Tuple[Optional[str], Optional[str], Optional[bool]]:
    if not raw_text:
        return (None, None, None)
    low = strip_accents_lower(raw_text)

    panel: Optional[str] = None
    if re.search(r"\b(?:qd\s*-?\s*)?oled\b", low):
        panel = "oled"
    elif re.search(r"\bmini\s*-?\s*led\b", low) or _word_in_text("miniled", low):
        panel = "miniled"
    elif re.search(r"\b(?:fast\s+|nano\s+|rapid\s+)?ips\b", low):
        panel = "ips"
    elif re.search(r"\bva\b", low):
        panel = "va"
    elif re.search(r"\btn\b", low):
        panel = "tn"

    res: Optional[str] = None
    if re.search(r"\b(?:4k|uhd|ultra\s+hd|2160p|3840\s*x\s*2160)\b", low):
        res = "4k"
    elif re.search(r"\b(?:uwqhd|wqhd|qhd|quad\s+hd|2k|1440p|2560\s*x\s*1440|3440\s*x\s*1440)\b", low):
        res = "qhd"
    elif re.search(r"\b(?:fhd|full\s+hd|1080p|1920\s*x\s*1080)\b", low):
        res = "fhd"
    elif re.search(r"\b(?:720p|1366\s*x\s*768)\b", low) or re.search(r"\bhd\b(?!\+)", low):
        res = "hd"

    curved: Optional[bool] = None
    if re.search(r"\b(?:curvo|curva|curved)\b", low):
        curved = True
    elif re.search(r"\b(?:plano|plana|flat)\b", low):
        curved = False

    return (panel, res, curved)


def extract_watch_size_mm(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)
    m = re.search(r"\b(38|40|41|42|43|44|45|46|47|49)\s*mm\b", low)
    return f"{m.group(1)}mm" if m else None


def extract_watch_connectivity(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)
    if re.search(r"\b(?:lte|cellular|celular|4g|5g|esim)\b", low):
        return "cellular"
    if re.search(r"\b(?:gps|bluetooth|bt|wifi|wi-fi)\b", low):
        return "gps"
    return None


def extract_speaker_wattage(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)
    if "cargador" in low and not any(w in low for w in ("parlante", "soundbar", "torre", "speaker", "audio")):
        return None
    m = re.search(r"\b(\d{1,4})\s*(?:w|watts?|rms)\b", low)
    if not m:
        return None
    val = int(m.group(1))
    if val < 5 or val > 5000:
        return None
    return f"{val}w"


def extract_wifi_standard(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    low = strip_accents_lower(raw_text)
    if re.search(r"\b(?:wi[\s\-]?fi\s*7|wifi7|be\d{4})\b", low):
        return "wifi7"
    if re.search(r"\b(?:wi[\s\-]?fi\s*6e|wifi6e)\b", low):
        return "wifi6e"
    if re.search(r"\b(?:wi[\s\-]?fi\s*6|wifi6|ax\d{3,4})\b", low):
        return "wifi6"
    if re.search(r"\b(?:wi[\s\-]?fi\s*5|wifi5|ac\d{3,4})\b", low):
        return "wifi5"
    return None


def extract_pack_count(raw_text: str) -> int:
    """Detecta cantidad de unidades en multi-packs ('Pack 3', '2-Pack', 'x2', '3 Unidades'); por defecto 1."""
    if not raw_text:
        return 1
    low = strip_accents_lower(raw_text)
    patterns = (
        r"\bpack\s*(?:de\s*|x\s*)?(\d{1,2})\b",
        r"\b(\d{1,2})\s*[-/\s]?\s*pack\b",
        r"\b(?:paquete|kit|set)\s*(?:de\s*|x\s*)?(\d{1,2})\b",
        r"\bx\s*(\d{1,2})\s*(?:unidades?|unds?|pzas?|piezas?|focos?|sensores?|nodos?|routers?)?\b",
        r"\b(\d{1,2})\s*(?:unidades?|unds?|focos?|nodos?)\b",
    )
    for pat in patterns:
        for m in re.findall(pat, low):
            cnt = int(m)
            if 2 <= cnt <= 24:
                return cnt
    return 1


def extract_console_profile(raw_text: str) -> Dict[str, Any]:
    """Extrae plataforma, edición y bundle de juego de una consola de videojuegos."""
    low = strip_accents_lower(raw_text or "")
    platform: Optional[str] = None
    if re.search(r"\b(?:ps5|playstation\s*5)\b", low):
        platform = "ps5"
    elif re.search(r"\b(?:ps4|playstation\s*4)\b", low):
        platform = "ps4"
    elif re.search(r"\bswitch\s*2\b", low):
        platform = "switch_2"
    elif re.search(r"\b(?:nintendo\s+)?switch\b", low):
        platform = "switch_1"
    elif re.search(r"\bseries\s*s\b", low):
        platform = "xbox_series_s"
    elif re.search(r"\bseries\s*x\b", low):
        platform = "xbox_series_x"
    elif "steam deck" in low:
        platform = "steam_deck"
    elif "rog ally" in low:
        platform = "rog_ally"
    elif "legion go" in low:
        platform = "legion_go"

    is_slim = _word_in_text("slim", low)
    is_pro = _word_in_text("pro", low)
    is_oled = _word_in_text("oled", low)
    is_lite = _word_in_text("lite", low)
    is_digital = bool(
        re.search(r"\b(?:digital|all[\s\-]digital|sin\s+lectora?)\b", low)
    )
    explicit_disc = bool(
        not is_digital
        and re.search(r"\b(?:con\s+lectora?|lector\s+de\s+disco|blu[\s\-]?ray|disco)\b", low)
    )

    bundle_games: Set[str] = set()
    for g_key, g_markers in _CONSOLE_BUNDLE_GAMES:
        if any(gm in low for gm in g_markers):
            bundle_games.add(g_key)

    return {
        "platform": platform,
        "is_slim": is_slim,
        "is_pro": is_pro,
        "is_oled": is_oled,
        "is_lite": is_lite,
        "is_digital": is_digital,
        "explicit_disc": explicit_disc,
        "bundle_games": bundle_games,
    }


def _extract_peripheral_kind(raw_text: str, category: str) -> Optional[str]:
    if category != "accesorios_pc":
        return None
    low = strip_accents_lower(raw_text or "")
    has_teclado = bool(re.search(r"\b(?:teclado|keyboard)\b", low))
    has_mouse = bool(re.search(r"\b(?:mouse|raton)\b", low))
    if has_teclado and has_mouse:
        return "combo_teclado_mouse"
    if has_mouse:
        return "mouse"
    if has_teclado:
        return "teclado"
    if re.search(r"\b(?:webcam|camara\s+web)\b", low):
        return "webcam"
    if re.search(r"\b(?:mando|control|dualsense|joy[\s\-]?con|joystick)\b", low):
        return "mando"
    if re.search(r"\b(?:microfono)\b", low):
        return "microfono"
    if re.search(r"\b(?:mousepad|mouse\s+pad|pad\s+mouse)\b", low):
        return "mousepad"
    if re.search(r"\b(?:hub|docking|adaptador)\b", low):
        return "hub"
    if re.search(r"\b(?:tableta\s+grafica|wacom)\b", low):
        return "tableta_grafica"
    return None


def _extract_storage_medium(raw_text: str, category: str) -> Dict[str, Optional[str]]:
    if category != "almacenamiento_redes":
        return {"medium": None, "interface": None}
    low = strip_accents_lower(raw_text or "")
    medium: Optional[str] = None
    if re.search(r"\b(?:router|mesh|deco|repetidor|access\s+point|modem|switch\s+de\s+red)\b", low):
        medium = "networking"
    elif re.search(r"\b(?:microsd|micro\s+sd|sdxc|sdhc|tarjeta\s+de\s+memoria)\b", low):
        medium = "memory_card"
    elif re.search(r"\b(?:usb|pendrive|flash\s+drive)\b", low) and not _word_in_text("ssd", low) and "disco" not in low:
        medium = "usb_flash"
    elif re.search(r"\b(?:ssd|estado\s+solido|disco\s+solido|nvme)\b", low):
        medium = "ssd"
    elif re.search(r"\b(?:hdd|disco\s+duro)\b", low):
        medium = "hdd"

    interface: Optional[str] = None
    if re.search(r"\bnvme\b", low):
        interface = "nvme"
    elif re.search(r"\bsata\b", low):
        interface = "sata"
    return {"medium": medium, "interface": interface}


def _preprocess_canonical_text(raw_text: str, category: str = "") -> str:
    """Pre-normaliza unidades, abreviaturas y generaciones manteniendo tokens distintivos por categoría."""
    out = strip_accents_lower(raw_text or "")
    cat_low = strip_accents_lower(category or "").strip()

    # Quitar sufijos de color de código fabricante (-B, -W, -S, -K) como '27GS75Q-B' -> '27GS75Q'
    out = _SIGNATURE_COLOR_TRAILING_SUFFIX_RE.sub(r"\1", out)

    # Normalizar generaciones de auriculares/tablets/smart home: '(2da gen)', '3ra Generación' -> '2', '3'
    out = re.sub(r"\b(\d+)\s*(?:ra|da|ta|va|na|a|o)\s*gen(?:eracion)?\b", r"\1", out)
    out = re.sub(r"\bgen(?:eracion)?\s*(\d+)\b", r"\1", out)

    # Unificar expresiones de consola digital/estándar y plataformas
    out = re.sub(r"\b(?:all[\s\-]?digital|sin\s+lectora?)\b", "digital", out)
    out = re.sub(r"\bwatch\s*(\d{1,2})\b", r"watch \1", out)
    out = re.sub(r"\bbuds\s*(\d{1,2})\b", r"buds \1", out)
    out = re.sub(r"\bswitch\s*(\d)\b", r"switch \1", out)

    # Compactar modelos con guión intermedio inconsistente (WH-1000XM5 == WH1000XM5, SRS-ULT1000 == SRSULT1000)
    out = re.sub(r"\busb[\s\-]*c\b", "usbc", out)
    out = re.sub(r"\bwh[\s\-]*(\d{3,4}[a-z0-9]*)(?:/[a-z]{3,5})?\b", r"wh\1", out)
    out = re.sub(r"\bwf[\s\-]*(\d{3,4}[a-z0-9]*)(?:/[a-z]{3,5})?\b", r"wf\1", out)
    out = re.sub(r"\b((?:wh|wf|srs|ult)[\s\-]*[a-z]{0,3}\d{3,4}[n]?)[bwlpc]\b", r"\1", out)
    out = re.sub(r"\bsrs[\s\-]*([a-z]+\d+[a-z0-9]*)\b", r"srs\1", out)
    out = re.sub(r"\btp[\s\-]*link\b", "tplink", out)

    # Limpiar ruido comercial común que fragmenta firmas idénticas entre tiendas
    out = re.sub(
        r"\b(?:hp\s+app|sistema\s+continuo|todo[\s\-]+en[\s\-]+uno|all[\s\-]+in[\s\-]+one|a\s+color|"
        r"windows\s+1[01](?:\s+home)?(?:\s+single\s+language)?|free\s*dos|teclado\s+(?:en\s+)?espanol|"
        r"disco\s+(?:duro\s+)?solid[oe]|full\s+hd|series?\s+[123]|serie\s+[123]00|1[1234](?:va|ra|ta|th))\b",
        " ",
        out,
    )
    if cat_low == "televisores":
        out = re.sub(r"\b(?:un|qn)(\d{2,3})([a-z]{1,2}\d{2,4}[a-z]?)(?:[aefh]?gxpe|[ae]xpe|pe)?\b", r"\1 \2", out)
        out = re.sub(r"\boled(\d{2})([bcgmrwz]\d)(?:ps[abcd]|bs[abcd])?\b", r"oled \1 \2", out)
        out = re.sub(r"\b(\d{2})qned(\d{2,3})[a-z]{2,4}\b", r"\1 qned\2", out)
        out = re.sub(r"\bqd[\s\-]*mini[\s\-]*led\b", "qd miniled", out)
    elif cat_low == "impresoras" and re.search(r"\b[lg]\d{3,4}\b", out):
        out = re.sub(r"\b(?:ecotank|pixma)\b", " ", out)
    elif cat_low == "laptops":
        out = re.sub(r"\bcore\s+u([579])\b", r"core ultra \1", out)
        out = re.sub(r"\bryzen\s+ia\s+([579])\b", r"ryzen ai \1", out)
        out = re.sub(r"\bntel\b", "intel", out)
        out = re.sub(r"\bideapad\s+slim\s+([35])i\b", r"ideapad slim \1", out)
        out = _strip_gpu_vram_tokens(out)
    elif cat_low == "celulares":
        out = re.sub(r"\b\d{2,3}\s*mp\b", " ", out)
        out = re.sub(r"\b[567]\.\d{1,2}\s*(?:\"|''|pulgadas|pulg|inch|inches)?\b", " ", out)
        out = re.sub(r"\bgalaxy\s+([aszmf])[\s\-]+(\d{1,2})\b", r"galaxy \1\2", out)
        out = re.sub(r"\breno\s*(\d{1,2})\b", r"reno \1", out)
        out = re.sub(r"\bmotorola\s+moto\b", "motorola", out)
        out = re.sub(r"\bxiaomi\s+note\s+(1[4-9])\b", r"xiaomi redmi note \1", out)
    elif cat_low == "tablets":
        out = re.sub(r"\bsamsung\s+(?:tablet\s+)?(?:galaxy\s+)?tab\s+", "samsung tab ", out)
        out = re.sub(r"\bsamsung\s+(?:tablet\s+)?(s\d{1,2}\s+(?:lite|fe|plus|ultra))\b", r"samsung tab \1", out)
    elif cat_low == "audifonos":
        out = re.sub(r"\bnoise\s+cancelling\b", "anc", out)

    # Normalizar Wi-Fi, paneles, resoluciones, tamaños de reloj, tasas de refresco y vatios
    out = re.sub(r"\bwi[\s\-]?fi\s*(5|6e|6|7)\b", r"wifi\1", out)
    out = re.sub(r"\bmini\s*[\-\s]?\s*led\b", "miniled", out)
    out = re.sub(r"\bover[\s\-]?ear\b", "overear", out)
    out = re.sub(r"\bin[\s\-]?ear\b", "inear", out)
    out = re.sub(r"\b(?:ultra\s+hd|2160p|3840\s*x\s*2160)\b", "4k", out)
    out = re.sub(r"\b(?:quad\s+hd|1440p|2560\s*x\s*1440)\b", "qhd", out)
    out = re.sub(r"\b(?:uwqhd|3440\s*x\s*1440)\b", "wqhd", out)
    out = re.sub(r"\b(?:full\s+hd|1080p|1920\s*x\s*1080)\b", "fhd", out)
    out = re.sub(r"\b(\d{2})\s*mm\b", r"\1mm", out)
    out = re.sub(r"\b(\d{2,3})\s*hz\b", r"\1hz", out)
    if cat_low in {"audio", "audifonos", "smart_home"}:
        out = re.sub(r"\b(\d{1,4})\s*(?:watts?|rms)\b", r"\1w", out)
        out = re.sub(r"\b(\d{1,4})\s*w\b", r"\1w", out)
    out = re.sub(r"\b(?:cellular|esim)\b", "lte", out)

    # Packs explícitos en una unidad semántica ('pack3', 'pack2')
    out = re.sub(r"\bpack\s*(?:de\s*|x\s*)?(\d{1,2})\b", r"pack\1", out)
    out = re.sub(r"\b(\d{1,2})\s*[\-\s]?pack\b", r"pack\1", out)

    # Normalizar '500 GB' / '1024 GB' / '12/512GB' antes de tokenizar
    out = normalize_memory_and_storage(out)

    # Quitar símbolos de pulgadas manteniendo decimales (23.8" -> 23.8, 15.6 pulgadas -> 15.6)
    out = re.sub(
        r"\b(\d{1,3}(?:\.\d{1,2})?)\s*(?:\"|''|pulgadas|pulg|inch|inches)\b",
        r"\1 ",
        out,
    )

    if cat_low == "smartwatches":
        # En smartwatches 'cellular'/'lte' se conserva; 'bt'/'gps' base se omiten salvo en guardrail
        out = re.sub(r"\blte\b", "cellular", out)

    return re.sub(r"\s+", " ", out).strip()


def _dedupe_adjacent_phrases(tokens: List[str]) -> List[str]:
    out: List[str] = []
    for tok in tokens:
        if not out or out[-1] != tok:
            out.append(tok)
    # Colapsar repeticiones de bigramas adyacentes (ej. 'playstation 5 playstation 5')
    collapsed: List[str] = []
    i = 0
    while i < len(out):
        if i + 3 < len(out) and out[i] == out[i + 2] and out[i + 1] == out[i + 3]:
            collapsed.extend([out[i], out[i + 1]])
            i += 4
            continue
        collapsed.append(out[i])
        i += 1
    return collapsed


def build_canonical_product_signature(
    title: str,
    brand: str = "",
    url: str = "",
    category: str = "",
) -> str:
    """
    Construye una firma técnica canónica genérica para agrupar el mismo producto entre
    las 8 tiendas oficiales en todas las 14 categorías tech, sin sensibilidad a colores,
    orden de especificaciones ni palabras de relleno de cada retail.
    """
    from app.collectors.spec_extractor import normalize_brand

    cat_low = strip_accents_lower(category or "").strip()
    raw_clean = _strip_bundles_and_colors(strip_accents_lower(title or ""), category=cat_low)
    resolved_brand = normalize_brand(brand, raw_clean or (title or ""))
    brand_tok_raw = strip_accents_lower(resolved_brand).replace("-", "").strip()

    pre = _preprocess_canonical_text(raw_clean, category=cat_low)
    pre = strip_color_tokens(normalize_memory_and_storage(pre))
    expanded = expand_retail_abbreviations(pre)

    # Extraer MPNs largos (p.ej. 'X1504MA-BQ523W', '82XQ00LTLM', '15-FB3021LA') para evaluar firma limpia
    inline_mpns = set(extract_inline_manufacturer_mpns(title=raw_clean, url=url))

    if not expanded and url:
        path_txt = re.sub(r"\.(html?|php|aspx?)\b", " ", urlparse(url).path or "", flags=re.I)
        path_txt = strip_url_bundle_tail(normalize_tech_text(path_txt, expand_abbrevs=True, strip_colors=True))
        expanded = _preprocess_canonical_text(path_txt, category=cat_low)

    cat_filler = _CATEGORY_SIGNATURE_FILLER_TOKENS.get(cat_low, set())
    if not cat_filler:
        # Categoría desconocida: usar unión segura de relleno general sin tocar oled/4k/fhd si fueran relevantes
        cat_filler = {
            "celular", "celulares", "smartphone", "smartphones", "movil", "telefono",
            "laptop", "notebook", "portatil", "tablet", "tableta", "smart", "tv", "televisor",
            "impresora", "multifuncional", "consola", "monitor", "audifonos", "auriculares",
            "smartwatch", "parlante", "bluetooth", "bt", "wifi", "wi", "fi", "5g", "chip",
            "procesador", "fhd", "hd", "4k", "oled", "amoled", "uhd", "wuxga",
        }

    brand_alias_tokens: Set[str] = set()
    if brand_tok_raw:
        brand_alias_tokens.update(brand_tok_raw.split())
        brand_alias_tokens.add(brand_tok_raw.replace(" ", ""))
        if brand_tok_raw == "tp link":
            brand_alias_tokens.update({"tp", "link", "tplink"})

    # Normalizar pulgadas comerciales de monitor en la firma ('23.8' -> '24')
    mon_in = extract_monitor_inches(raw_clean, allow_implicit=(cat_low == "monitores")) if cat_low in {"monitores", ""} else None

    model_tokens: List[str] = []
    spec_tokens: List[str] = []
    seen_specs: Set[str] = set()

    for tok in expanded.split():
        low_tok = tok.lower().strip()
        if not low_tok or low_tok in _GLOBAL_SIGNATURE_FILLER_TOKENS or low_tok in cat_filler:
            continue
        if low_tok in brand_alias_tokens:
            continue
        if low_tok == "usb" and cat_low in {"audifonos", "smartwatches"}:
            continue
        if low_tok in _STORAGE_TB_EQUIV:
            low_tok = _STORAGE_TB_EQUIV[low_tok]

        # Normalizar tamaño comercial equivalente en monitores ('23.8' -> '24')
        if cat_low == "monitores" and mon_in and low_tok in _MONITOR_INCH_GROUP_MAP:
            low_tok = _MONITOR_INCH_GROUP_MAP[low_tok]

        is_screen_inch_tok = bool(
            (cat_low == "monitores" and (low_tok == mon_in or low_tok in MONITOR_STANDARD_INCHES))
            or (cat_low == "televisores" and low_tok.isdigit() and int(low_tok) in TV_STANDARD_INCHES)
        )
        is_spec_tok = bool(
            is_screen_inch_tok
            or re.match(r"^\d{1,4}(?:gb|tb)$", low_tok)
            or re.match(r"^\d{2,3}hz$", low_tok)
            or re.match(r"^\d{2}mm$", low_tok)
            or re.match(r"^\d{1,4}w$", low_tok)
            or re.match(r"^pack\d{1,2}$", low_tok)
            or low_tok in _SPEC_BUCKET_EXACT_TOKENS
        )
        if is_spec_tok:
            if low_tok not in seen_specs:
                seen_specs.add(low_tok)
                spec_tokens.append(low_tok)
        else:
            model_tokens.append(low_tok)

    # Colocar marca una sola vez al inicio y ordenar specs determinísticamente
    final_tokens: List[str] = []
    if brand_tok_raw:
        final_tokens.extend(brand_tok_raw.split())
    # Mantener orden estable: RAM (< 64GB) antes que almacenamiento, luego pantalla/mm/hz/w/res/panel/redes
    def _spec_sort_key(st: str) -> Tuple[int, float, str]:
        m_gb = re.match(r"^(\d+)gb$", st)
        if m_gb:
            val = int(m_gb.group(1))
            if val in VALID_RAM_NUMS_GB and val < 64:
                return (0, float(val), st)
            return (1, float(val), st)
        m_tb = re.match(r"^(\d+)tb$", st)
        if m_tb:
            return (1, float(int(m_tb.group(1)) * 1024), st)
        if cat_low in {"monitores", "televisores"} and re.match(r"^\d+(?:\.\d+)?$", st):
            return (2, float(st), st)
        if st.endswith("mm"):
            return (3, float(int(st[:-2])), st)
        if st.endswith("hz"):
            return (4, float(int(st[:-2])), st)
        if st.endswith("w"):
            return (5, float(int(st[:-1])), st)
        if st.startswith("pack"):
            return (7, float(int(st[4:])), st)
        return (6, 0.0, st)

    spec_tokens.sort(key=_spec_sort_key)
    dedup_models = _dedupe_adjacent_phrases(model_tokens)

    # Si existen MPNs largos en `inline_mpns`, omitirlos de la firma solo cuando quedan otros tokens de modelo específicos
    if inline_mpns and len(dedup_models) >= 2:
        stripped_models: List[str] = []
        skip_next = False
        for idx_m, m_tok in enumerate(dedup_models):
            if skip_next:
                skip_next = False
                continue
            compact_single = re.sub(r"[^a-z0-9]", "", m_tok)
            if compact_single in inline_mpns:
                continue
            if idx_m + 1 < len(dedup_models):
                compact_pair = re.sub(r"[^a-z0-9]", "", f"{m_tok}{dedup_models[idx_m + 1]}")
                if compact_pair in inline_mpns:
                    skip_next = True
                    continue
            if idx_m + 2 < len(dedup_models):
                compact_triple = re.sub(r"[^a-z0-9]", "", f"{m_tok}{dedup_models[idx_m + 1]}{dedup_models[idx_m + 2]}")
                if compact_triple in inline_mpns:
                    dedup_models[idx_m + 1] = ""
                    dedup_models[idx_m + 2] = ""
                    continue
            if m_tok:
                stripped_models.append(m_tok)
        stripped_models = [t for t in stripped_models if t]
        if stripped_models:
            cand_sig_no_mpn = " ".join(_dedupe_adjacent_phrases(final_tokens + stripped_models + spec_tokens))[:500].strip()
            if is_signature_specific_enough(cand_sig_no_mpn, brand=resolved_brand, category=cat_low):
                return cand_sig_no_mpn

    final_tokens.extend(dedup_models)
    final_tokens.extend(spec_tokens)

    return " ".join(_dedupe_adjacent_phrases(final_tokens))[:500].strip()


def is_signature_specific_enough(sig: str, brand: str = "", category: str = "") -> bool:
    """
    Evita agrupar títulos demasiado genéricos sin identificador de modelo (ej. 'samsung', 'logitech mouse', 'lg monitor 27'),
    pero permite firmas exactas sin dígitos cuando tienen marca + al menos 2 tokens válidos descriptivos/modelo.
    """
    if not sig:
        return False
    brand_words = set(strip_accents_lower(brand or "").replace("-", " ").split())
    non_brand = [t for t in sig.split() if t not in brand_words]
    if not non_brand:
        return False

    cat_low = strip_accents_lower(category or "").strip()
    generic_cat_tokens: Set[str] = set()
    if cat_low == "accesorios_pc":
        generic_cat_tokens = {"mouse", "teclado", "webcam", "pad", "hub", "cooler"}
    elif cat_low == "televisores":
        generic_cat_tokens = {"qled", "qned", "oled", "led", "lcd", "miniled", "nanocell", "uhd", "fhd", "hd"}

    non_spec = [
        t
        for t in non_brand
        if t not in _SPEC_BUCKET_EXACT_TOKENS
        and t not in generic_cat_tokens
        and not re.match(r"^\d+(?:gb|tb|hz|mm|w)$", t)
        and not re.match(r"^pack\d+$", t)
        and not (cat_low in {"monitores", "televisores", "laptops", "tablets"} and t in MONITOR_STANDARD_INCHES)
    ]
    if not non_spec:
        return False

    if any(re.search(r"\d", t) for t in non_spec):
        return True

    # Modelos o títulos reconocibles sin dígitos (ej. 'skullcandy jib inear', 'fiddler mouse pilas', 'airpods max')
    significant_words = [t for t in non_spec if len(t) >= 2]
    if len(significant_words) >= 2:
        return True
    if brand_words and len(non_brand) >= 2 and len(significant_words) >= 1:
        return True
    return False


def _extract_expanded_model_shapes(tokens: Sequence[str], brand_words: Set[str]) -> Dict[str, Set[str]]:
    """Extrae códigos de modelo alfanuméricos distintivos (p.ej. 'mk470', '27gs75q', 'xm5', 'ax55') para evitar colisiones."""
    grouped: Dict[str, Set[str]] = {}
    ignored = {"4g", "5g", "4k", "8k", "6e", "wi", "usb", "sata", "nvme"} | brand_words
    for tok in tokens:
        t = tok.lower()
        if t in ignored or t in STANDARD_STORAGE_TOKENS or t in _SPEC_BUCKET_EXACT_TOKENS:
            continue
        if re.match(r"^\d+(?:gb|tb|hz|mm|w)$", t) or re.match(r"^pack\d+$", t):
            continue
        m = re.match(r"^([a-z]{1,6})(\d{1,5}[a-z0-9]*)$", t)
        if m:
            prefix, rest = m.group(1), m.group(2)
            if prefix in {"r", "i"} and len(rest) == 1:
                continue
            shape_key = f"{prefix}:{len(rest)}"
            grouped.setdefault(shape_key, set()).add(t)
    return grouped


def extract_variant_profile(
    title: str,
    url: str = "",
    category: str = "",
    brand: str = "",
) -> Dict[str, Any]:
    """Extrae un perfil estructurado completo de variante para validar compatibilidad estricta multi-tienda."""
    from app.collectors.spec_extractor import normalize_brand

    cat_low = strip_accents_lower(category or "").strip()
    clean_title = _strip_bundles_and_colors(title or "", category=cat_low)
    resolved_brand = normalize_brand(brand, clean_title or (title or ""))
    brand_low = strip_accents_lower(resolved_brand).strip()
    brand_words = set(brand_low.replace("-", " ").split()) if brand_low else set()

    norm_text = normalize_tech_text(clean_title, expand_abbrevs=True, strip_colors=True)
    sig = build_canonical_product_signature(clean_title, resolved_brand, url, cat_low)

    allow_small = cat_low == "almacenamiento_redes" or any(
        w in norm_text for w in ("ssd", "microsd", "pendrive", "flash drive", "usb")
    )
    storages = extract_storage_tokens(norm_text, allow_small_external=allow_small)
    rams = (
        extract_ram_tokens(_strip_gpu_vram_tokens(norm_text))
        if cat_low in {"celulares", "laptops", "tablets", ""}
        else set()
    )

    modifiers = {m for m in STRICT_MODEL_MODIFIERS if _word_in_text(m, norm_text)}
    if cat_low in {"laptops", ""} and _word_in_text("go", norm_text) and "vivobook" in norm_text:
        modifiers.add("go")
    is_audio_cat = cat_low in {"audifonos", "audio"}
    inherent_anc_re = r"\b(?:wh\s*1000\s*xm[456]|wh\s*ch720n|wf\s*c710n|wf\s*1000\s*xm[45]|wh\s*ult900n)[a-z]*\b"
    has_anc = (
        bool(re.search(r"\b(?:anc|cancelacion\s+activa|noise\s+cancelling)\b", norm_text))
        or bool(re.search(inherent_anc_re, norm_text))
    ) if is_audio_cat else False
    raw_audio_low = strip_accents_lower(clean_title or "")
    wired_audio = (
        bool(
            re.search(r"\b(?:con\s+cable|cableado|cableada|alambrico|alambrica|3\.5\s*mm|jack)\b", raw_audio_low)
            or re.search(r"\b[a-z]*\d{3,4}\s+c\b", raw_audio_low)
            or re.search(r"\b(?:tune|wave|t)\s*\d{3,4}c\b", raw_audio_low)
        )
        if is_audio_cat
        else False
    )
    audio_form: Optional[str] = None
    if is_audio_cat:
        if re.search(r"\b(?:over\s*ear|overear|vincha|diadema)\b", norm_text):
            audio_form = "overear"
        elif re.search(r"\b(?:in\s*ear|inear|tws|earbuds)\b", norm_text):
            audio_form = "inear"

    is_tv = cat_low == "televisores" or (
        cat_low == "" and any(_word_in_text(w, norm_text) for w in ("televisor", "smart tv", "qled", "qned", "nanocell"))
    )
    is_mon = cat_low == "monitores" or (
        cat_low == "" and any(_word_in_text(w, norm_text) for w in ("monitor", "ultragear", "odyssey", "zenscreen"))
    )

    tv_inch = extract_screen_inches_from_text(clean_title) if is_tv else None
    if is_tv and tv_inch is None:
        for sz in TV_STANDARD_INCHES:
            if _word_in_text(str(sz), norm_text):
                tv_inch = float(sz)
                break

    mon_inch = extract_monitor_inches(clean_title, allow_implicit=is_mon) if is_mon else None
    hz = extract_refresh_rate_hz(clean_title) if (is_mon or is_tv or cat_low == "laptops") else None
    panel, res, curved = extract_panel_and_resolution(clean_title) if (is_mon or is_tv) else (None, None, None)

    is_watch = cat_low == "smartwatches" or any(
        w in norm_text for w in ("smartwatch", "apple watch", "galaxy watch", "huawei watch", "watch")
    )
    watch_mm = extract_watch_size_mm(clean_title) if is_watch else None
    watch_conn = extract_watch_connectivity(clean_title) if is_watch else None
    watch_tier = {t for t in ("ultra", "se", "classic", "active", "gt", "fit", "fe") if _word_in_text(t, norm_text)} if is_watch else set()

    tablet_cellular: Optional[bool] = None
    if cat_low == "tablets":
        tablet_cellular = any(_word_in_text(w, norm_text) for w in ("cellular", "lte", "5g", "4g"))

    phone_net: Optional[str] = None
    if cat_low == "celulares":
        if _word_in_text("5g", norm_text):
            phone_net = "5g"
        elif _word_in_text("4g", norm_text) or _word_in_text("lte", norm_text):
            phone_net = "4g"

    console_prof = extract_console_profile(clean_title) if cat_low == "consolas" or _word_in_text("consola", norm_text) else None
    speaker_watt = extract_speaker_wattage(clean_title) if cat_low == "audio" else None
    wifi_std = extract_wifi_standard(clean_title) if cat_low in {"almacenamiento_redes", "smart_home"} else None
    is_mesh = bool(_word_in_text("mesh", norm_text) or "deco" in norm_text) if cat_low == "almacenamiento_redes" else False
    pack_count = extract_pack_count(title or clean_title)
    peripheral_kind = _extract_peripheral_kind(clean_title, cat_low)
    storage_medium = _extract_storage_medium(clean_title, cat_low)
    hw_cpu_gpu = extract_cpu_and_gpu_signatures(norm_text) if cat_low in {"laptops", ""} else {"cpu_vendor": None, "cpu_tier": None, "cpu_sku": None, "gpu_model": None}
    laptop_screen_bucket = _canonical_laptop_screen_bucket(clean_title, norm_text) if cat_low == "laptops" else None
    is_touch = bool(re.search(r"\b(?:touch|tactil)\b", norm_text)) if cat_low == "laptops" else False
    is_2in1 = bool(re.search(r"\b(?:2\s+en\s+1|x360)\b", norm_text)) if cat_low == "laptops" else False
    is_oled_laptop = bool(re.search(r"\bp?oled\b", norm_text)) if cat_low == "laptops" else False
    model_shapes = _extract_expanded_model_shapes(sig.split(), brand_words)

    return {
        "category": cat_low,
        "brand": brand_low,
        "signature": sig,
        "storages": storages,
        "rams": rams,
        "modifiers": modifiers,
        "has_anc": has_anc,
        "wired_audio": wired_audio,
        "audio_form": audio_form,
        "tv_inch": int(round(tv_inch)) if tv_inch is not None else None,
        "mon_inch": mon_inch,
        "hz": hz,
        "panel": panel,
        "resolution": res,
        "curved": curved,
        "watch_mm": watch_mm,
        "watch_conn": watch_conn,
        "watch_tier": watch_tier,
        "tablet_cellular": tablet_cellular,
        "phone_net": phone_net,
        "console": console_prof,
        "speaker_watt": speaker_watt,
        "wifi_std": wifi_std,
        "is_mesh": is_mesh,
        "pack_count": pack_count,
        "peripheral_kind": peripheral_kind,
        "storage_medium": storage_medium,
        "hw": hw_cpu_gpu,
        "laptop_screen_bucket": laptop_screen_bucket,
        "is_touch": is_touch,
        "is_2in1": is_2in1,
        "is_oled_laptop": is_oled_laptop,
        "model_shapes": model_shapes,
    }


def are_listings_variant_compatible(prof_a: Dict[str, Any], prof_b: Dict[str, Any]) -> bool:
    """
    Comprueba simétricamente que dos perfiles de listing pertenecen exactamente al mismo producto y variante
    (rechaza Slim vs Pro, Digital vs Disco, 24" vs 27", 40mm vs 44mm, MK470 vs MK270, Pack 1 vs Pack 3, etc.).
    """
    cat_a = prof_a.get("category") or ""
    cat_b = prof_b.get("category") or ""
    if cat_a and cat_b and cat_a != cat_b:
        return False

    brand_a = prof_a.get("brand") or ""
    brand_b = prof_b.get("brand") or ""
    if brand_a and brand_b and brand_a != brand_b:
        return False

    # 1. Modificadores estrictos de gama/edición (Pro, Plus, Ultra, Air, FE, Lite, Max, Mini, etc.)
    if prof_a.get("modifiers") != prof_b.get("modifiers"):
        return False

    # 2. Pack multi-unidad vs unidad simple
    if int(prof_a.get("pack_count") or 1) != int(prof_b.get("pack_count") or 1):
        return False

    # 3. Capacidad de almacenamiento y RAM
    stor_a = prof_a.get("storages") or set()
    stor_b = prof_b.get("storages") or set()
    if stor_a and stor_b and not (stor_a & stor_b):
        return False

    ram_a = prof_a.get("rams") or set()
    ram_b = prof_b.get("rams") or set()
    if ram_a and ram_b and not (ram_a & ram_b):
        return False

    # 4. Smartwatches (tamaño de caja mm, LTE vs GPS, tier)
    mm_a, mm_b = prof_a.get("watch_mm"), prof_b.get("watch_mm")
    if mm_a and mm_b and mm_a != mm_b:
        return False
    conn_a, conn_b = prof_a.get("watch_conn"), prof_b.get("watch_conn")
    if (conn_a == "cellular") != (conn_b == "cellular"):
        return False
    if prof_a.get("watch_tier") != prof_b.get("watch_tier"):
        return False

    # 5. Monitores y TVs (pulgadas, Hz, panel, resolución, curvatura explícita)
    if prof_a.get("tv_inch") and prof_b.get("tv_inch") and prof_a["tv_inch"] != prof_b["tv_inch"]:
        return False
    if prof_a.get("mon_inch") and prof_b.get("mon_inch") and prof_a["mon_inch"] != prof_b["mon_inch"]:
        return False
    if prof_a.get("hz") and prof_b.get("hz") and prof_a["hz"] != prof_b["hz"]:
        return False

    pan_a, pan_b = prof_a.get("panel"), prof_b.get("panel")
    if (pan_a == "oled") != (pan_b == "oled") and (cat_a in {"monitores", "televisores"} or cat_b in {"monitores", "televisores"}):
        return False
    if (pan_a == "miniled") != (pan_b == "miniled") and (cat_a == "monitores" or cat_b == "monitores"):
        return False
    if pan_a and pan_b and pan_a != pan_b:
        return False

    res_a, res_b = prof_a.get("resolution"), prof_b.get("resolution")
    if res_a and res_b and res_a != res_b:
        return False

    curv_a, curv_b = prof_a.get("curved"), prof_b.get("curved")
    if curv_a is not None and curv_b is not None and curv_a != curv_b:
        return False

    # 6. Consolas (plataforma, Slim/Pro/OLED/Lite, Digital vs Disco, bundle de juego)
    con_a, con_b = prof_a.get("console"), prof_b.get("console")
    if con_a and con_b:
        if con_a["platform"] and con_b["platform"] and con_a["platform"] != con_b["platform"]:
            return False
        for key in ("is_slim", "is_pro", "is_oled", "is_lite", "is_digital"):
            if con_a[key] != con_b[key]:
                return False
        if con_a["is_digital"] and con_b["explicit_disc"]:
            return False
        if con_b["is_digital"] and con_a["explicit_disc"]:
            return False
        if con_a["bundle_games"] != con_b["bundle_games"]:
            return False

    # 7. Audífonos y audio (ANC, formato in-ear/over-ear, modelo cableado vs inalámbrico, potencia en watts)
    if bool(prof_a.get("has_anc")) != bool(prof_b.get("has_anc")):
        return False
    if bool(prof_a.get("wired_audio")) != bool(prof_b.get("wired_audio")):
        return False
    if prof_a.get("audio_form") and prof_b.get("audio_form") and prof_a["audio_form"] != prof_b["audio_form"]:
        return False
    if prof_a.get("speaker_watt") and prof_b.get("speaker_watt") and prof_a["speaker_watt"] != prof_b["speaker_watt"]:
        return False

    # 8. Redes, almacenamiento y periféricos PC
    if prof_a.get("wifi_std") and prof_b.get("wifi_std") and prof_a["wifi_std"] != prof_b["wifi_std"]:
        return False
    if bool(prof_a.get("is_mesh")) != bool(prof_b.get("is_mesh")):
        return False
    pk_a, pk_b = prof_a.get("peripheral_kind"), prof_b.get("peripheral_kind")
    if pk_a and pk_b and pk_a != pk_b:
        return False

    sm_a, sm_b = prof_a.get("storage_medium") or {}, prof_b.get("storage_medium") or {}
    if sm_a.get("medium") and sm_b.get("medium") and sm_a["medium"] != sm_b["medium"]:
        return False
    if sm_a.get("interface") and sm_b.get("interface") and sm_a["interface"] != sm_b["interface"]:
        return False

    # 9. Conectividad tablet/smartphone y CPU/GPU
    if prof_a.get("tablet_cellular") is not None and prof_b.get("tablet_cellular") is not None:
        if prof_a["tablet_cellular"] != prof_b["tablet_cellular"]:
            return False
    if prof_a.get("phone_net") and prof_b.get("phone_net") and prof_a["phone_net"] != prof_b["phone_net"]:
        return False

    hw_a, hw_b = prof_a.get("hw") or {}, prof_b.get("hw") or {}
    for hw_k in ("cpu_vendor", "cpu_tier", "cpu_sku", "gpu_model"):
        if hw_a.get(hw_k) and hw_b.get(hw_k) and hw_a[hw_k] != hw_b[hw_k]:
            return False
    if (hw_a.get("gpu_model") is not None) != (hw_b.get("gpu_model") is not None) and (cat_a == "laptops" or cat_b == "laptops"):
        return False

    sb_a, sb_b = prof_a.get("laptop_screen_bucket"), prof_b.get("laptop_screen_bucket")
    if sb_a and sb_b and sb_a != sb_b:
        return False
    if bool(prof_a.get("is_touch")) != bool(prof_b.get("is_touch")):
        return False
    if bool(prof_a.get("is_2in1")) != bool(prof_b.get("is_2in1")):
        return False
    if bool(prof_a.get("is_oled_laptop")) != bool(prof_b.get("is_oled_laptop")):
        return False

    # 10. Códigos alfanuméricos de modelo con misma forma (ej. mk470 vs mk270, 520bt vs 720bt, xm4 vs xm5)
    shapes_a = prof_a.get("model_shapes") or {}
    shapes_b = prof_b.get("model_shapes") or {}
    for shape_k, toks_a in shapes_a.items():
        toks_b = shapes_b.get(shape_k)
        if toks_b and not (toks_a & toks_b):
            has_prefix_match = any(
                a.startswith(b) or b.startswith(a)
                for a in toks_a
                for b in toks_b
            )
            if not has_prefix_match:
                return False

    return True


def _check_extended_category_guardrails(
    canonical_title: str,
    cand_title: str = "",
    cand_url: str = "",
) -> bool:
    """Extensión no intrusiva de `evaluate_strict_guardrails` para relojes, consolas, monitores y packs."""
    if not cand_title:
        # Cuando solo se dispone de URL persistida sin título, solo bloquear packs distintos si URL los declara
        canon_pack = extract_pack_count(canonical_title)
        url_pack = extract_pack_count(cand_url)
        if canon_pack != 1 and url_pack != 1 and canon_pack != url_pack:
            return False
        return True

    # Smartwatches
    canon_mm = extract_watch_size_mm(canonical_title)
    cand_mm = extract_watch_size_mm(cand_title) or extract_watch_size_mm(cand_url)
    if canon_mm and cand_mm and canon_mm != cand_mm:
        return False

    canon_low = strip_accents_lower(canonical_title)
    cand_low = strip_accents_lower(cand_title)
    if any(w in canon_low for w in ("smartwatch", "apple watch", "galaxy watch", "huawei watch", "redmi watch")):
        c_conn = extract_watch_connectivity(canonical_title)
        k_conn = extract_watch_connectivity(cand_title)
        if (c_conn == "cellular") != (k_conn == "cellular"):
            return False

    # Consolas
    if any(re.search(rf"\b{w}\b", canon_low) for w in ("consola", "playstation", "ps5", "ps4", "switch", "xbox")):
        con_c = extract_console_profile(canonical_title)
        con_k = extract_console_profile(cand_title)
        if con_c["platform"] and con_k["platform"] and con_c["platform"] != con_k["platform"]:
            return False
        for key in ("is_slim", "is_oled", "is_lite", "is_digital"):
            if con_c[key] != con_k[key]:
                return False
        if con_c["bundle_games"] != con_k["bundle_games"]:
            return False

    # Monitores
    if any(_word_in_text(w, canon_low) for w in ("monitor", "ultragear", "odyssey", "zenscreen")):
        m_in_c = extract_monitor_inches(canonical_title, allow_implicit=True)
        m_in_k = extract_monitor_inches(cand_title, allow_implicit=True)
        if m_in_c and m_in_k and m_in_c != m_in_k:
            return False
        hz_c = extract_refresh_rate_hz(canonical_title)
        hz_k = extract_refresh_rate_hz(cand_title)
        if hz_c and hz_k and hz_c != hz_k:
            return False
        pan_c, res_c, _ = extract_panel_and_resolution(canonical_title)
        pan_k, res_k, _ = extract_panel_and_resolution(cand_title)
        if (pan_c == "oled") != (pan_k == "oled"):
            return False
        if pan_c and pan_k and pan_c != pan_k:
            return False
        if res_c and res_k and res_c != res_k:
            return False

    # Audífonos (ANC y modelo cableado '530 C' vs inalámbrico)
    if any(_word_in_text(w, canon_low) for w in ("audifono", "audifonos", "auricular", "auriculares", "airpods", "headphone", "headset")):
        wired_c = bool(
            re.search(r"\b(?:con\s+cable|cableado|cableada|alambrico|alambrica|3\.5\s*mm|jack)\b", canon_low)
            or re.search(r"\b[a-z]*\d{3,4}\s+c\b", canon_low)
        )
        wired_k = bool(
            re.search(r"\b(?:con\s+cable|cableado|cableada|alambrico|alambrica|3\.5\s*mm|jack)\b", cand_low)
            or re.search(r"\b[a-z]*\d{3,4}\s+c\b", cand_low)
        )
        if wired_c != wired_k:
            return False
        anc_c = bool(re.search(r"\b(?:anc|cancelacion\s+activa|noise\s+cancelling)\b", canon_low))
        anc_k = bool(re.search(r"\b(?:anc|cancelacion\s+activa|noise\s+cancelling)\b", cand_low))
        if anc_c != anc_k:
            return False

    # Multi-packs
    if extract_pack_count(canonical_title) != extract_pack_count(cand_title):
        return False

    return True


_STRICT_PRIMARY_TECH_PREFIX_RE = re.compile(
    r"^\s*(?:laptop|notebook|macbook|ultrabook|chromebook|tablet|tableta|ipad|"
    r"impresora|multifuncional|monitor|consola|playstation|ps5|xbox|nintendo\s+switch)\b",
    re.I,
)

_STRICT_NON_TECH_BLACKLIST_RE = re.compile(
    r"\b(?:"
    # Ropa, calzado, moda y bolsos/billeteras
    r"gorro|gorra|sombrero|polo|polera|casaca|camiseta|camisa|blusa|chompa|"
    r"pantalon|jean|short|falda|vestido|zapatilla|zapatillas|zapato|zapatos|"
    r"sandalia|bota|medias|calcetines|ropa|tarjetero|billetera|cartera|bolso|"
    r"canguro|morral|maletin|correa\s+para\s+reloj|"
    # Viaje, equipaje e hidratación no-tech
    r"maleta|mochila|lonchera|tomatodo|termo|cantimplora|"
    # Cocina, hogar, electrodomésticos y muebles no-tech
    r"azucarero|taza|tazon|plato|olla|sarten|vaso|copa|tetera|cafetera|licuadora|"
    r"batidora|freidora|airfryer|horno|microondas|refrigeradora|frigobar|"
    r"congeladora|lavadora|secadora|cocina|encimera|campana\s+extractora|terma|"
    r"calentador|hervidor|tostadora|plancha|aire\s+acondicionado|deshumedecedor|"
    r"purificador|sabana|toalla|almohada|edredon|colchon|mueble|escritorio|"
    r"estante|repisa|silla|sofa|mesa|velador|cama|linterna|cobertor\s+de\s+auto|"
    r"herramienta|taladro|bicicleta|trotadora|mancuerna|guitarra|ukelele|"
    # Librería, juguetes, merch, alimentos y consumibles/fundas sueltas
    r"agenda|cuaderno|libro|comic|manga|peluche|funko|juguete|rompecabezas|"
    r"sticker|llavero|poster|chocolate|cafe|cerveza|perfume|maquillaje|crema|"
    r"shampoo|desodorante|pañal|panal|vitamina|proteina|"
    r"botella\s+de\s+tinta|toner|cartucho\s+de\s+tinta|tinta\s+(?:epson|canon|hp|brother)|"
    r"mica\s+protectora|vidrio\s+templado|carcasa|protector\s+de\s+pantalla|"
    r"book\s*cover|keyboard\s*cover|smart\s*cover|\bcover\b|"
    r"rack\s+(?:para\s+|de\s+|con\s+)?(?:tv|brazo)|brazo\s+para\s+tv|soporte\s+(?:para\s+|de\s+)?tv|"
    r"lector\s+de\s+disco\s+para|estuche|"
    # Juguetes y merchandising infantil (no confundir con electrónica real)
    r"disney|pixar|toy\s+story|woody|jessie|buzz\s+lightyear|barbie|hot\s+wheels|"
    r"fisher\s+price|paw\s+patrol|patrulla\s+canina|peppa\s+pig|stitch|frozen|elsa|"
    r"minnie|mickey|hello\s+kitty|bluey|gabby|sakar|lexibook|ekids|kiddesigns|"
    r"infantil|infantiles|para\s+ninos|de\s+juguete"
    r")\b",
    re.I,
)

_STRICT_KARAOKE_TOY_RE = re.compile(
    r"\b(?:mini\s+karaoke|microfono\s+(?:de\s+|con\s+)?karaoke|karaoke\s+con\s+microfono|karaoke\s+(?:woody|jessie|disney|frozen|barbie|infantil))\b",
    re.I,
)
_STRICT_REAL_AUDIO_CARRIER_RE = re.compile(
    r"\b(?:torre\s+de\s+sonido|equipo\s+de\s+sonido|minicomponente|partybox|xboom|boombox|soundbar|barra\s+de\s+sonido)\b",
    re.I,
)

_STRICT_NON_PC_COOLER_RE = re.compile(
    r"\bcooler\b(?=.*\b(?:\d+(?:\.\d+)?\s*(?:l|lt|lts|litros?|qt|oz)|playa|camping|hielera|termic[oa]|conservadora|basa|coleman|igloo|yeti|rey)\b)",
    re.I,
)
_STRICT_EXPLICIT_PC_COOLER_RE = re.compile(
    r"\b(?:cooler\s+(?:para\s+)?(?:laptop|notebook|cpu|pc|procesador|gabinete)|liquid\s+cooler|water\s+cooling|disipador)\b",
    re.I,
)

_STRICT_TECH_WHITELIST_RE = re.compile(
    r"\b(?:"
    r"celular|smartphone|iphone|galaxy\s+(?:s|a|z|m|f|note|tab|buds|watch)\w*|redmi|xiaomi|poco|motorola|honor|realme|oppo|vivo|oneplus|pixel\s+\d|"
    r"laptop|notebook|macbook|ultrabook|chromebook|vivobook|zenbook|ideapad|thinkpad|legion|loq|victus|pavilion|omen|inspiron|latitude|xps|nitro|predator|aspire|tuf|rog|"
    r"tablet|tableta|ipad|matepad|redmi\s+pad|lenovo\s+tab|xiaomi\s+pad|galaxy\s+tab|"
    r"televisor|smart\s+tv|\btv\b|qled|oled|qned|nanocell|mini[\s\-]?led|crystal\s+uhd|"
    r"impresora|multifuncional|ecotank|smart\s+tank|pixma|laserjet|deskjet|ink\s+tank|neverstop|"
    r"consola|playstation|ps5|ps4|xbox|nintendo\s+switch|switch\s+(?:2|oled|lite)|steam\s+deck|rog\s+ally|legion\s+go|dualsense|dualshock|joy[\s\-]?con|mando\s+(?:ps5|xbox|switch|gamer|inalambrico)|"
    r"monitor|ultragear|odyssey|zenscreen|proart|"
    r"audifono|audifonos|auricular|auriculares|airpods|freebuds|earbuds|earphone|headphone|headset|wh[\s\-]?\d{3,4}\w*|wf[\s\-]?\d{3,4}\w*|"
    r"smartwatch|reloj\s+inteligente|apple\s+watch|watch\s+fit|watch\s+gt|garmin|amazfit|mi\s+band|smart\s+band|fitbit|"
    r"parlante|parlantes|soundbar|barra\s+de\s+sonido|minicomponente|torre\s+de\s+sonido|subwoofer|tornamesa|microfono|speaker|altavoz|bocina|"
    r"camara|gopro|instax|osmo|dron|drone|dji|webcam|camara\s+web|lente|gimbal|"
    r"disco\s+(?:duro|externo|solido)|estado\s+solido|ssd|hdd|nvme|memoria\s+usb|pendrive|flash\s+drive|micro\s*sd|sdxc|sdhc|tarjeta\s+de\s+memoria|"
    r"router|mesh|deco|repetidor|extensor\s+(?:wifi|rango)|access\s+point|switch\s+(?:ethernet|gigabit|red)|nas|adaptador\s+(?:wifi|ethernet|red|usb|hdmi)|"
    r"teclado|keyboard|mouse|raton|hub\s+usb|docking|pad\s+mouse|mouse\s*pad|mousepad|cargador|power\s+bank|powerbank|ups|estabilizador|supresor|tableta\s+grafica|wacom|apple\s+pencil|base\s+enfriadora|"
    r"alexa|echo\s+(?:dot|pop|show|spot|studio|hub)|google\s+nest|nest\s+(?:mini|hub|audio)|chromecast|apple\s+tv|fire\s+tv|roku|mi\s+tv\s+stick|"
    r"foco\s+inteligente|ampolleta\s+inteligente|enchufe\s+inteligente|toma\s+inteligente|camara\s+(?:de\s+)?seguridad|camara\s+wifi|tapo|ezviz|imou|timbre\s+inteligente|cerradura\s+(?:digital|inteligente)|aspiradora\s+robot|robot\s+aspirador"
    r")\b",
    re.I,
)


def is_strict_tech_product(
    title: str,
    category: str = "",
    url: str = "",
    brand: str = "",
) -> bool:
    """
    Doble candado obligatorio SOLO TECNOLOGÍA (blacklist + whitelist positiva).
    Rechaza moda, equipaje, cocina, línea blanca, muebles, librería y coolers de camping,
    mientras conserva bundles legítimos cuyo dispositivo principal es hardware tech.
    """
    raw_title = (title or "").strip()
    if not raw_title or len(raw_title) < 4:
        return False

    low_title = strip_accents_lower(raw_title)
    cat_low = strip_accents_lower(category or "").strip()

    # Si el título declara primero hardware primario (ej. Laptop + Mochila), limpiar la cola de regalo
    # antes de evaluar la blacklist de mochilas/maletines.
    title_for_blacklist = low_title
    if _STRICT_PRIMARY_TECH_PREFIX_RE.search(low_title):
        title_for_blacklist = _strip_bundles_and_colors(low_title, category=cat_low)

    # Candado 1: Blacklist estricta (sobre título sin cola de regalo, marca y slug del producto)
    brand_low = strip_accents_lower(brand or "").strip()
    if _STRICT_NON_TECH_BLACKLIST_RE.search(f"{title_for_blacklist} {brand_low}".strip()):
        return False

    if "karaoke" in low_title and not _STRICT_REAL_AUDIO_CARRIER_RE.search(low_title):
        w_match = re.search(r"\b(\d{2,4})\s*(?:w|watts?|rms)\b", low_title)
        high_power = bool(w_match and int(w_match.group(1)) >= 50)
        if not high_power and (
            _STRICT_KARAOKE_TOY_RE.search(low_title)
            or "microfono" in low_title
            or "mini" in low_title
        ):
            return False

    if "cooler" in title_for_blacklist and not _STRICT_EXPLICIT_PC_COOLER_RE.search(title_for_blacklist):
        if _STRICT_NON_PC_COOLER_RE.search(title_for_blacklist) or cat_low != "accesorios_pc":
            return False

    if "ventilador" in title_for_blacklist and not _STRICT_EXPLICIT_PC_COOLER_RE.search(title_for_blacklist):
        if not re.search(r"\b(?:cpu|rgb|pwm|pc|gabinete|laptop|notebook)\b", title_for_blacklist):
            return False

    if re.search(r"\bfunda\b", title_for_blacklist):
        return False

    # Candado 2: Whitelist positiva obligatoria (título o slug específico del producto en la URL)
    url_slug = ""
    if url:
        path = (urlparse(url).path or "").strip("/")
        if path:
            parts = [p for p in path.split("/") if p and p.lower() != "p"]
            if parts:
                # Usar solo el último segmento (slug del producto) para no falsar con la ruta de categoría
                url_slug = strip_accents_lower(parts[-1].replace("-", " ").replace("_", " "))

    evidence = f"{low_title} {url_slug}".strip()
    return bool(_STRICT_TECH_WHITELIST_RE.search(evidence))


def _canonical_laptop_screen_bucket(raw_title: str, norm_text: str) -> Optional[str]:
    """Devuelve el bucket exacto de pulgadas en laptops sin confundir 15.3\" con 15.6\" o 16\"."""
    inches = extract_screen_inches_from_text(raw_title)
    if inches is None:
        m = re.search(
            r"\b(13(?:\.[036])?|14(?:\.[02])?|15(?:\.[036])?|16(?:\.[012])?|17(?:\.[03])?|18(?:\.0)?)\b",
            norm_text,
        )
        if m:
            tok = m.group(1)
            # Evitar falsos números cuando es '15' en 'Windows 15'? No existe, pero 'vivobook 15' == 15.6"
            if tok == "15" and any(w in norm_text for w in ("vivobook 15", "aspire 15", "hp 15", "victus 15", "v15", "nitro 15", "loq 15")):
                inches = 15.6
            elif tok == "15" and "15.3" in norm_text:
                inches = 15.3
            elif "." in tok or tok in {"13", "14", "16", "17", "18"}:
                if tok != "16" or any(w in norm_text for w in ("16", "v16", "f16", "a16", "g16", "vivobook 16", "omnibook 3 16", "legion pro 5i 16")):
                    inches = float(tok)
    if inches is None:
        if "macbook neo" in norm_text:
            return "13"
        if any(w in norm_text for w in ("zenbook a14", "zenbook 14")):
            return "14"
        if any(w in norm_text for w in ("tuf f16", "tuf 16", "tuf a16", "v16", "vivobook 16", "rog strix g16")):
            return "16"
        if any(w in norm_text for w in ("vivobook 15", "victus 15")):
            return "15.6"
        return None
    if 12.8 <= inches <= 13.7:
        return "13"
    if 13.8 <= inches <= 14.5:
        return "14"
    if 14.8 <= inches <= 15.35:
        return "15.3"
    if 15.4 <= inches <= 15.8:
        return "15.6"
    if 15.9 <= inches <= 16.3:
        return "16"
    if 16.8 <= inches <= 17.5:
        return "17"
    if 17.8 <= inches <= 18.5:
        return "18"
    return f"{inches:.1f}".rstrip("0").rstrip(".")


def _extract_laptop_product_line(norm_text: str, brand_low: str) -> Optional[str]:
    """Extrae la línea/familia canónica de laptop (ej. 'aspire_lite', 'vivobook_15', 'ideapad_slim_3')."""
    patterns: Tuple[Tuple[str, str], ...] = (
        (r"\baspire\s+lite\b", "aspire_lite"),
        (r"\baspire\s+(\d{1,2})\b", r"aspire_\1"),
        (r"\bnitro\s+v\b", "nitro_v"),
        (r"\bnitro\s+(\d{1,2})\b", r"nitro_\1"),
        (r"\bpredator\b", "predator"),
        (r"\bvivobook\s+go(?:\s+(1[456]))?\b", "vivobook_go"),
        (r"\bvivobook\s+s\s*(1[456])\b", r"vivobook_s_\1"),
        (r"\bvivobook\s+(1[456])\b", r"vivobook_\1"),
        (r"\bzenbook\s+duo\b", "zenbook_duo"),
        (r"\bzenbook\s+s\s*(1[46])\b", r"zenbook_s_\1"),
        (r"\bzenbook\s+(a14|14)\b", r"zenbook_\1"),
        (r"\btuf\s+(?:gaming\s+)?([fa]?1[56])\b", r"tuf_\1"),
        (r"\btuf\s+gaming\b", "tuf_gaming"),
        (r"\brog\s+strix\s+(g1[68])\b", r"rog_strix_\1"),
        (r"\b(?:gaming\s+)?v16\b", "asus_v16"),
        (r"\bideapad\s+slim\s+([135])i?\b", r"ideapad_slim_\1"),
        (r"\bideapad\s+([135])\b", r"ideapad_\1"),
        (r"\bloq\s+essential\b", "loq_essential"),
        (r"\bloq\b", "loq"),
        (r"\blegion\s+pro\s+([579])i?\b", r"legion_pro_\1"),
        (r"\blegion\b", "legion"),
        (r"\byoga\s+slim\s+([79])i?\b", r"yoga_slim_\1"),
        (r"\byoga\s+([79])i?\b", r"yoga_\1"),
        (r"\bvictus\b", "victus"),
        (r"\bomnibook\s+([35x])\b", r"omnibook_\1"),
        (r"\bomen\b", "omen"),
        (r"\bpavilion\b", "pavilion"),
        (r"\bmacbook\s+(neo|air|pro)\b", r"macbook_\1"),
        (r"\bv15\s+g\d\b", "v15"),
        (r"\bathlon\s+v15\b", "v15"),
        (r"\binspiron\s+(\d{2})\b", r"inspiron_\1"),
    )
    line: Optional[str] = None
    for pat, repl in patterns:
        m = re.search(pat, norm_text)
        if m:
            line = m.expand(repl) if "\\" in repl else repl
            break
    if line is None and brand_low == "hp":
        if re.search(r"\b1[456]-[a-z]{2}\d{4}la\b", norm_text) or _word_in_text("15", norm_text):
            line = "hp_series"
    if line == "tuf_16":
        line = "tuf_f16"
    if line is None:
        return None
    flags: List[str] = [line]
    if re.search(r"\b(?:2\s+en\s+1|x360)\b", norm_text):
        flags.append("2in1")
    if re.search(r"\b(?:touch|tactil)\b", norm_text):
        flags.append("touch")
    if re.search(r"\bp?oled\b", norm_text):
        flags.append("oled")
    return "_".join(flags)


def _extract_tv_series_code(norm_text: str) -> Optional[str]:
    """Extrae el identificador de serie/modelo en TVs (p.ej. 'u8000h', 'm70h', 'qned70', 'nu80', 'c6', 'c6k')."""
    m_lg_oled = re.search(r"\b(?:oled\s*\d{2}\s*)?([bcgmrwz]\d)\b", norm_text)
    if m_lg_oled and "oled" in norm_text:
        return f"oled_{m_lg_oled.group(1)}"
    m_sam = re.search(r"\b(?:un|qn)?(?:\d{2,3})?([umsq]\d{2,4}[fh]|qn\d{2}[fh]|ls\d{2}[fh]|s\d{2}[fh])\b", norm_text)
    if m_sam:
        return m_sam.group(1)
    for pat in (
        r"\b(qned\d{2,3}|nu\d{2})\b",
        r"\b(?:\d{2,3})([cpqt]\d[klg]|\d{2}[uq]\d[a-z]{2,4}|qd\d{2}[a-z]{2}|u\d[a-z]{3}|a\d{3}u?|du\d{4})\b",
        r"\b\d{2,3}([a-z]\d{1,3}[a-z]{1,4})\b",
    ):
        m = re.search(pat, norm_text)
        if m:
            return m.group(1)
    return None


def build_structured_match_key(
    title: str,
    brand: str = "",
    url: str = "",
    category: str = "",
) -> Optional[Tuple[str, ...]]:
    """
    Construye una clave de Huella Estructurada determinística por categoría para unir
    productos idénticos entre tiendas con formatos de título distintos, sin mezclar variantes:
    - Laptops: (category, brand, product_line, cpu_tier, ram_gb, storage_gb, screen_inches_bucket, gpu_or_none)
    - TVs / Monitores / Smartphones / Tablets / Consolas / Audífonos: claves estructuradas + firma limpia.
    """
    from app.collectors.spec_extractor import normalize_brand

    cat_low = strip_accents_lower(category or "").strip()
    if not cat_low or not title:
        return None

    clean_title = _strip_bundles_and_colors(title, category=cat_low)
    resolved_brand = normalize_brand(brand, clean_title or title)
    brand_low = strip_accents_lower(resolved_brand).strip()
    if not brand_low:
        return None

    pre = _preprocess_canonical_text(clean_title, category=cat_low)
    norm_text = normalize_tech_text(pre, expand_abbrevs=True, strip_colors=True)
    sig = build_canonical_product_signature(clean_title, resolved_brand, url, cat_low)

    if cat_low == "laptops":
        line = _extract_laptop_product_line(norm_text, brand_low)
        hw = extract_cpu_and_gpu_signatures(norm_text)
        cpu_tier = hw.get("cpu_tier")
        if line == "macbook_neo" and not cpu_tier:
            cpu_tier = "apple_a18_pro"
        rams = sorted(extract_ram_tokens(_strip_gpu_vram_tokens(norm_text)))
        storages = sorted(extract_storage_tokens(norm_text))
        screen_bucket = _canonical_laptop_screen_bucket(clean_title, norm_text)
        gpu_tok = hw.get("gpu_model") or "none"
        if line and cpu_tier and len(rams) == 1 and len(storages) == 1 and screen_bucket:
            return ("laptops", brand_low, line, cpu_tier, rams[0], storages[0], screen_bucket, gpu_tok)
        return None

    if cat_low == "televisores":
        tv_inch = extract_screen_inches_from_text(clean_title)
        if tv_inch is None:
            for sz in TV_STANDARD_INCHES:
                if _word_in_text(str(sz), norm_text):
                    tv_inch = float(sz)
                    break
        series = _extract_tv_series_code(norm_text)
        if series and tv_inch is not None:
            return ("televisores", brand_low, series, str(int(round(tv_inch))))
        return None

    if cat_low in {"celulares", "tablets", "consolas", "monitores", "audifonos"}:
        if sig and is_signature_specific_enough(sig, brand=resolved_brand, category=cat_low):
            return (cat_low, brand_low, sig)
        return None

    return None
