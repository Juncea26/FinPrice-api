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
import re
import statistics
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from app.core.logging import get_logger

logger = get_logger("collectors.validators")

T = TypeVar("T")

# Palabras clave de accesorios que nunca deben contaminar un producto principal
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
    "fe",
    "lite",
    "mini",
    "fold",
    "flip",
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
    # Unificar '512 gb' -> '512gb', '1 tb' -> '1tb'
    normalized = re.sub(r"\b(\d+)\s+(gb|tb)\b", r"\1\2", no_accents)
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
    return bool(re.search(pattern, text))


def extract_critical_model_tokens(canonical_title: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    """
    Extrae del título canónico:
    1. Lista de tokens críticos de modelo, serie, gama y generación (ej. ['redmi', 'note', '15', 'pro'])
    2. Capacidad de almacenamiento principal (ej. '512gb')
    3. Capacidad de memoria RAM si se especifica (ej. '12gb')
    """
    norm = normalize_text(canonical_title)

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
    # 1. BLOQUEO DE ACCESORIOS E INTRUSOS
    # --------------------------------------------------------------------------
    for acc_kw in ACCESSORY_KEYWORDS:
        in_scraped = _has_whole_word(acc_kw, scraped_title_norm) or _has_whole_word(acc_kw, scraped_url_norm)
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

    primary_target = scraped_title_norm if scraped_title_norm else scraped_url_norm
    title_and_specs = f"{primary_target} {specs_text} {desc_norm}".strip()

    for token in critical_tokens:
        # Si existe scraped_title, los tokens de modelo/línea deben estar en scraped_title (o en tech_specs/description
        # para medidas de pantalla/resolución como '11', '13', '4k', 'evo'). Solo si scraped_title está vacío se usa scraped_url.
        is_screen_or_res_token = token in {"11", "13", "4k", "evo"}
        if is_screen_or_res_token:
            full_screen_corpus = f"{title_and_specs} {scraped_url_norm}".strip()
            found_token = _has_whole_word(token, full_screen_corpus)
            if not found_token and token == "11":
                found_token = _has_whole_word("10.9", full_screen_corpus) or _has_whole_word("10.8", full_screen_corpus)
            elif not found_token and token == "13":
                found_token = _has_whole_word("13.3", full_screen_corpus) or _has_whole_word("13.6", full_screen_corpus)
        else:
            found_token = _has_whole_word(token, primary_target)
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
