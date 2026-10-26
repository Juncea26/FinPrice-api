"""
Motor de Extracción, Normalización y Fusión Multi-Tienda de Especificaciones Técnicas (spec_extractor.py).
Extrae automáticamente tech_specs, brand y features desde el DOM y JSON estructurado de:
- Falabella (__NEXT_DATA__ attributes/specifications + tablas HTML)
- Tiendas Efe, La Curacao e Hiraoka (Magento 2 #product-attribute-specs-table / .additional-attributes)
- Ripley (window.__PRELOADED_STATE__.product.product.attributes / __NEXT_DATA__ + tablas HTML)
Incluye inferencia inteligente desde el título (extract_specs_from_title_fallback) y fusión multi-tienda (merge_product_specs).
"""
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger("collectors.spec_extractor")

# ==============================================================================
# 1. MAPEO CANÓNICO DE CLAVES (CANONICAL_SPEC_MAP)
# ==============================================================================

CANONICAL_SPEC_MAP: Dict[str, Tuple[str, ...]] = {
    "Marca": (
        "marca",
        "brand",
        "fabricante",
    ),
    "Procesador": (
        "procesador",
        "modelo del procesador",
        "modelo de procesador",
        "chip",
        "tipo de procesador",
        "cpu",
        "familia de procesador",
    ),
    "Memoria RAM": (
        "memoria ram",
        "ram",
        "capacidad de memoria ram",
        "memoria unificada",
        "memoria del sistema",
    ),
    "Almacenamiento": (
        "almacenamiento",
        "memoria interna",
        "capacidad de almacenamiento",
        "disco duro",
        "ssd",
        "rom",
        "capacidad de disco solido",
        "disco solido",
        "almacenamiento interno",
    ),
    "Pantalla": (
        "tamaño de la pantalla",
        "tamano de la pantalla",
        "tamaño de pantalla",
        "tamano de pantalla",
        "pantalla",
        "tipo de pantalla",
        "diagonal de la pantalla",
    ),
    "Resolución": (
        "resolución",
        "resolucion",
        "resolución de pantalla",
        "resolucion de pantalla",
        "definición",
        "definicion",
        "definición de pantalla",
        "definicion de pantalla",
        "calidad de imagen",
        "tasa de refresco",
    ),
    "Cámara Principal": (
        "resolución cámara posterior",
        "resolucion camara posterior",
        "cámara posterior",
        "camara posterior",
        "cámara principal",
        "camara principal",
        "cámara trasera",
        "camara trasera",
        "cámara",
        "camara",
    ),
    "Batería": (
        "capacidad de la batería",
        "capacidad de la bateria",
        "capacidad de batería",
        "capacidad de bateria",
        "tipo de batería",
        "tipo de bateria",
        "batería",
        "bateria",
        "autonomía",
        "autonomia",
        "duración de la batería",
        "duracion de la bateria",
    ),
    "Conectividad": (
        "conectividad",
        "red móvil",
        "red movil",
        "red",
        "wifi",
        "wi-fi",
        "conexión inalámbrica",
        "conexion inalambrica",
    ),
    "Sistema Operativo": (
        "sistema operativo",
        "os",
        "versión sistema operativo",
        "version sistema operativo",
    ),
}

# Mapa de marcas conocidas y su capitalización oficial
KNOWN_BRANDS_MAP: Dict[str, str] = {
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "poco": "Xiaomi",
    "apple": "Apple",
    "iphone": "Apple",
    "ipad": "Apple",
    "macbook": "Apple",
    "asus": "Asus",
    "lg": "LG",
    "lenovo": "Lenovo",
    "motorola": "Motorola",
    "moto": "Motorola",
    "hp": "HP",
    "sony": "Sony",
    "honor": "Honor",
    "acer": "Acer",
    "dell": "Dell",
    "msi": "MSI",
    "huawei": "Huawei",
    "hisense": "Hisense",
    "tcl": "TCL",
    "jbl": "JBL",
    "oppo": "Oppo",
    "realme": "Realme",
    "vivo": "Vivo",
    "nintendo": "Nintendo",
    "playstation": "Sony",
}

VALID_RAM_GB = {2, 3, 4, 6, 8, 12, 16, 18, 24, 32, 36, 48, 64}
VALID_STORAGE_GB = {32, 64, 128, 256, 512, 1024, 2048}


def _clean_key(key: str) -> str:
    """Limpia acentos, signos de puntuación y espacios de una etiqueta de especificación."""
    if not key:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(key).lower())
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", no_accents)
    return re.sub(r"\s+", " ", cleaned).strip()


def map_to_canonical_key(raw_label: str) -> Optional[str]:
    """Traduce el nombre de atributo de una tienda a su clave canónica si existe."""
    norm_label = _clean_key(raw_label)
    if not norm_label:
        return None

    # 1. Coincidencia exacta con los sinónimos definidos
    for canonical, synonyms in CANONICAL_SPEC_MAP.items():
        for syn in synonyms:
            if norm_label == _clean_key(syn):
                return canonical

    # 2. Coincidencia parcial controlada (excluyendo falsos positivos como 'camara frontal' o 'memoria expandible')
    excluded_substrings = (
        "frontal",
        "expandible",
        "empaque",
        "garantia",
        "peso",
        "alto",
        "ancho",
        "profundidad",
        "dimension",
        "incluye",
        "color",
        "precio",
    )
    if any(ex in norm_label for ex in excluded_substrings):
        return None

    for canonical, synonyms in CANONICAL_SPEC_MAP.items():
        for syn in synonyms:
            syn_clean = _clean_key(syn)
            if len(syn_clean) >= 4 and syn_clean in norm_label:
                return canonical

    return None


# ==============================================================================
# 2. FUNCIONES DE NORMALIZACIÓN DE VALORES
# ==============================================================================

def normalize_brand(raw_brand: Optional[str], title: str = "") -> str:
    """Normaliza la marca a su capitalización estándar o la infiere desde el título."""
    if raw_brand:
        cleaned = str(raw_brand).strip()
        lower = _clean_key(cleaned)
        if lower in KNOWN_BRANDS_MAP:
            return KNOWN_BRANDS_MAP[lower]
        for token in lower.split():
            if token in KNOWN_BRANDS_MAP:
                return KNOWN_BRANDS_MAP[token]
        if len(cleaned) >= 2 and not cleaned.isdigit():
            return cleaned.upper() if len(cleaned) <= 3 else cleaned.title()

    if title:
        title_norm = _clean_key(title)
        for token in title_norm.split():
            if token in KNOWN_BRANDS_MAP:
                return KNOWN_BRANDS_MAP[token]

    return ""


def normalize_ram(raw_val: str) -> Optional[str]:
    """Normaliza la Memoria RAM al formato estándar '{N} GB' (ej. '8 GB', '12 GB', '16 GB')."""
    if not raw_val:
        return None
    text = str(raw_val).upper()
    # Buscar patrón explícito con GB
    matches = re.findall(r"\b(\d{1,3})\s*GB\b", text)
    for m in matches:
        num = int(m)
        if num in VALID_RAM_GB:
            return f"{num} GB"
    # Si el campo era únicamente un número válido de RAM (ej. '12' en la fila Memoria RAM)
    bare = re.match(r"^\s*(\d{1,2})\s*$", text)
    if bare and int(bare.group(1)) in VALID_RAM_GB:
        return f"{int(bare.group(1))} GB"
    return None


def normalize_storage(raw_val: str) -> Optional[str]:
    """Normaliza el Almacenamiento al formato estándar '{N} GB' o '{N} TB' (ej. '128 GB', '512 GB', '1 TB')."""
    if not raw_val:
        return None
    text = str(raw_val).upper()
    tb_match = re.search(r"\b(\d{1,2})\s*TB\b", text)
    if tb_match:
        return f"{int(tb_match.group(1))} TB"

    gb_matches = re.findall(r"\b(\d{2,4})\s*GB\b", text)
    for m in gb_matches:
        num = int(m)
        if num in VALID_STORAGE_GB:
            if num == 1024:
                return "1 TB"
            return f"{num} GB"

    bare = re.match(r"^\s*(\d{2,4})\s*$", text)
    if bare and int(bare.group(1)) in VALID_STORAGE_GB:
        val = int(bare.group(1))
        return "1 TB" if val == 1024 else f"{val} GB"
    return None


def normalize_processor(raw_val: str) -> Optional[str]:
    """Limpia y estandariza el nombre del procesador."""
    if not raw_val:
        return None
    s = re.sub(r"\s+", " ", str(raw_val)).strip(" .,-")
    if not s or len(s) < 2 or s.lower() in {"si", "sí", "no", "n/a", "otro"}:
        return None
    # Estandarizaciones frecuentes
    s = re.sub(r"\bqualcomm\s+snapdragon\b", "Snapdragon", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsnapdragon\b", "Snapdragon", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmediatek\s+dimensity\b", "MediaTek Dimensity", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdimensity\b", "MediaTek Dimensity", s, flags=re.IGNORECASE)
    s = re.sub(r"MediaTek\s+MediaTek\s+Dimensity", "MediaTek Dimensity", s, flags=re.IGNORECASE)
    s = re.sub(r"\bexynos\b", "Exynos", s, flags=re.IGNORECASE)
    s = re.sub(r"\bintel\s+core\b", "Intel Core", s, flags=re.IGNORECASE)
    s = re.sub(r"\bamd\s+ryzen\b", "AMD Ryzen", s, flags=re.IGNORECASE)
    if re.match(r"^m[1-5](\s+pro|\s+max|\s+ultra)?$", s, flags=re.IGNORECASE):
        s = f"Apple {s.upper()}"
    elif re.match(r"^chip\s+m[1-5]\b", s, flags=re.IGNORECASE):
        s = re.sub(r"^chip\s+", "Apple ", s, flags=re.IGNORECASE)
    return s


def normalize_resolution(raw_val: str) -> Optional[str]:
    """Normaliza la resolución o calidad de imagen."""
    if not raw_val:
        return None
    s = re.sub(r"\s+", " ", str(raw_val)).strip(" .,-")
    if not s or s.lower() in {"si", "sí", "no", "n/a"}:
        return None
    if re.search(r"\b4k\b|\b3840\s*x\s*2160\b|\buhd\b", s, flags=re.IGNORECASE):
        if "oled" in s.lower() and "120" in s.lower():
            return "OLED 4K 120Hz"
        return "4K Ultra HD"
    if re.search(r"\bfull\s*hd\b|\bfhd\b|\b1920\s*x\s*1080\b", s, flags=re.IGNORECASE):
        return "Full HD"
    return s


def normalize_camera(raw_val: str) -> Optional[str]:
    """Normaliza la Cámara Principal exigiendo unidades válidas (ej. MP) y descartando conteos de lentes ('1', '2')."""
    if not raw_val:
        return None
    s = re.sub(r"\s+", " ", str(raw_val)).strip(" .,-")
    if re.match(r"^\d+$", s):
        return None
    if "mp" not in s.lower() and "megapix" not in s.lower() and "píxeles" not in s.lower():
        return None
    s = re.sub(r"(\d+)\s*mp\b", r"\1 MP", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\+\s*", " + ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_battery(raw_val: str) -> Optional[str]:
    """Normaliza la Batería exigiendo unidades (mAh, Wh, horas) y descartando enteros sueltos."""
    if not raw_val:
        return None
    s = re.sub(r"\s+", " ", str(raw_val)).strip(" .,-")
    if re.match(r"^\d+(\.\d+)?$", s):
        return None
    if not re.search(r"\b(mah|wh|hora|horas|hrs)\b", s, flags=re.IGNORECASE):
        return None
    s = re.sub(r"(\d+)\s*mah\b", r"\1 mAh", s, flags=re.IGNORECASE)
    return s


def normalize_connectivity(raw_val: str) -> Optional[str]:
    """Normaliza la Conectividad (5G, 4G, Wi-Fi, Bluetooth)."""
    if not raw_val:
        return None
    s = re.sub(r"\s+", " ", str(raw_val)).strip(" .,-")
    if s.lower() in {"si", "sí", "yes", "no", "n/a", "liberado"}:
        return None
    if re.search(r"\b5g\b", s, flags=re.IGNORECASE):
        return "5G"
    if re.search(r"\b4g\b", s, flags=re.IGNORECASE):
        return "4G LTE"
    if re.search(r"\bwi-?fi\s*6e?\b", s, flags=re.IGNORECASE):
        return "Wi-Fi 6"
    if re.search(r"\bwi-?fi\b", s, flags=re.IGNORECASE):
        return "Wi-Fi"
    return s


# ==============================================================================
# 3. INFERENCIA INTELIGENTE DE RESPALDO DESDE EL TÍTULO
# ==============================================================================

def extract_specs_from_title_fallback(title: str) -> Dict[str, str]:
    """
    Extrae automáticamente especificaciones técnicas desde el título cuando la tienda
    no las incluye en su tabla HTML.
    """
    specs: Dict[str, str] = {}
    if not title:
        return specs

    clean_t = str(title).strip()

    # 1. Marca
    brand = normalize_brand(None, clean_t)
    if brand:
        specs["Marca"] = brand

    # 2. Patrón combinado RAM+Storage (ej. '8+128GB', '12+512GB', '12/512GB')
    combo_match = re.search(r"\b(\d{1,2})\s*(?:GB)?\s*[+/]\s*(\d{2,4})\s*(GB|TB)?\b", clean_t, flags=re.IGNORECASE)
    if combo_match:
        ram_cand = int(combo_match.group(1))
        stor_cand = int(combo_match.group(2))
        unit = (combo_match.group(3) or "GB").upper()
        if ram_cand in VALID_RAM_GB:
            specs["Memoria RAM"] = f"{ram_cand} GB"
        if unit == "TB" or stor_cand in VALID_STORAGE_GB:
            specs["Almacenamiento"] = f"{stor_cand} TB" if unit == "TB" else f"{stor_cand} GB"

    # 3. Memoria RAM y Almacenamiento explícitos o múltiples tokens GB/TB en el título
    ram_explicit = re.search(r"\b(\d{1,2})\s*GB\s*RAM\b", clean_t, flags=re.IGNORECASE)
    if ram_explicit and int(ram_explicit.group(1)) in VALID_RAM_GB:
        specs["Memoria RAM"] = f"{int(ram_explicit.group(1))} GB"

    stor_explicit = re.search(r"\b(\d{1,4})\s*(GB|TB)\s*(?:SSD|ROM|NVME)\b", clean_t, flags=re.IGNORECASE)
    if stor_explicit:
        val = int(stor_explicit.group(1))
        unit = stor_explicit.group(2).upper()
        specs["Almacenamiento"] = f"{val} {unit}"

    # Escanear todos los tokens '{N}GB' / '{N}TB' restantes
    all_cap_matches = re.findall(r"\b(\d{1,4})\s*(GB|TB)\b", clean_t, flags=re.IGNORECASE)
    for num_str, unit_str in all_cap_matches:
        num = int(num_str)
        unit = unit_str.upper()
        if unit == "TB":
            specs.setdefault("Almacenamiento", f"{num} TB")
        elif num >= 64 and num in VALID_STORAGE_GB:
            specs.setdefault("Almacenamiento", "1 TB" if num == 1024 else f"{num} GB")
        elif num < 64 and num in VALID_RAM_GB:
            specs.setdefault("Memoria RAM", f"{num} GB")

    # 4. Procesador desde el título
    proc_patterns = [
        r"\b(Snapdragon\s+[A-Za-z0-9\s\-]+?(?:Gen\s*\d+|Elite|Ultra|Plus)?)\b",
        r"\b(Exynos\s+\d{3,4})\b",
        r"\b((?:MediaTek\s+)?Dimensity\s+\d{3,4}(?:[\-\s]*Ultra|[\-\s]*Pro|[\-\s]*Max)?)\b",
        r"\b(Intel\s+Core\s+(?:Ultra\s+)?(?:i[3579]|[3579])(?:\s*-\s*[A-Za-z0-9]+)?)\b",
        r"\b(AMD\s+Ryzen\s+[3579](?:\s+\d{4}[A-Za-z]*)?)\b",
        r"\b(Apple\s+M[1-5](?:\s+Pro|\s+Max|\s+Ultra)?)\b",
        r"\b(?:Chip\s+)?(M[1-5](?:\s+Pro|\s+Max|\s+Ultra)?)\b",
        r"\b(A1[5-9](?:\s+Pro|\s+Bionic)?)\b",
    ]
    for pat in proc_patterns:
        pm = re.search(pat, clean_t, flags=re.IGNORECASE)
        if pm:
            raw_p = pm.group(1).strip()
            if re.match(r"^A1[5-9]", raw_p, flags=re.IGNORECASE) and "apple" not in raw_p.lower():
                raw_p = f"Apple {raw_p.upper()}"
            norm_p = normalize_processor(raw_p)
            if norm_p:
                specs["Procesador"] = norm_p
                break

    # 5. Conectividad desde el título
    if re.search(r"\b5G\b", clean_t, flags=re.IGNORECASE):
        specs["Conectividad"] = "5G"
    elif re.search(r"\bWi-?Fi\s*6\b", clean_t, flags=re.IGNORECASE):
        specs["Conectividad"] = "Wi-Fi 6"
    elif re.search(r"\bWi-?Fi\b", clean_t, flags=re.IGNORECASE):
        specs["Conectividad"] = "Wi-Fi"
    elif re.search(r"\b4G\b", clean_t, flags=re.IGNORECASE):
        specs["Conectividad"] = "4G LTE"

    # 6. Pantalla y Resolución desde el título
    screen_size_m = re.search(r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|''|pulgadas)\b", clean_t, flags=re.IGNORECASE)
    panel_m = re.search(r"\b(OLED\s*evo|AMOLED|OLED|QLED|Liquid\s+Retina|Super\s+Retina|IPS)\b", clean_t, flags=re.IGNORECASE)
    if screen_size_m and panel_m:
        specs["Pantalla"] = f'{screen_size_m.group(1)}" {panel_m.group(1)}'
    elif screen_size_m:
        specs["Pantalla"] = f'{screen_size_m.group(1)}"'
    elif panel_m:
        specs["Pantalla"] = panel_m.group(1)

    if re.search(r"\b4K\b|\bUHD\b", clean_t, flags=re.IGNORECASE):
        if "oled" in clean_t.lower() and "120hz" in clean_t.lower():
            specs["Resolución"] = "OLED 4K 120Hz"
        else:
            specs["Resolución"] = "4K Ultra HD"
    elif re.search(r"\b1\.5K\b", clean_t, flags=re.IGNORECASE):
        specs["Resolución"] = "1.5K AMOLED 120Hz" if "amoled" in clean_t.lower() else "1.5K"
    elif re.search(r"\b(?:FHD|Full\s*HD)\b", clean_t, flags=re.IGNORECASE):
        specs["Resolución"] = "Full HD"
    elif re.search(r"\bWUXGA\+?\b", clean_t, flags=re.IGNORECASE):
        hz = re.search(r"\b(\d{2,3}\s*Hz)\b", clean_t, flags=re.IGNORECASE)
        specs["Resolución"] = f"WUXGA+ {hz.group(1)}" if hz else "WUXGA+"

    # 7. Cámara si aparece en título (ej. '200MP' o '200M')
    cam_m = re.search(r"\b(\d{2,3})\s*MP?\b", clean_t, flags=re.IGNORECASE)
    if cam_m and int(cam_m.group(1)) in {48, 50, 64, 108, 200}:
        specs.setdefault("Cámara Principal", f"{int(cam_m.group(1))} MP")

    return specs


# ==============================================================================
# 4. EXTRACTORES DOM / JSON POR TIENDA
# ==============================================================================

def _extract_html_spec_tables(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """Extrae pares (etiqueta, valor) desde tablas de especificaciones HTML (Magento 2, Falabella, Ripley, Hiraoka)."""
    pairs: List[Tuple[str, str]] = []
    selectors = (
        "#product-attribute-specs-table tr, "
        "table.additional-attributes tr, "
        ".additional-attributes-wrapper table tr, "
        ".product.info.detailed table tr, "
        ".specification-table tr, "
        ".product-specifications tr, "
        "table tr"
    )
    for tr in soup.select(selectors):
        cells = tr.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            val = cells[1].get_text(" ", strip=True)
            if label and val and label.lower() not in {"atributo", "especificación", "especificacion"}:
                pairs.append((label, val))
    return pairs


def _extract_falabella_json_specs(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """Extrae specifications / attributes desde #__NEXT_DATA__ de Falabella."""
    pairs: List[Tuple[str, str]] = []
    next_script = soup.find("script", id="__NEXT_DATA__")
    if not next_script or not next_script.string:
        return pairs
    try:
        data = json.loads(next_script.string)
        props = data.get("props", {}).get("pageProps", {})
        prod = props.get("productData", {}) or props.get("product", {})
        if prod.get("brand"):
            pairs.append(("Marca", str(prod["brand"])))

        for attr_list_key in ("attributes", "specifications", "specs"):
            attr_list = prod.get(attr_list_key)
            if isinstance(attr_list, list):
                for item in attr_list:
                    if isinstance(item, dict):
                        k = str(item.get("name") or item.get("label") or item.get("id") or "")
                        v = item.get("value") or item.get("values")
                        if isinstance(v, list):
                            v = ", ".join(str(x) for x in v if x)
                        if k and v:
                            pairs.append((k, str(v)))
            elif isinstance(attr_list, dict):
                for k, v in attr_list.items():
                    if k and v:
                        pairs.append((str(k), str(v)))
    except Exception as e:
        logger.debug(f"Error extrayendo specs JSON de Falabella: {e}")
    return pairs


def _extract_ripley_json_specs(soup: BeautifulSoup, raw_html: str) -> List[Tuple[str, str]]:
    """Extrae attributes desde window.__PRELOADED_STATE__ y #__NEXT_DATA__ de Ripley."""
    pairs: List[Tuple[str, str]] = []

    # 1. Buscar en #__NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})
            prod = (
                props.get("detailProps", {}).get("data", {}).get("product", {})
                or props.get("product", {})
            )
            if prod.get("brand"):
                pairs.append(("Marca", str(prod["brand"])))
            attrs = prod.get("attributes") or prod.get("specifications") or []
            if isinstance(attrs, list):
                for item in attrs:
                    if isinstance(item, dict):
                        k = str(item.get("name") or item.get("label") or "")
                        v = str(item.get("value") or "")
                        if k and v:
                            pairs.append((k, v))
        except Exception:
            pass

    # 2. Buscar en window.__PRELOADED_STATE__
    preloaded_match = re.search(
        r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*(?:;|</script>)",
        raw_html,
        flags=re.DOTALL,
    )
    if preloaded_match:
        try:
            state = json.loads(preloaded_match.group(1))
            prod = state.get("product", {}).get("product", {}) or state.get("product", {})
            if prod.get("brand"):
                pairs.append(("Marca", str(prod["brand"])))
            attrs = prod.get("attributes") or []
            if isinstance(attrs, list):
                for item in attrs:
                    if isinstance(item, dict):
                        k = str(item.get("name") or item.get("label") or "")
                        v = str(item.get("value") or "")
                        if k and v:
                            pairs.append((k, v))
        except Exception:
            pass

    return pairs


def normalize_raw_pairs_to_specs(
    raw_pairs: Sequence[Tuple[str, str]], title: str = ""
) -> Dict[str, str]:
    """
    Convierte una secuencia de pares (etiqueta_tienda, valor_tienda) al diccionario
    estandarizado tech_specs utilizando CANONICAL_SPEC_MAP y el fallback de título.
    """
    specs: Dict[str, str] = {}
    screen_size: Optional[str] = None
    screen_type: Optional[str] = None
    res_value: Optional[str] = None
    refresh_rate: Optional[str] = None

    for raw_k, raw_v in raw_pairs:
        norm_k_clean = _clean_key(raw_k)
        canonical = map_to_canonical_key(raw_k)
        val = str(raw_v).strip()
        if not canonical or not val:
            continue

        if canonical == "Marca":
            b = normalize_brand(val, title)
            if b:
                specs["Marca"] = b

        elif canonical == "Procesador":
            p = normalize_processor(val)
            if p and ("Procesador" not in specs or len(p) > len(specs["Procesador"])):
                specs["Procesador"] = p

        elif canonical == "Memoria RAM":
            r = normalize_ram(val)
            if r:
                specs["Memoria RAM"] = r

        elif canonical == "Almacenamiento":
            st = normalize_storage(val)
            if st:
                specs["Almacenamiento"] = st

        elif canonical == "Pantalla":
            if "tamaño" in norm_k_clean or "tamano" in norm_k_clean or "diagonal" in norm_k_clean:
                screen_size = val
            elif "tipo" in norm_k_clean:
                screen_type = re.sub(r"\bdisplay\b", "", val, flags=re.IGNORECASE).strip()
            else:
                specs.setdefault("Pantalla", val)

        elif canonical == "Resolución":
            if "refresco" in norm_k_clean:
                refresh_rate = val
            else:
                nr = normalize_resolution(val)
                if nr and (not res_value or "4K" in nr or "HD" in nr or "K" in nr):
                    res_value = nr

        elif canonical == "Cámara Principal":
            cam = normalize_camera(val)
            if cam:
                specs["Cámara Principal"] = cam

        elif canonical == "Batería":
            bat = normalize_battery(val)
            if bat:
                specs["Batería"] = bat

        elif canonical == "Conectividad":
            conn = normalize_connectivity(val)
            if conn:
                # Priorizar 5G sobre otros valores genéricos
                if specs.get("Conectividad") != "5G":
                    specs["Conectividad"] = conn

        elif canonical == "Sistema Operativo":
            if val.lower() not in {"si", "sí", "no"}:
                specs.setdefault("Sistema Operativo", val)

    # Consolidar Pantalla si se obtuvieron tamaño y tipo por separado
    if screen_size and screen_type:
        specs["Pantalla"] = f"{screen_size} {screen_type}".strip()
    elif screen_size:
        specs["Pantalla"] = screen_size
    elif screen_type and "Pantalla" not in specs:
        specs["Pantalla"] = screen_type

    # Consolidar Resolución y tasa de refresco
    if res_value and refresh_rate and refresh_rate.lower() not in res_value.lower():
        specs["Resolución"] = f"{res_value} {refresh_rate}".strip()
    elif res_value:
        specs["Resolución"] = res_value
    elif refresh_rate:
        specs["Resolución"] = refresh_rate

    # Aplicar inferencia inteligente desde el título como respaldo para cualquier campo faltante
    title_fallback = extract_specs_from_title_fallback(title)
    for k, v in title_fallback.items():
        if k not in specs or not specs[k]:
            specs[k] = v

    return specs


# ==============================================================================
# 5. AUTOGENERACIÓN DE CARACTERÍSTICAS PRINCIPALES (features: List[str])
# ==============================================================================

def generate_product_features(
    soup: Optional[BeautifulSoup],
    tech_specs: Dict[str, str],
    title: str = "",
    existing_features: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Extrae puntos destacados reales de la tienda y los completa con resúmenes legibles
    generados desde tech_specs (ej. 'Procesador: Exynos 1580', 'Memoria RAM: 8 GB'),
    garantizando siempre entre 4 y 6 características reales listas para mostrar en la app.
    """
    features: List[str] = []
    seen_lower = set()

    noise_phrases = (
        "imprimir esta ficha",
        "ver más",
        "ver mas",
        "envío gratis",
        "envio gratis",
        "términos y condiciones",
        "terminos y condiciones",
        "garantía del proveedor",
        "agregar al carrito",
    )

    def _add_feature(feat_text: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(feat_text)).strip(" .•-\t\n\r")
        if len(cleaned) < 6 or len(cleaned) > 140:
            return
        low = cleaned.lower()
        if any(np in low for np in noise_phrases):
            return
        if low not in seen_lower:
            seen_lower.add(low)
            features.append(cleaned)

    # 1. Extraer viñetas reales de la descripción / resumen del producto en el DOM
    if soup is not None:
        for li in soup.select(
            ".product.attribute.overview li, "
            ".product.attribute.description li, "
            ".product-highlights li, "
            ".feature-list li"
        ):
            _add_feature(li.get_text(" ", strip=True))
            if len(features) >= 4:
                break

    # 2. Completar con resúmenes legibles generados directamente desde tech_specs
    priority_spec_keys = (
        "Procesador",
        "Memoria RAM",
        "Almacenamiento",
        "Pantalla",
        "Resolución",
        "Cámara Principal",
        "Batería",
        "Conectividad",
        "Sistema Operativo",
    )
    for key in priority_spec_keys:
        if len(features) >= 6:
            break
        val = tech_specs.get(key)
        if val:
            summary = f"{key}: {val}"
            # Evitar duplicar si el valor ya está explícito en la misma forma
            _add_feature(summary)

    # 3. Si aún hay menos de 4 características, completar con existing_features o Marca/Modelo
    if existing_features:
        for ef in existing_features:
            if len(features) >= 6:
                break
            _add_feature(ef)

    if len(features) < 4 and tech_specs.get("Marca"):
        _add_feature(f"Marca: {tech_specs['Marca']}")
    if len(features) < 4 and title:
        _add_feature(f"Modelo: {title}")

    return features[:6]


# ==============================================================================
# 6. EXTRACCIÓN INTEGRAL Y FUSIÓN MULTI-TIENDA
# ==============================================================================

def extract_product_specs(
    html: str, title: str = "", store_id: str = ""
) -> Dict[str, Any]:
    """
    Punto de entrada principal por tienda: procesa el HTML/JSON-LD junto con el título
    y devuelve {'brand': str, 'tech_specs': Dict[str, str], 'features': List[str]}.
    """
    soup = BeautifulSoup(html, "lxml") if html else None
    raw_pairs: List[Tuple[str, str]] = []

    if soup is not None:
        if store_id == "falabella" or soup.find("script", id="__NEXT_DATA__"):
            raw_pairs.extend(_extract_falabella_json_specs(soup))
        if store_id == "ripley" or "__PRELOADED_STATE__" in (html or ""):
            raw_pairs.extend(_extract_ripley_json_specs(soup, html))

        # Extraer tablas HTML de especificaciones (Magento 2: Efe, Curacao, Hiraoka, así como Falabella/Ripley)
        raw_pairs.extend(_extract_html_spec_tables(soup))

        # Extraer también de las viñetas de resumen en Hiraoka si tienen formato 'Etiqueta Valor'
        for li in soup.select(".product.attribute.overview li, .product.attribute.description li"):
            txt = li.get_text(" ", strip=True).rstrip(".")
            if ":" in txt:
                parts = txt.split(":", 1)
                raw_pairs.append((parts[0].strip(), parts[1].strip()))
            else:
                for prefix in (
                    "Resolución cámara posterior",
                    "Capacidad de la batería",
                    "Sistema Operativo",
                    "Tipo de Pantalla",
                    "Pantalla",
                ):
                    if txt.lower().startswith(prefix.lower()):
                        val_part = txt[len(prefix) :].strip()
                        if val_part:
                            raw_pairs.append((prefix, val_part))

    tech_specs = normalize_raw_pairs_to_specs(raw_pairs, title=title)
    brand = tech_specs.get("Marca") or normalize_brand(None, title)
    if brand:
        tech_specs["Marca"] = brand

    features = generate_product_features(soup=soup, tech_specs=tech_specs, title=title)

    return {
        "brand": brand,
        "tech_specs": tech_specs,
        "features": features,
    }


def merge_product_specs(
    specs_list: Sequence[Dict[str, str]],
    base_specs: Optional[Dict[str, str]] = None,
    title: str = "",
) -> Dict[str, str]:
    """
    Fusión Multi-Tienda:
    Combina las fichas técnicas extraídas en vivo de múltiples tiendas priorizando los valores
    reales de tienda más completos, y usa base_specs / título únicamente como respaldo.
    """
    merged: Dict[str, str] = {}

    # 1. Fusionar primero las especificaciones reales extraídas en vivo de cada tienda
    for store_specs in specs_list:
        if not store_specs or not isinstance(store_specs, dict):
            continue
        norm_store = normalize_raw_pairs_to_specs(
            [(k, str(v)) for k, v in store_specs.items() if v], title=""
        )
        for k, v in norm_store.items():
            if not v:
                continue
            val_str = str(v).strip()
            if k in {"Memoria RAM", "Almacenamiento", "Marca"}:
                merged[k] = val_str
            elif k not in merged or not merged[k]:
                merged[k] = val_str
            else:
                current = merged[k]
                if len(val_str) > len(current) and len(val_str) <= 60:
                    merged[k] = val_str

    # 2. Completar únicamente claves faltantes usando base_specs normalizados
    if base_specs:
        base_pairs = [(k, str(v)) for k, v in base_specs.items() if v]
        norm_base = normalize_raw_pairs_to_specs(base_pairs, title=title)
        for k, v in norm_base.items():
            if (k not in merged or not merged[k]) and v:
                merged[k] = str(v)

    # 3. Asegurar normalización final de Memoria RAM, Almacenamiento y Marca
    if "Memoria RAM" in merged:
        norm_r = normalize_ram(merged["Memoria RAM"])
        if norm_r:
            merged["Memoria RAM"] = norm_r
    if "Almacenamiento" in merged:
        norm_s = normalize_storage(merged["Almacenamiento"])
        if norm_s:
            merged["Almacenamiento"] = norm_s

    brand = normalize_brand(merged.get("Marca"), title)
    if brand:
        merged["Marca"] = brand

    # 4. Completar cualquier atributo aún faltante desde el título
    for k, v in extract_specs_from_title_fallback(title).items():
        if k not in merged or not merged[k]:
            merged[k] = v

    return merged
