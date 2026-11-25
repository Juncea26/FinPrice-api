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
from app.collectors.tech_normalizer import (
    DEFAULT_NEUTRAL_TOKENS,
    evaluate_strict_guardrails,
    expand_retail_abbreviations,
    extract_product_codes,
    has_exact_code_match,
    normalize_memory_and_storage,
    normalize_tech_text,
    strip_url_bundle_tail,
    validate_persisted_url_no_contradiction,
)

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
    "essential",
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
    "ryzen",
    "intel",
    "snapdragon",
    "rtx",
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
    "essential",
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
    """Convierte texto a minúsculas sin tildes, normaliza memoria/almacenamiento y expande abreviaturas retail."""
    if not text:
        return ""
    return normalize_tech_text(str(text), expand_abbrevs=True, strip_colors=False)


def normalize_url_slug(url: str) -> str:
    """Extrae y normaliza el slug de una URL convirtiendo separadores en espacios."""
    if not url:
        return ""
    parsed = urlparse(str(url))
    raw_path = f"{parsed.path} {parsed.query}"
    cleaned = re.sub(r"\.(html?|php|aspx?)\b", " ", raw_path, flags=re.IGNORECASE)
    norm = normalize_tech_text(cleaned, expand_abbrevs=True, strip_colors=False)
    norm = re.sub(r"\b(\d+gb|\d+tb)(ram|ssd)?\b", r"\1 \2", norm)
    norm = re.sub(r"\b(u\d{4})([a-z])\b", r"\1 \1\2", norm)
    norm = re.sub(r"\b(ux\d{4})([a-z]{1,2})\b", r"\1 \1\2 a14", norm)
    norm = re.sub(r"\b(tb336[a-z0-9]*)\b", r"\1 idea tab 11", norm)
    norm = re.sub(r"\b(fx607[a-z0-9]*)\b", r"\1 tuf f16", norm)
    norm = re.sub(r"\b(82xq[a-z0-9]*)\b", r"\1 ideapad slim 3", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    return strip_url_bundle_tail(norm)


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
    # Equivalencia Intel Core 5 / Core i5 (ej. Intel Core 5 210H <-> CI5 / C5)
    if token in {"3", "5", "7", "9"} and bool(re.search(rf"\bcore\s+i{re.escape(token)}\b", text)):
        return True
    if token in {"i3", "i5", "i7", "i9"} and bool(re.search(rf"\bcore\s+{re.escape(token[1:])}\b", text)):
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
    if token == "ryzen" and any(re.search(rf"\b{x}\b", text) for x in ["ryzen", "r5", "r7", "r9", "82xq"]):
        return True
    if token == "intel" and any(re.search(rf"\b{x}\b", text) for x in ["intel", "core", "i3", "i5", "i7", "i9", "c5", "ci5", "210h", "fx607", "83je"]):
        return True
    if token == "rtx" and ("rtx" in text or "fx607" in text or "83je" in text or "fb3049" in text):
        return True
    if token in {"u8000h", "u8000"} and "vision" in text and "ai" in text and "uhd" in text:
        return True
    return False


def extract_critical_model_tokens(canonical_title: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    """
    Extrae del título canónico (previa limpieza de colores con strip_color_tokens):
    1. Lista de tokens críticos de modelo, serie, gama y generación (ej. ['redmi', 'note', '15', 'pro'])
    2. Capacidad de almacenamiento principal (ej. '512gb', '1tb')
    3. Capacidad de memoria RAM si se especifica (ej. '12gb')
    """
    norm = normalize_tech_text(
        strip_color_tokens(normalize_memory_and_storage(canonical_title)),
        expand_abbrevs=True,
        strip_colors=True,
    )

    # 1. Extraer almacenamiento y RAM
    storage_match: Optional[str] = None
    ram_match: Optional[str] = None
    all_mem_tokens = re.findall(r"\b(\d+(?:gb|tb))\b", norm)
    for mem_tok in all_mem_tokens:
        if (mem_tok in STORAGE_TOKENS_SET or mem_tok.endswith("tb")) and storage_match is None:
            storage_match = "1tb" if mem_tok == "1024gb" else mem_tok
        elif mem_tok not in STORAGE_TOKENS_SET and ram_match is None:
            ram_match = mem_tok

    # 2. Extraer tokens críticos de familia, serie y gama en el orden en que aparecen
    critical_tokens: List[str] = []
    words = re.findall(r"\b[a-z0-9\.]+\b", norm)
    for w in words:
        if w in CRITICAL_MODEL_IDENTIFIERS and w not in DEFAULT_NEUTRAL_TOKENS and w not in critical_tokens:
            critical_tokens.append(w)

    # 3. Extraer números exactos de generación y códigos alfanuméricos de modelo
    cleaned_for_gen = re.sub(r"\b\d+(?:gb|tb|mb|mp|mah|hz|w)\b", " ", norm)
    cleaned_for_gen = re.sub(r"\b[45]g\b", " ", cleaned_for_gen)
    cleaned_for_gen = re.sub(r"\b\d+\.\d+\b", " ", cleaned_for_gen)

    gen_candidates = re.findall(r"\b[a-z]*\d+[a-z]*\b", cleaned_for_gen)
    ignored_numeric = {"2024", "2025", "2026", "2027", "360", "100"}
    for cand in gen_candidates:
        if cand in ignored_numeric or cand in DEFAULT_NEUTRAL_TOKENS:
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
    target_tech_specs: Optional[Dict[str, Any]] = None,
    candidate_html: str = "",
) -> bool:
    """
    Valida estrictamente que la oferta extraída corresponda al mismo producto canónico
    inspeccionando título, URL, tech_specs, description y códigos oficiales (EAN/GTIN/MPN).
    Elimina falsos [IDENTITY_MISMATCH] por espacios (12 GB RAM 512GB), omisión de 5G/Chip
    o abreviaturas retail, manteniendo estricto el rechazo de variantes distintas.
    """
    if not canonical_title:
        return False

    # Modo solo-contradicción explícita cuando solo se evalúa una URL persistida en BD (título vacío)
    if not (scraped_title or "").strip():
        is_ok = validate_persisted_url_no_contradiction(
            canonical_title=canonical_title,
            scraped_url=scraped_url,
            store_id=store_id,
            target_specs=target_tech_specs or tech_specs,
        )
        if not is_ok:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False
        return True

    bundle_pat = r"\s*(\+|\bcon\b|\bincluye\b)\s*(funda|case|folio|book\s*cover|cargador|audifonos?(?:\s+inalambricos?)?|mochila|mouse|cover|soundbar|maletin|teclado|lapiz|pen|stylus|combo|pack|tags?|regalo|hph|watch|buds)\b.*$"
    url_promo_pat = r"\b(funda|case|folio|cargador|audifonos?(?:\s+inalambricos?)?|mochila|mouse|cover|soundbar|maletin|teclado|lapiz|pen|combo|pack)(?:\s+\d+)?\s*$"
    filler_pat = r"\b(celular\s+libre|smartphone|disco\s+solido\s+de|unidad\s+de\s+estado\s+solido|liberado|dual\s+sim|teclado\s+en\s+(?:espanol|ingles))\b"

    raw_cand_no_bundle = re.sub(bundle_pat, "", scraped_title or "", flags=re.IGNORECASE).strip()
    canonical_norm = normalize_text(canonical_title)
    scraped_title_norm = normalize_text(raw_cand_no_bundle)
    scraped_url_norm = normalize_url_slug(scraped_url)

    clean_title_norm = re.sub(filler_pat, "", scraped_title_norm, flags=re.IGNORECASE).strip()
    clean_url_norm = re.sub(bundle_pat, "", scraped_url_norm, flags=re.IGNORECASE).strip()
    clean_url_norm = re.sub(url_promo_pat, "", clean_url_norm, flags=re.IGNORECASE).strip()
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
    # 0. EXTRACCIÓN DE CÓDIGOS OFICIALES (EAN/GTIN/MPN) Y GUARDRAILS ESTRICTOS
    # --------------------------------------------------------------------------
    target_codes = extract_product_codes(tech_specs=target_tech_specs, title=canonical_title)
    candidate_codes = extract_product_codes(
        html_or_json=candidate_html,
        tech_specs=tech_specs,
        title=scraped_title,
        url=scraped_url,
    )
    exact_code_matched = has_exact_code_match(target_codes, candidate_codes)

    if not evaluate_strict_guardrails(
        canonical_title=canonical_title,
        scraped_title=scraped_title,
        scraped_url=scraped_url,
        cand_specs=tech_specs,
        cand_description=description,
        target_specs=target_tech_specs,
        exact_code_matched=exact_code_matched,
    ):
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

    # Señal exacta por EAN / GTIN / MPN (tras pasar accesorios y guardrails estrictos)
    if exact_code_matched:
        return True

    # --------------------------------------------------------------------------
    # 2. COINCIDENCIA EXACTA DE FAMILIA, MODELO, GENERACIÓN Y SUFIJOS CRÍTICOS
    # --------------------------------------------------------------------------
    critical_tokens, required_storage, required_ram = extract_critical_model_tokens(canonical_title)

    primary_target = clean_title_norm if clean_title_norm else clean_url_norm
    title_and_specs = f"{primary_target} {specs_text} {desc_norm}".strip()
    hardware_or_chip_tokens = {
        "a14", "a15", "a16", "a17", "a18",
        "m1", "m2", "m3", "m4", "m5",
        "ryzen", "intel", "core", "i3", "i5", "i7", "i9",
        "snapdragon", "exynos", "dimensity",
        "rtx", "gtx", "3050", "4050", "4060", "5050", "210h", "7520u",
    }

    for token in critical_tokens:
        if token in DEFAULT_NEUTRAL_TOKENS:
            continue
        is_screen_or_res_token = token in {"8.7", "10.9", "11", "13", "14", "15", "16", "55", "65", "4k", "evo"}
        if is_screen_or_res_token:
            full_screen_corpus = f"{title_and_specs} {scraped_url_norm}".strip()
            found_token = _has_whole_word(token, full_screen_corpus)
            if not found_token and token == "11":
                found_token = _has_whole_word("10.9", full_screen_corpus) or _has_whole_word("10.8", full_screen_corpus)
            elif not found_token and token == "13":
                found_token = _has_whole_word("13.3", full_screen_corpus) or _has_whole_word("13.6", full_screen_corpus)
            elif not found_token and token in {"14", "15", "16"}:
                found_token = any(x in full_screen_corpus for x in [f"{token}.0", f"{token}.6", f"{token}f", "fx607", "fx507"])
        elif token in hardware_or_chip_tokens:
            # Permitir que chip/CPU/GPU se verifique tanto en título como en ficha técnica (tech_specs/URL)
            hw_corpus = f"{primary_target} {specs_text} {scraped_url_norm}".strip()
            found_token = _has_whole_word(token, hw_corpus)
            if not found_token and token == "x" and "snapdragon" in hw_corpus:
                found_token = True
        else:
            found_token = _has_whole_word(token, primary_target)
            if not found_token and len(token) >= 4 and _has_whole_word(token, scraped_url_norm):
                found_token = True
            if not found_token and token in {"pixma", "ecotank", "uhd", "vision", "tizen", "webos", "evo", "neo"}:
                found_token = True
            if not found_token and token == "oled55b6psa" and _has_whole_word("b6", primary_target):
                found_token = True
            if not found_token and not scraped_title_norm:
                found_token = _has_whole_word(token, f"{primary_target} {specs_text}")
                if not found_token and token == "plus" and _has_whole_word("pro", canonical_norm) and _has_whole_word("pro", scraped_url_norm):
                    found_token = True
                if not found_token and token == "galaxy" and ("sm a" in scraped_url_norm or "sm s" in scraped_url_norm or "sm x" in scraped_url_norm):
                    found_token = True
        if not found_token:
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

    # Bloquear cruce de arquitecturas de procesador en laptops (AMD Ryzen vs Intel Core)
    combined_cand_cpu = f"{clean_title_norm} {clean_url_norm} {specs_text}"
    if "ryzen" in canonical_norm or "amd" in canonical_norm:
        if any(re.search(rf"\b{x}\b", f"{clean_title_norm} {clean_url_norm}") for x in ["intel", "i3", "i5", "i7", "i9", "3i", "5i"]):
            return False
    elif "intel" in canonical_norm or any(re.search(rf"\b{x}\b", canonical_norm) for x in ["i3", "i5", "i7", "i9"]):
        if any(re.search(rf"\b{x}\b", f"{clean_title_norm} {clean_url_norm}") for x in ["ryzen", "amd"]):
            return False

    # Rechazo estricto bidireccional de sufijos de gama ('pro', 'ultra', 'plus', 'air', 'lite', 'fe', 'mini', 'essential')
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
        req_stor_set = {"1024gb", "1tb"} if required_storage in {"1024gb", "1tb"} else {required_storage}
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

        if title_storages and not (title_storages & req_stor_set):
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

        if url_storages and not (url_storages & req_stor_set):
            logger.warning(
                f"[IDENTITY_MISMATCH] Oferta descartada en {store_id}: "
                f"esperado='{canonical_title}', recibido='{scraped_title}' ({scraped_url})"
            )
            return False

        has_storage_match = (
            bool(req_stor_set & title_storages)
            or bool(req_stor_set & specs_storages)
            or bool(req_stor_set & desc_storages)
            or (not title_storages and bool(req_stor_set & url_storages))
            or (not scraped_title_norm and not specs_text and not desc_norm and not url_storages)
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


# Frases explícitas de sin stock o error 404 cuando la página responde HTTP 200 OK (Módulo 3)
EXPLICIT_OUT_OF_STOCK_PHRASES: Tuple[str, ...] = (
    "producto sin stock :(",
    "producto sin stock",
    "producto agotado",
    "sin stock disponible",
    "pronto disponible",
    "¡uy! no hemos encontrado resultados",
    "ups! 404",
)

# Frases de error o sin stock prohibidas en páginas en vivo (Regla 3)
FORBIDDEN_LIVE_PAGE_PHRASES: Tuple[str, ...] = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock :(",
    "producto sin stock",
    "producto agotado",
    "sin stock disponible",
    "pronto disponible",
)


def check_is_in_stock(
    store_id: str,
    html_or_json: str,
    status_code: int = 200,
    has_valid_price: bool = True,
) -> bool:
    """
    Política General Anti-Borrado de Tiendas (Módulo 3):
    - Si la petición devuelve un código temporal (403, 429, 500, 502, 503) o vacío por timeout,
      retorna True para retener la oferta existente sin borrarla ni desactivarla.
    - En tiendas Magento 2 (lacuracao.pe, efe.com.pe, hiraoka.com.pe), un producto está CON STOCK
      (in_stock = True) siempre que la página responda 200 OK, tenga un precio válido y tenga el botón
      "Agregar al carrito" / "Añadir al carro" (o no muestre un mensaje explícito de agotado).
    - Una oferta SOLO se marca sin stock (in_stock = False) cuando la página responde HTTP 200 OK
      y muestra explícitamente un mensaje de agotado:
      "Producto sin stock :(", "Producto sin stock", "Producto agotado", "Sin stock disponible",
      "¡Uy! No hemos encontrado resultados" o "Ups! 404".
    """
    if status_code in {403, 429, 500, 502, 503, 504} or not html_or_json:
        return True

    if status_code != 200:
        return False

    vis_html = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        html_or_json,
        flags=re.IGNORECASE | re.DOTALL,
    )
    vis_text = re.sub(r"<[^>]+>", " ", vis_html)
    vis_low = re.sub(r"\s+", " ", vis_text).strip().lower()

    for phrase in EXPLICIT_OUT_OF_STOCK_PHRASES:
        if phrase in vis_low:
            return False

    s_id = (store_id or "").lower().strip()
    if s_id in {"curacao", "efe", "hiraoka", "conectaretail"}:
        if not has_valid_price:
            return False
        raw_low = html_or_json.lower()
        has_cart_btn = any(
            marker in raw_low
            for marker in (
                "agregar al carrito",
                "añadir al carro",
                "anadir al carro",
                "agregar al carro",
                "product-addtocart-button",
                "instock",
                "in_stock",
            )
        )
        return True if (has_cart_btn or has_valid_price) else False

    return bool(has_valid_price)


def _is_falabella_group_node_official(node: Dict[str, Any], expected_token: str) -> Optional[bool]:
    """
    Evalúa los campos estructurados de vendedor en un nodo productData/item/variant de Falabella o Tottus.
    Retorna True si declara vendedor oficial, False si declara vendedor tercero, o None si no declara vendedor.
    """
    if not isinstance(node, dict):
        return None
    if node.get("isMarketplace") is True:
        return False

    direct_sellers: List[str] = []
    for key in ("sellerName", "sellerId"):
        val = node.get(key)
        if val is not None and str(val).strip():
            direct_sellers.append(str(val).strip().lower())
    seller_obj = node.get("seller")
    if isinstance(seller_obj, dict):
        for key in ("name", "sellerName", "id", "sellerId"):
            val = seller_obj.get(key)
            if val is not None and str(val).strip():
                direct_sellers.append(str(val).strip().lower())
    elif isinstance(seller_obj, str) and seller_obj.strip():
        direct_sellers.append(seller_obj.strip().lower())

    if direct_sellers:
        return any(expected_token in s for s in direct_sellers)
    return None


def _is_ripley_item_official_struct(node: Dict[str, Any]) -> bool:
    """Evalúa si un nodo producto/resultado de Ripley en __NEXT_DATA__ es 1P oficial de Ripley."""
    if not isinstance(node, dict):
        return True
    if node.get("isMarketplaceProduct") is True:
        return False
    part_id = str(
        node.get("partNumber") or node.get("parentProductID") or node.get("sku") or ""
    ).strip().upper()
    if part_id.startswith("PMP"):
        return False

    seller_val = str(node.get("seller") or node.get("sellerName") or "").strip().lower()
    if seller_val and ("marketplace" in seller_val or "ripley" not in seller_val):
        return False

    mkt = node.get("marketplace")
    if isinstance(mkt, dict):
        shop_name = str(mkt.get("shopName") or mkt.get("sellerName") or "").strip().lower()
        if shop_name and "ripley" not in shop_name and "ecsa" not in shop_name:
            return False

    shop = node.get("shop")
    if isinstance(shop, dict) and not seller_val:
        shop_seller_id = str(shop.get("sellerId") or shop.get("id") or "").strip()
        shop_name = str(shop.get("shopName") or "").strip().lower()
        if shop_seller_id not in {"", "1"} and "ripley" not in shop_name and "ecsa" not in shop_name:
            return False

    return True


_SIDEBAR_FILTER_SELLER_PREFIXES: Tuple[str, ...] = (
    "ordenar por",
    "relevancia",
    "menor precio",
    "mayor precio",
    "color",
    "capacidad",
    "camara",
    "cámara",
    "conectividad",
    "procesador",
    "memoria",
    "almacenamiento",
    "pantalla",
    "resolucion",
    "resolución",
    "sistema operativo",
    "tipo de",
    "filtrar",
    "filtros",
    "precio",
    "marca",
    "categoria",
    "categoría",
    "tamano",
    "tamaño",
)


def _strip_layout_and_filter_blocks(raw_html: str) -> str:
    """Elimina scripts, sidebars, nav, header, footer y facetas de filtro antes de analizar 'Vendido por ...'."""
    cleaned = re.sub(
        r"<(script|style|noscript|template|aside|nav|header|footer)\b[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<(div|section|ul|form)\b[^>]*(?:class|id)=[\"'][^\"']*"
        r"(?:facet|filter|sidebar|refinement|sort-by|layered-filter)[^\"']*[\"'][^>]*>.*?</\1>",
        " ",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned


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
    u_low = (url or "").lower()
    is_search_url = any(
        seg in u_low for seg in ("/search", "/buscar", "/catalogsearch/", "ntt=", "?q=", "&q=", "?ft=")
    )

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

    # Inspección estructurada de __NEXT_DATA__ para Falabella, Tottus y Ripley
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
                    p_data = page_props.get("productData") or page_props.get("product") or {}
                    search_results = page_props.get("results")

                    if isinstance(search_results, list) and not p_data:
                        if not search_results:
                            return True
                        has_official_or_unknown = False
                        for item in search_results:
                            if not isinstance(item, dict):
                                continue
                            item_res = _is_falabella_group_node_official(item, expected_token)
                            if item_res is not False:
                                has_official_or_unknown = True
                                break
                        if not has_official_or_unknown:
                            logger.warning(
                                f"[MARKETPLACE_SELLER_REJECTED] {s_id}: todos los resultados son de terceros ({url})"
                            )
                            return False
                        return True

                    if isinstance(p_data, dict) and p_data:
                        top_check = _is_falabella_group_node_official(p_data, expected_token)
                        if top_check is False:
                            top_seller = str(p_data.get("sellerName") or p_data.get("sellerId") or "").strip().lower()
                            logger.warning(f"[MARKETPLACE_SELLER_REJECTED] {s_id}: seller={top_seller!r} url={url}")
                            return False

                        var_checks: List[Optional[bool]] = []
                        for var in p_data.get("variants") or []:
                            if not isinstance(var, dict):
                                continue
                            v_check = _is_falabella_group_node_official(var, expected_token)
                            if v_check is not None:
                                var_checks.append(v_check)
                            for off in var.get("offerings") or var.get("offers") or []:
                                if isinstance(off, dict):
                                    o_check = _is_falabella_group_node_official(off, expected_token)
                                    if o_check is not None:
                                        var_checks.append(o_check)

                        if var_checks:
                            if any(vc is True for vc in var_checks):
                                return True
                            logger.warning(
                                f"[MARKETPLACE_SELLER_REJECTED] {s_id}: ninguna variante/offering pertenece a {expected_token} ({url})"
                            )
                            return False
                        if top_check is True:
                            return True

                elif s_id == "ripley":
                    r_prod = (
                        page_props.get("detailProps", {}).get("data", {}).get("product")
                        or page_props.get("product")
                        or {}
                    )
                    findability_prods = (
                        (page_props.get("findabilityProps") or {}).get("data") or {}
                    ).get("products")

                    if isinstance(findability_prods, list) and not r_prod:
                        if not findability_prods:
                            return True
                        if any(
                            isinstance(it, dict) and _is_ripley_item_official_struct(it)
                            for it in findability_prods
                        ):
                            return True
                        logger.warning(
                            f"[MARKETPLACE_SELLER_REJECTED] ripley: todos los resultados de búsqueda son marketplace ({url})"
                        )
                        return False

                    if isinstance(r_prod, dict) and r_prod:
                        if not _is_ripley_item_official_struct(r_prod):
                            logger.warning(f"[MARKETPLACE_SELLER_REJECTED] ripley: producto marketplace en PDP url={url}")
                            return False
                        has_pdp_struct = bool(
                            r_prod.get("name")
                            or r_prod.get("partNumber")
                            or r_prod.get("SKUs")
                            or r_prod.get("parentpricestock")
                        )
                        if has_pdp_struct:
                            # Confirmar también que no exista un "Vendido por <tercero>" en el buybox principal
                            stripped_pdp = _strip_layout_and_filter_blocks(raw)
                            vis_pdp = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped_pdp)).strip()
                            for vm in re.findall(
                                r"Vendido\s+por[:\s]+([A-Za-z0-9\s\.\-&ÁÉÍÓÚáéíóúñÑ]{2,45})",
                                vis_pdp,
                                flags=re.IGNORECASE,
                            ):
                                c_sel = re.split(
                                    r"\b(?:raz[oó]n\s+social|ruc|env[ií]o|retiro|garant[ií]a|condici[oó]n|pol[ií]ticas|precio|s/|agregar|comprar|stock|disponible|calificaci[oó]n)\b",
                                    vm,
                                    flags=re.IGNORECASE,
                                )[0].strip(" .:-|,;").lower()
                                if (
                                    c_sel
                                    and not any(c_sel.startswith(p) for p in _SIDEBAR_FILTER_SELLER_PREFIXES)
                                    and not re.match(r"^(?:marketplace\s+\d+\b|ripley\s+\d+\b)", c_sel)
                                    and not c_sel.startswith("ripley")
                                ):
                                    logger.warning(
                                        f"[MARKETPLACE_SELLER_REJECTED] ripley: 'Vendido por {c_sel}' no es tienda oficial ({url})"
                                    )
                                    return False
                            return True
            except Exception:
                pass

    if s_id == "ripley" and '"isMarketplaceProduct":true' in raw.replace(" ", ""):
        return False

    if not is_search_url and s_id in {"falabella", "tottus", "ripley"} and '"sellerName"' in raw:
        expected_tok = s_id
        for sm in re.findall(r'"sellerName"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE):
            sm_clean = sm.strip().lower()
            if sm_clean and expected_tok not in sm_clean:
                logger.warning(
                    f"[MARKETPLACE_SELLER_REJECTED] {s_id}: sellerName={sm_clean!r} no es tienda oficial ({url})"
                )
                return False

    # Inspección de texto visible "Vendido por ..." (excluyendo nav/aside/footer/facetas/filtros)
    vis_html = _strip_layout_and_filter_blocks(raw)
    vis_text = re.sub(r"<[^>]+>", " ", vis_html)
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
            if any(clean_seller.startswith(prefix) for prefix in _SIDEBAR_FILTER_SELLER_PREFIXES):
                continue
            if re.match(r"^(?:marketplace\s+\d+\b|ripley\s+\d+\b)", clean_seller):
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

