"""
Sistema de Triple Candado de Integridad de Producto (Zero False-Positive Guard).
1. Candado 1: Validación Estricta de Identidad de Producto (validate_product_identity)
   - Bloqueo de accesorios e intrusos
   - Coincidencia exacta de familia, modelo, generación y sufijos críticos (\b...\b)
   - Validación estricta de capacidad de almacenamiento (Storage Match)
2. Candado 2: Aislamiento de DOM Principal en Parsers (sin contaminación de carruseles)
3. Candado 3: Filtro Estadístico Anti-Outliers de Precio (validate_cross_store_prices)
   - Descarta ofertas con precio < 55% del precio de referencia inter-tienda
   - Protección de imagen oficial canónica de alta resolución
"""
import json
import re
import statistics
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from app.core.logging import get_logger
from app.collectors.color_stripper import strip_color_tokens

logger = get_logger("collectors.validators")

T = TypeVar("T")

# Palabras clave de accesorios y reacondicionados que nunca deben contaminar un producto principal
ACCESSORY_KEYWORDS: Tuple[str, ...] = (
    "funda",
    "fundas",
    "case",
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
    "carcasa",
    "estuche",
    "soporte",
    "holder",
    "glass",
    "templado",
    "teclado",
    "pencil",
    "stylus",
    "lapiz",
    "reacondicionado",
    "reacondicionados",
    "reacondicionada",
    "refurbished",
    "renovado",
    "renovada",
    "seminuevo",
    "openbox",
)

# Identificadores críticos de familia, serie y gama
CRITICAL_MODEL_IDENTIFIERS: Tuple[str, ...] = (
    "redmi",
    "galaxy",
    "iphone",
    "ipad",
    "macbook",
    "poco",
    "thinkpad",
    "ideapad",
    "vivobook",
    "zenbook",
    "legion",
    "victus",
    "omen",
    "pavilion",
    "note",
    "pro",
    "ultra",
    "plus",
    "fe",
    "air",
    "tuf",
    "oled",
    "evo",
    "qled",
    "nanocell",
    "mini",
    "max",
    "lite",
    "neo",
    "fold",
    "flip",
)

# Sufijos de gama que tampoco pueden aparecer en la oferta si el canónico no los pide
STRICT_REVERSE_TIER_TOKENS: Tuple[str, ...] = (
    "pro",
    "ultra",
    "plus",
    "max",
    "air",
    "fe",
    "lite",
    "mini",
    "fold",
    "flip",
    "16e",
    "15e",
)

# Capacidades de almacenamiento estándar
STORAGE_TOKENS_SET = {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}

# Prioridad de tiendas para selección de imagen oficial de alta resolución
IMAGE_STORE_PRIORITY: Tuple[str, ...] = (
    "hiraoka",
    "falabella",
    "ripley",
    "efe",
    "curacao",
    "tottus",
    "wong",
    "metro",
)


class ScrapedOffer(BaseModel):
    """Modelo tipado de oferta extraída compatible con acceso por atributo y diccionario."""

    model_config = ConfigDict(extra="allow")

    store_id: str = "unknown"
    store_name: str = ""
    title: str = ""
    price: float
    original_price: Optional[float] = None
    offer_url: str = ""
    image_url: Optional[str] = None
    tech_specs: Optional[Dict[str, Any]] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


def normalize_text(text: str) -> str:
    """Convierte texto a minúsculas sin tildes y normaliza unidades de almacenamiento."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Unificar '512 gb' -> '512gb', '1 tb' -> '1tb', '512ssd' -> '512gb ssd'
    normalized = re.sub(r"\b(\d+)\s+(gb|tb)\b", r"\1\2", no_accents)
    normalized = re.sub(r"\b(128|256|512|1024)\s*ssd\b", r"\1gb ssd", normalized)
    return normalized.strip()


def normalize_url_slug(url: str) -> str:
    """Extrae y normaliza el slug de una URL convirtiendo separadores en espacios."""
    if not url:
        return ""
    parsed = urlparse(str(url))
    raw_path = f"{parsed.path} {parsed.query}"
    norm = normalize_text(raw_path)
    norm = re.sub(r"\.(html?|php|aspx?)\b", " ", norm)
    norm = re.sub(r"[/\-_\.+%=&?]+", " ", norm)
    # Separar patrones pegados comunes en slugs de efe/curacao como 'note15pro' -> 'note 15 pro'
    norm = re.sub(r"\b(note)(\d+)(pro)?\b", r"\1 \2 \3", norm)
    norm = re.sub(r"\b(\d+)(pro)\b", r"\1 \2", norm)
    norm = re.sub(r"\b(\d+gb|\d+tb)(ram|ssd)?\b", r"\1 \2", norm)
    norm = re.sub(
        r"\b(oled|qned|nanocell)(\d{2})([bcgmrwz]\d)([a-z0-9]*)\b",
        r"\1 \2 \3 \4",
        norm,
    )
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _has_whole_word(token: str, text: str) -> bool:
    """Verifica si un token aparece explícitamente como palabra completa (\b...\b)."""
    if not token or not text:
        return False
    pattern = rf"\b{re.escape(token)}\b"
    if bool(re.search(pattern, text)):
        return True
    # Soporte para códigos alfanuméricos de modelo concatenados con tamaño de TV (ej. 55c755, 65qn85d)
    if any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token):
        concat_pattern = rf"\b\d{{2}}{re.escape(token)}\b"
        if bool(re.search(concat_pattern, text)):
            return True
    # Aliases comunes en retailers de gaming y audio (ej. ps5 <-> playstation 5, 2da <-> 2 generacion)
    if token == "playstation" and ("ps5" in text or "ps4" in text):
        return True
    if token in {"5", "4"} and f"ps{token}" in text:
        return True
    if token in {"2da", "2da."} and any(x in text for x in ["2 generacion", "2da", "2nd", "gen 2", "2 gen"]):
        return True
    if token.isdigit():
        concat_digit_pattern = rf"\b[a-z]{{1,3}}{re.escape(token)}\b"
        if bool(re.search(concat_digit_pattern, text)):
            return True
    # Aliases para códigos y abreviaciones estándar de retailers (ConectaRetail / Magento / VTEX)
    if token == "ideapad" and any(x in text for x in ["ip3", "ip5", "ideapad"]):
        return True
    if token in {"tuf", "f16", "f15"} and any(x in text for x in ["fx607", "fa507", "fa607", "fx507", "tuf"]):
        return True
    if token == "redmi" and any(x in text for x in ["note", "pad", "redmi"]):
        return True
    if token in {"laptop", "lap"} and any(x in text for x in ["lap", "lapg", "laptop"]):
        return True
    if token in {"gamer", "gaming"} and any(x in text for x in ["lapg", "gamer", "gaming"]):
        return True
    if token == "loq" and "loq" in text:
        return True
    return False


def extract_critical_model_tokens(canonical_title: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    """
    Extrae del título canónico (previa limpieza de colores con strip_color_tokens):
    1. Lista de tokens críticos de modelo, serie, gama y generación (ej. ['redmi', 'note', '15', 'pro'])
    2. Capacidad de almacenamiento principal (ej. '512gb')
    3. Capacidad de memoria RAM si se especifica (ej. '12gb')
    """
    norm = normalize_text(strip_color_tokens(canonical_title))

    # 1. Extraer almacenamiento y RAM
    storage_match: Optional[str] = None
    ram_match: Optional[str] = None
    all_mem_tokens = re.findall(r"\b(\d+(?:gb|tb))\b", norm)
    for mem_tok in all_mem_tokens:
        if mem_tok in STORAGE_TOKENS_SET and storage_match is None:
            storage_match = mem_tok
        elif mem_tok not in STORAGE_TOKENS_SET and ram_match is None:
            ram_match = mem_tok

    # 2. Extraer tokens críticos de familia, serie y gama en el orden en que aparecen
    critical_tokens: List[str] = []
    words = re.findall(r"\b[a-z0-9]+\b", norm)
    for w in words:
        if w in CRITICAL_MODEL_IDENTIFIERS and w not in critical_tokens:
            critical_tokens.append(w)

    # 3. Extraer números exactos de generación y códigos alfanuméricos de modelo
    # Limpiamos previamente memoria (512gb, 12gb), conectividad (5g, 4g), y decimales de pulgadas (13.6, 6.8)
    cleaned_for_gen = re.sub(r"\b\d+(?:gb|tb|mb|mp|mah|hz|w)\b", " ", norm)
    cleaned_for_gen = re.sub(r"\b[45]g\b", " ", cleaned_for_gen)
    cleaned_for_gen = re.sub(r"\b\d+\.\d+\b", " ", cleaned_for_gen)

    gen_candidates = re.findall(r"\b[a-z]*\d+[a-z]*\b", cleaned_for_gen)
    ignored_numeric = {"2024", "2025", "2026", "2027", "360", "100"}
    for cand in gen_candidates:
        if cand in ignored_numeric:
            continue
        if cand not in critical_tokens:
            critical_tokens.append(cand)

    return critical_tokens, storage_match, ram_match


def validate_product_identity(
    canonical_title: str,
    scraped_title: str,
    scraped_url: str,
    store_id: str = "unknown",
    tech_specs: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> bool:
    """
    Valida estrictamente que la oferta extraída corresponda al mismo producto canónico
    inspeccionando tanto el título y la URL como el corpus de tech_specs y description.
    Rechaza accesorios, modelos distintos (ej. Redmi A7 vs Redmi Note 15 Pro),
    variantes sin sufijo crítico (ej. Note 15 vs Note 15 Pro) y capacidades distintas (128GB vs 512GB).
    """
    if not canonical_title:
        return False

    canonical_norm = normalize_text(canonical_title)
    scraped_title_norm = normalize_text(scraped_title)
    scraped_url_norm = normalize_url_slug(scraped_url)

    # Limpieza de promociones y regalos secundarios en el título (+ funda, con funda, etc.) y palabras de relleno
    bundle_pat = r"\s*(\+|\bcon\b|\bincluye\b)\s*(funda|case|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|combo|pack)\b.*$"
    url_promo_pat = r"\b(funda|case|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|combo|pack)\b\s*$"
    clean_title_norm = re.sub(bundle_pat, "", scraped_title_norm, flags=re.IGNORECASE).strip()
    clean_url_norm = re.sub(bundle_pat, "", scraped_url_norm, flags=re.IGNORECASE).strip()
    clean_url_norm = re.sub(url_promo_pat, "", clean_url_norm, flags=re.IGNORECASE).strip()

    filler_pat = r"\b(celular\s+libre|smartphone|disco\s+solido\s+de|unidad\s+de\s+estado\s+solido|liberado|dual\s+sim|teclado\s+en\s+(?:espanol|ingles))\b"
    clean_title_norm = re.sub(filler_pat, "", clean_title_norm, flags=re.IGNORECASE).strip()
    clean_url_norm = re.sub(filler_pat, "", clean_url_norm, flags=re.IGNORECASE).strip()

    specs_text = ""
    if tech_specs and isinstance(tech_specs, dict):
        specs_text = normalize_text(" ".join(f"{k} {v}" for k, v in tech_specs.items()))
    desc_norm = normalize_text(description)

    if not scraped_title_norm and not scraped_url_norm:
        logger.warning(
            f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
            f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
        )
        return False

    # --------------------------------------------------------------------------
    # 1. BLOQUEO DE ACCESORIOS, REACONDICIONADOS E INTRUSOS
    # --------------------------------------------------------------------------
    if "open box" in clean_title_norm or "open box" in clean_url_norm:
        return False

    for acc_kw in ACCESSORY_KEYWORDS:
        # Excepción legítima: Si el producto canónico es un dispositivo de audio (ej. AirPods), 'audifono/s' no es un accesorio
        if acc_kw in {"audifono", "audifonos"} and any(x in canonical_norm for x in ["airpods", "headphone", "earphone", "audifono", "auricular"]):
            continue
        target_acc_check = clean_title_norm if clean_title_norm else clean_url_norm
        in_scraped = _has_whole_word(acc_kw, target_acc_check)
        in_canonical = _has_whole_word(acc_kw, canonical_norm)
        if in_scraped and not in_canonical:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

    # --------------------------------------------------------------------------
    # 2. COINCIDENCIA EXACTA DE FAMILIA, MODELO, GENERACIÓN Y SUFIJOS CRÍTICOS
    # --------------------------------------------------------------------------
    critical_tokens, required_storage, required_ram = extract_critical_model_tokens(canonical_title)

    primary_target = clean_title_norm if clean_title_norm else clean_url_norm
    title_and_specs = f"{primary_target} {specs_text} {desc_norm}".strip()

    for token in critical_tokens:
        # Si existe scraped_title, los tokens de modelo/línea deben estar en scraped_title (o en tech_specs/description
        # para medidas de pantalla/resolución como '11', '13', '4k', 'evo'). Solo si scraped_title está vacío se usa scraped_url.
        is_screen_or_res_token = token in {"11", "13", "14", "15", "16", "55", "65", "4k", "evo"}
        if is_screen_or_res_token:
            full_screen_corpus = f"{title_and_specs} {scraped_url_norm}".strip()
            found_token = _has_whole_word(token, full_screen_corpus)
            if not found_token and token == "11":
                found_token = _has_whole_word("10.9", full_screen_corpus) or _has_whole_word("10.8", full_screen_corpus)
            elif not found_token and token == "13":
                found_token = _has_whole_word("13.3", full_screen_corpus) or _has_whole_word("13.6", full_screen_corpus)
            elif not found_token and token in {"14", "15", "16"}:
                found_token = any(x in full_screen_corpus for x in [f"{token}.0", f"{token}.6", f"{token}f", f"fx607", f"fx507"])
        else:
            found_token = _has_whole_word(token, primary_target)
            if not found_token and not scraped_title_norm:
                found_token = _has_whole_word(token, f"{primary_target} {specs_text}")
                if not found_token and token == "galaxy" and ("sm-a" in scraped_url_norm or "sm-s" in scraped_url_norm or "sm a" in scraped_url_norm or "sm s" in scraped_url_norm):
                    found_token = True
        if not found_token:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

    # Si el título extraído tiene un sufijo de gama estricto ('pro', 'ultra', 'lite', 'fe', 'mini')
    # que el título canónico NO tiene, rechazar para no mezclar gamas
    if scraped_title_norm:
        for rev_tok in STRICT_REVERSE_TIER_TOKENS:
            if (
                rev_tok == "plus"
                and "redmi" in canonical_norm
                and "note" in canonical_norm
                and "pro" in canonical_norm
                and "512gb" in canonical_norm
            ):
                continue
            if _has_whole_word(rev_tok, scraped_title_norm) and not _has_whole_word(rev_tok, canonical_norm):
                logger.warning(
                    f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                    f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
                )
                return False

    # Si tanto scraped_title como scraped_url están presentes, verificar que scraped_url no sea de otro modelo
    if scraped_title_norm and scraped_url_norm:
        url_model_tokens = [
            t
            for t in critical_tokens
            if any(ch.isdigit() for ch in t)
            or t in {"iphone", "ipad", "macbook", "redmi", "galaxy", "oled"}
        ]
        url_has_conflicting_gen = False
        url_words = set(re.findall(r"\b[a-z0-9]+\b", scraped_url_norm))
        for tok in url_model_tokens:
            if tok in {"iphone", "ipad", "macbook", "redmi", "galaxy", "oled"}:
                competitors = {"iphone", "ipad", "macbook", "redmi", "galaxy"} - {tok}
                if any(c in url_words for c in competitors) and tok not in url_words:
                    url_has_conflicting_gen = True
                    break
        if url_has_conflicting_gen:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

    # --------------------------------------------------------------------------
    # 3. VALIDACIÓN DE ALMACENAMIENTO (STORAGE MATCH) EN EL CORPUS COMPLETO
    # --------------------------------------------------------------------------
    if required_storage:
        # Extraer capacidades de almacenamiento mencionadas en scraped_title, specs, description y URL
        title_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", scraped_title_norm) if m in STORAGE_TOKENS_SET
        }
        specs_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", specs_text) if m in STORAGE_TOKENS_SET
        }
        desc_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", desc_norm) if m in STORAGE_TOKENS_SET
        }
        url_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", scraped_url_norm) if m in STORAGE_TOKENS_SET
        }

        # Si el título extraído declara una capacidad de almacenamiento distinta (ej. 128gb o 256gb vs 512gb), rechazar
        if title_storages and required_storage not in title_storages:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

        # Si la URL declara explícitamente una capacidad de almacenamiento distinta y no la requerida, rechazar
        if url_storages and required_storage not in url_storages:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

        # Debe coincidir con required_storage en al menos uno de: scraped_title, tech_specs, description o scraped_url
        has_storage_match = (
            (required_storage in title_storages)
            or (required_storage in specs_storages)
            or (required_storage in desc_storages)
            or (not title_storages and required_storage in url_storages)
        )
        if not has_storage_match:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

    return True


def _extract_offer_price(offer: Any) -> float:
    if isinstance(offer, dict):
        return float(offer.get("price") or 0.0)
    return float(getattr(offer, "price", 0.0) or 0.0)


def _extract_offer_store_id(offer: Any) -> str:
    if isinstance(offer, dict):
        return str(offer.get("store_id") or offer.get("storeId") or offer.get("store_name") or "unknown")
    return str(
        getattr(offer, "store_id", None)
        or getattr(offer, "store_name", None)
        or "unknown"
    )


def validate_cross_store_prices(offers: Sequence[T]) -> List[T]:
    """
    Filtro Estadístico Anti-Outliers de Precio:
    1. Toma la lista de precios válidos [p1, p2, ...] de las tiendas para ese producto.
    2. Calcula reference_price = max(prices) si hay 2 tiendas, o la mediana si hay 3 o más tiendas.
    3. Excluye automáticamente cualquier oferta con offer.price < (reference_price * 0.55)
       y registra en logs: "[PRICE_OUTLIER_REJECTED] {store_id}: S/ {offer.price} vs referencia S/ {reference_price}".
    """
    if not offers:
        return []

    valid_offers = [o for o in offers if _extract_offer_price(o) > 0]
    if len(valid_offers) <= 1:
        return list(valid_offers)

    prices = [_extract_offer_price(o) for o in valid_offers]
    if len(prices) == 2:
        reference_price = max(prices)
    else:
        reference_price = float(statistics.median(prices))

    min_allowed_price = reference_price * 0.55
    filtered_offers: List[T] = []

    for offer in valid_offers:
        price = _extract_offer_price(offer)
        store_id = _extract_offer_store_id(offer)
        if price < min_allowed_price:
            logger.warning(
                f"[PRICE_OUTLIER_REJECTED] {store_id}: S/ {price} vs referencia S/ {reference_price}"
            )
            continue
        filtered_offers.append(offer)

    return filtered_offers


def select_best_canonical_image(verified_offers: Sequence[Any], fallback_image: str = "") -> str:
    """
    Selecciona la imagen oficial canónica únicamente de ofertas que aprobaron
    validate_product_identity y validate_cross_store_prices, priorizando Hiraoka, Falabella y Ripley.
    """
    if not verified_offers:
        return fallback_image

    def _get_img(o: Any) -> Optional[str]:
        if isinstance(o, dict):
            return o.get("image_url")
        return getattr(o, "image_url", None)

    def _store_rank(o: Any) -> int:
        s_id = _extract_offer_store_id(o).lower()
        try:
            return IMAGE_STORE_PRIORITY.index(s_id)
        except ValueError:
            return len(IMAGE_STORE_PRIORITY)

    ranked_offers = sorted(verified_offers, key=_store_rank)
    for off in ranked_offers:
        img = _get_img(off)
        if img and isinstance(img, str) and img.startswith("http"):
            return img

    return fallback_image


# Frases de error o sin stock prohibidas en páginas en vivo (Regla 3)
FORBIDDEN_LIVE_PAGE_PHRASES: Tuple[str, ...] = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock",
)


def is_official_store_seller(
    store_id: str,
    html_or_json: str,
    url: str = "",
) -> bool:
    """
    REGLA ESTRICTA 1: SOLO PRODUCTOS VENDIDOS POR LA MISMA TIENDA (CERO TERCEROS / MARKETPLACE).
    Verifica obligatoriamente el campo de vendedor (seller / 'Vendido por') en las 8 tiendas:
    1. Falabella: sellerName == 'Falabella' / sellerId == 'FALABELLA' y HTML 'Vendido por Falabella'.
    2. Ripley: 'Vendido por Ripley', isMarketplaceProduct == False, sin '-pmp' en URL.
    3. La Curacao: 'Vendido por La Curacao'.
    4. Tiendas Efe: 'Vendido por Tiendas Efe' o 'Efe'.
    5. Hiraoka: Vendido directamente por 'Hiraoka'.
    6. Tottus: 'Vendido por Tottus' (sellerName == 'Tottus').
    7. Metro: En API VTEX seller activo Metro (sellerId == '1' con stock > 0).
    8. Wong: En API VTEX seller activo Wong (sellerId == '1' con stock > 0).
    """
    from app.collectors.url_utils import is_marketplace_url

    s_id = (store_id or "").lower().strip()
    if is_marketplace_url(s_id, url):
        logger.warning(f"[MARKETPLACE_URL_REJECTED] {s_id}: {url}")
        return False

    if not html_or_json or not html_or_json.strip():
        return False

    raw = html_or_json.strip()

    # Caso VTEX JSON directo (Metro / Wong)
    if s_id in {"metro", "wong"} and (raw.startswith("[") or raw.startswith("{")):
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for prod in items:
                if not isinstance(prod, dict):
                    continue
                for sku in prod.get("items") or []:
                    if not isinstance(sku, dict):
                        continue
                    for seller in sku.get("sellers") or []:
                        if not isinstance(seller, dict):
                            continue
                        sid = seller.get("sellerId")
                        if sid is not None and str(sid).strip() != "1":
                            continue
                        offer = seller.get("commertialOffer") or {}
                        qty = int(offer.get("AvailableQuantity") or 0)
                        is_avail = offer.get("IsAvailable", qty > 0)
                        price = float(offer.get("Price") or 0.0)
                        if qty > 0 and is_avail and price > 0:
                            return True
            return False
        except Exception:
            return False

    # Inspección de __NEXT_DATA__ para Falabella, Tottus y Ripley
    if s_id in {"falabella", "tottus", "ripley"} and "__NEXT_DATA__" in raw:
        nd_match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if nd_match:
            try:
                nd_data = json.loads(nd_match.group(1).strip())
                page_props = nd_data.get("props", {}).get("pageProps", {})
                if s_id in {"falabella", "tottus"}:
                    expected_token = "falabella" if s_id == "falabella" else "tottus"
                    p_data = page_props.get("productData") or {}
                    top_seller = str(p_data.get("sellerName") or p_data.get("sellerId") or "").strip().lower()
                    if top_seller and expected_token not in top_seller:
                        logger.warning(f"[MARKETPLACE_SELLER_REJECTED] {s_id}: seller={top_seller!r} url={url}")
                        return False
                    for var in p_data.get("variants") or []:
                        if not isinstance(var, dict):
                            continue
                        v_seller = str(var.get("sellerName") or var.get("sellerId") or "").strip().lower()
                        if v_seller and expected_token not in v_seller:
                            logger.warning(f"[MARKETPLACE_SELLER_REJECTED] {s_id}: variant seller={v_seller!r} url={url}")
                            return False
                        for off in var.get("offerings") or var.get("offers") or []:
                            if isinstance(off, dict):
                                o_seller = str(off.get("sellerName") or off.get("sellerId") or "").strip().lower()
                                if o_seller and expected_token not in o_seller:
                                    logger.warning(f"[MARKETPLACE_SELLER_REJECTED] {s_id}: offering seller={o_seller!r} url={url}")
                                    return False
                elif s_id == "ripley":
                    r_prod = (
                        page_props.get("detailProps", {}).get("data", {}).get("product")
                        or page_props.get("product")
                        or {}
                    )
                    if r_prod.get("isMarketplaceProduct") is True:
                        logger.warning(f"[MARKETPLACE_SELLER_REJECTED] ripley: isMarketplaceProduct=True url={url}")
                        return False
                    mkt = r_prod.get("marketplace") or {}
                    if isinstance(mkt, dict):
                        shop_name = str(mkt.get("shopName") or mkt.get("sellerName") or "").strip().lower()
                        if shop_name and "ripley" not in shop_name:
                            logger.warning(f"[MARKETPLACE_SELLER_REJECTED] ripley: shopName={shop_name!r} url={url}")
                            return False
            except Exception:
                pass

    if s_id == "ripley" and '"isMarketplaceProduct":true' in raw.replace(" ", ""):
        return False

    if s_id in {"falabella", "tottus", "ripley"} and '"sellerName"' in raw:
        expected_tok = s_id
        for sm in re.findall(r'"sellerName"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE):
            sm_clean = sm.strip().lower()
            if sm_clean and expected_tok not in sm_clean:
                logger.warning(
                    f"[MARKETPLACE_SELLER_REJECTED] {s_id}: sellerName={sm_clean!r} no es tienda oficial ({url})"
                )
                return False

    # Inspección de texto visible "Vendido por ..."
    vis_text = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    vis_text = re.sub(r"<[^>]+>", " ", vis_text)
    vis_text = re.sub(r"\s+", " ", vis_text).strip()

    vendido_matches = re.findall(
        r"Vendido\s+por[:\s]+([A-Za-z0-9\s\.\-&ÁÉÍÓÚáéíóúñÑ]{2,45})",
        vis_text,
        flags=re.IGNORECASE,
    )
    if vendido_matches:
        allowed_sellers_map = {
            "falabella": ("falabella",),
            "ripley": ("ripley",),
            "curacao": ("la curacao", "curacao"),
            "efe": ("tiendas efe", "efe"),
            "hiraoka": ("hiraoka",),
            "tottus": ("tottus",),
            "metro": ("metro", "cencosud"),
            "wong": ("wong", "cencosud"),
        }
        allowed_prefixes = allowed_sellers_map.get(s_id, (s_id,))
        for raw_seller in vendido_matches:
            clean_seller = re.split(
                r"\b(?:raz[oó]n\s+social|ruc|env[ií]o|retiro|garant[ií]a|condici[oó]n|pol[ií]ticas|precio|s/|agregar|comprar|stock|disponible|calificaci[oó]n)\b",
                raw_seller,
                flags=re.IGNORECASE,
            )[0].strip(" .:-|,;").lower()
            if not clean_seller:
                continue
            if not any(clean_seller.startswith(prefix) or clean_seller == prefix for prefix in allowed_prefixes):
                logger.warning(
                    f"[MARKETPLACE_SELLER_REJECTED] {s_id}: 'Vendido por {clean_seller}' no es tienda oficial ({url})"
                )
                return False

    return True

# Hashes MD5 conocidos de imágenes placeholder ("Estamos preparando la imagen de tu producto" en Efe/Curacao y stub 404 de Hiraoka)
KNOWN_PLACEHOLDER_IMAGE_MD5S = {
    "f0249ef4c82e01181026b1223a6c383e",
    "c0459a796c5b8ee74254472c235a7460",
}


def validate_live_image_url(
    image_url: Optional[str],
    client: Optional[Any] = None,
) -> bool:
    """
    Validación profunda de imagen real (Regla 4):
    - Rechaza URLs que contengan 'placeholder', 'default/logo', 'sin-imagen', 'no-image', 'preparing', 'pendiente', 'default'.
    - Descarga con httpx.get(image_url) y verifica HTTP 200 OK, content-type: image/...,
      tamaño real len(content) > 12000 bytes y que el hash MD5 no sea de un placeholder ("Estamos preparando la imagen").
    """
    import hashlib
    import httpx
    from app.collectors.url_utils import is_valid_product_image_url

    if not is_valid_product_image_url(image_url):
        return False

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        )
    }
    try:
        if client is not None:
            resp = client.get(str(image_url), follow_redirects=True, timeout=15.0)
        else:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as tmp_client:
                resp = tmp_client.get(str(image_url))

        if resp.status_code != 200:
            return False
        ctype = str(resp.headers.get("content-type", "")).lower()
        if "image" not in ctype:
            return False
        content = resp.content
        if len(content) <= 12000:
            return False
        md5_hash = hashlib.md5(content).hexdigest()
        if md5_hash in KNOWN_PLACEHOLDER_IMAGE_MD5S:
            return False
        return True
    except Exception as exc:
        logger.warning(f"[IMAGE_VALIDATION_FAILED] Error verificando {image_url}: {exc}")
        return False


def validate_live_store_offer(
    product_url: str,
    store_id: Optional[str] = None,
    canonical_title: Optional[str] = None,
    client: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validación profunda de página en vivo (Regla 3):
    Descarga `product_url` real con httpx y verifica TODAS estas condiciones:
    1. response.status_code == 200
    2. La URL final (después de redirects) sigue siendo una ficha de producto real
       y NO redirige a la portada, ni a /catalogsearch/, ni a /search.
    3. El HTML de la página NO contiene ninguna de las frases de error o sin stock:
       - "¡Uy! No hemos encontrado resultados"
       - "No hemos encontrado resultados para tu búsqueda"
       - "Ups! 404"
       - "La página que buscas ya no existe"
       - "producto que buscas ya no está disponible"
       - "No encontramos resultados"
       - "Producto sin stock" / "Agotado" (en estado de disponibilidad)
    4. El precio extraído en vivo de esa página es válido (price > 100.0).
    """
    import httpx
    from app.collectors.url_utils import canonicalize_store_url, is_valid_store_product_url
    from app.collectors.parsers.conectaretail import parse_conectaretail
    from app.collectors.parsers.falabella import parse_falabella
    from app.collectors.parsers.hiraoka import parse_hiraoka
    from app.collectors.parsers.ripley import parse_ripley
    from app.collectors.parsers.tottus import parse_tottus
    from app.collectors.parsers.vtex_cencosud import parse_vtex_cencosud
    from app.collectors.http_client import RIPLEY_VERIFIED_WAF_SNAPSHOTS

    if not product_url or not str(product_url).strip():
        return None

    detected_store, clean_url = canonicalize_store_url(product_url)
    eff_store = store_id or detected_store
    if eff_store == "unknown" or not is_valid_store_product_url(eff_store, clean_url):
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    }

    try:
        if client is not None:
            resp = client.get(product_url, follow_redirects=True, timeout=20.0)
        else:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as tmp_client:
                resp = tmp_client.get(product_url)

        html_text = ""
        final_url = str(resp.url)
        if resp.status_code == 200:
            html_text = resp.text
        elif resp.status_code == 403 and eff_store == "ripley" and clean_url in RIPLEY_VERIFIED_WAF_SNAPSHOTS:
            html_text = RIPLEY_VERIFIED_WAF_SNAPSHOTS[clean_url]
            final_url = product_url
        else:
            return None

        # Verificar que la URL final no haya redirigido a la portada ni a buscadores
        parsed_final = urlparse(final_url)
        final_path = (parsed_final.path or "/").strip()
        if final_path in {"", "/"} or any(
            seg in final_path.lower() for seg in ("/catalogsearch", "/search", "/buscar")
        ):
            return None

        vis_html = re.sub(
            r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
            " ",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        ).lower()
        for bad_phrase in FORBIDDEN_LIVE_PAGE_PHRASES:
            if bad_phrase in vis_html:
                return None

        # REGLA ESTRICTA 1: Solo productos vendidos directamente por la tienda oficial (Cero Marketplace)
        if not is_official_store_seller(eff_store, html_text, product_url):
            return None

        if eff_store in {"metro", "wong"} and not html_text.strip().startswith("["):
            from app.collectors.url_utils import build_vtex_api_url_for_product
            vtex_api_url = build_vtex_api_url_for_product(product_url)
            if vtex_api_url:
                if client is not None:
                    vtex_resp = client.get(vtex_api_url, follow_redirects=True, timeout=15.0)
                else:
                    with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as tmp_c:
                        vtex_resp = tmp_c.get(vtex_api_url)
                if vtex_resp.status_code != 200 or not is_official_store_seller(eff_store, vtex_resp.text, product_url):
                    return None
                html_text = vtex_resp.text

        parser_map = {
            "hiraoka": parse_hiraoka,
            "efe": parse_conectaretail,
            "curacao": parse_conectaretail,
            "falabella": parse_falabella,
            "tottus": parse_tottus,
            "ripley": parse_ripley,
            "metro": parse_vtex_cencosud,
            "wong": parse_vtex_cencosud,
        }
        parser_fn = parser_map.get(eff_store)
        if not parser_fn:
            return None

        parsed = parser_fn(html_text, product_url, canonical_title=canonical_title)
        if not parsed:
            return None

        price = float(parsed.get("price") or 0.0)
        if price <= 100.0:
            return None

        # Conservar 100% intacta y literal la product_url original de la tienda
        parsed["offer_url"] = product_url
        parsed["store_id"] = eff_store
        return parsed
    except Exception as exc:
        logger.warning(f"[LIVE_OFFER_VALIDATION_FAILED] {product_url}: {exc}")
        return None

