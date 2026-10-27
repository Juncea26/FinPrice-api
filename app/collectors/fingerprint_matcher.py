"""
Motor de Búsqueda Compacta + Verificación por Huella Técnica (fingerprint_matcher.py).
Separa las palabras de marketing de la Huella Técnica Obligatoria (ProductFingerprint)
para garantizar:
- CERO Falsos Negativos: Encuentra el mismo producto exacto aunque varíe la redacción comercial.
- CERO Falsos Positivos: Jamás mezcla tamaños de pantalla (55" vs 42"/65"/77"), modelos (C6 vs B6/G6,
  Note 15 Pro 5G vs Redmi A7 o Note 15 Pro 4G), ni capacidades (512GB/12GB vs 256GB/8GB).
"""
import asyncio
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.collectors.url_utils import (
    CANONICAL_HOSTS,
    build_store_search_url,
    canonicalize_store_url,
)
from app.collectors.validators import ACCESSORY_KEYWORDS

logger = get_logger("collectors.fingerprint_matcher")

ALL_8_STORE_IDS: Tuple[str, ...] = (
    "falabella",
    "ripley",
    "efe",
    "curacao",
    "hiraoka",
    "tottus",
    "metro",
    "wong",
)

# Palabras de marketing/relleno que varían entre tiendas y deben ignorarse al construir queries
MARKETING_STOPWORDS: Set[str] = {
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
    "dolby",
    "atmos",
    "vision",
    "smart",
    "tv",
    "uhd",
    "ai",
    "thinq",
    "televisor",
    "celular",
    "libre",
    "smartphone",
    "laptop",
    "tablet",
    "pulgadas",
    "disco",
    "solido",
    "ssd",
    "ram",
    "memoria",
    "interna",
    "wi",
    "fi",
    "wifi",
    "color",
    "gris",
    "negro",
    "blanco",
    "azul",
    "cielo",
    "plateado",
    "silver",
    "black",
    "white",
    "blue",
    "brown",
    "cafe",
    "moca",
    "titanio",
    "titanium",
    "gray",
    "2024",
    "2025",
    "2026",
    "chip",
}

# Equivalencias de marca implícita por línea exclusiva de producto
IMPLIED_BRAND_TOKENS: Dict[str, Set[str]] = {
    "apple": {"apple", "iphone", "ipad", "macbook"},
    "xiaomi": {"xiaomi", "redmi", "poco"},
    "samsung": {"samsung", "galaxy"},
    "lg": {"lg", "oled42", "oled48", "oled55", "oled65", "oled77", "oled83"},
}

# Tamaños de pantalla estándar en TVs que son mutuamente excluyentes
TV_SCREEN_SIZES: Set[int] = {32, 40, 42, 43, 48, 50, 55, 58, 60, 65, 70, 75, 77, 83, 85, 86, 98}

# Capacidades de almacenamiento estándar en GB
STANDARD_STORAGE_GB: Set[int] = {32, 64, 128, 256, 512, 1024, 2048}

# Capacidades de RAM estándar en GB
STANDARD_RAM_GB: Set[int] = {2, 3, 4, 6, 8, 12, 16, 24, 32, 36, 48, 64}


class ProductFingerprint(BaseModel):
    """Huella Técnica Obligatoria de un producto para validación determinista en las 8 tiendas."""

    brand: str = Field(..., description="Marca obligatoria en minúsculas (ej. 'lg', 'samsung', 'xiaomi', 'apple')")
    family_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens de línea y modelo obligatorios (ej. ['oled', 'c6'], ['redmi', 'note', '15', 'pro'])",
    )
    screen_inches: Optional[int] = Field(
        default=None,
        description="Pulgadas exactas cuando aplique (ej. 55 para TV 55\", 11 para iPad 11\")",
    )
    storage_gb: Optional[int] = Field(
        default=None,
        description="Capacidad de almacenamiento exacta en GB (ej. 128, 256, 512)",
    )
    ram_gb: Optional[int] = Field(
        default=None,
        description="Memoria RAM exacta en GB cuando sea diferenciadora del SKU (ej. 8, 12, 16)",
    )
    network: Optional[str] = Field(
        default=None,
        description="'5g' si el producto canónico exige conectividad 5G",
    )
    forbidden_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens de modelos o variantes distintas que deben bloquearse inmediatamente",
    )


def _normalize_for_fingerprint(text: str) -> str:
    """
    Normaliza un texto o slug a minúsculas sin tildes y separa códigos compuestos de retail
    (como 'oled55c6psaotb' -> 'oled 55 c6 psaotb', 'note15pro' -> 'note 15 pro', '12+512gb' -> '12gb 512gb').
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"\.(html?|php|aspx?)\b", " ", no_accents)
    cleaned = re.sub(r"[/\-_\.+%=&?,:;()\[\]\"']+", " ", cleaned)

    # Expandir patrones '12+512gb' o '8/256gb' cuando estaban juntos en el texto original
    combo_matches = re.findall(
        r"\b(\d{1,2})\s*(?:gb|g)?\s*[+/]\s*(\d{2,4})\s*(?:gb|g)?\b", no_accents
    )
    extra_tokens: List[str] = []
    for r_val, s_val in combo_matches:
        extra_tokens.append(f"{r_val}gb")
        extra_tokens.append(f"{s_val}gb")

    # Expandir '8g ram 256g rom' -> '8gb ram 256gb rom'
    cleaned = re.sub(r"\b(\d{1,4})\s*g\b(?=\s*(?:ram|rom|blue|black|green|white|gray))", r"\1gb", cleaned)
    cleaned = re.sub(r"\b(\d{1,4})\s+(gb|tb)\b", r"\1\2", cleaned)

    # Expandir códigos de modelo de TVs LG/Samsung pegados: ej. 'oled55c6psa' -> 'oled 55 c6 psa', 'oled77g6psa' -> 'oled 77 g6 psa'
    cleaned = re.sub(
        r"\b(oled|qned|nanocell)(\d{2})([bcgmrwz]\d)([a-z0-9]*)\b",
        r"\1 \2 \3 \4",
        cleaned,
    )
    # Expandir 'note15pro5g' / 'note15pro' / 'a7pro'
    cleaned = re.sub(r"\b(note)(\d+)(pro)?(5g)?\b", r"\1 \2 \3 \4", cleaned)
    cleaned = re.sub(r"\b([a-z]\d+)(pro|plus|ultra|max|fe|lite)\b", r"\1 \2", cleaned)
    cleaned = re.sub(r"\b(\d+)(pro|plus|ultra|max|fe|lite)(5g)?\b", r"\1 \2 \3", cleaned)

    if extra_tokens:
        cleaned = f"{cleaned} {' '.join(extra_tokens)}"

    return re.sub(r"\s+", " ", cleaned).strip()


def _has_word(token: str, normalized_text: str) -> bool:
    if not token or not normalized_text:
        return False
    return bool(re.search(rf"\b{re.escape(token.lower())}\b", normalized_text))


def build_compact_search_query(fingerprint: ProductFingerprint) -> str:
    """
    Construye una query de búsqueda compacta usando SOLO la huella técnica:
    '{brand} {family_tokens} {screen_inches or storage_gb}'
    Ejemplos:
      - 'LG OLED 55 C6'
      - 'Samsung Galaxy Tab S10 FE 128GB'
      - 'Xiaomi Redmi Note 15 Pro 5G 512GB'
    """
    parts: List[str] = []
    if fingerprint.brand:
        parts.append(fingerprint.brand.upper() if len(fingerprint.brand) <= 3 else fingerprint.brand.title())

    for tok in fingerprint.family_tokens:
        if tok.lower() != fingerprint.brand.lower():
            if tok.lower() in {"oled", "qled", "fe", "5g"} or re.match(r"^[a-z]\d+$", tok.lower()):
                parts.append(tok.upper())
            else:
                parts.append(tok.title())

    if fingerprint.screen_inches and str(fingerprint.screen_inches) not in parts:
        # En TVs (ej. LG OLED 55 C6), colocar las pulgadas junto a OLED/modelo
        if "OLED" in parts and len(parts) >= 3:
            oled_idx = parts.index("OLED") + 1
            parts.insert(oled_idx, str(fingerprint.screen_inches))
        else:
            parts.append(str(fingerprint.screen_inches))

    if fingerprint.network and fingerprint.network.upper() not in parts:
        parts.append(fingerprint.network.upper())

    if fingerprint.storage_gb:
        cap_str = "1TB" if fingerprint.storage_gb == 1024 else f"{fingerprint.storage_gb}GB"
        if cap_str not in parts:
            parts.append(cap_str)

    return " ".join(parts)


def matches_fingerprint(
    fingerprint: ProductFingerprint,
    candidate_title: str,
    candidate_specs: Optional[Dict[str, str]] = None,
    candidate_url: str = "",
) -> bool:
    """
    Evalúa determinísticamente si un producto candidato cumple el 100% de la Huella Técnica:
    1. Sin palabras de accesorios ni forbidden_tokens.
    2. Misma marca (brand).
    3. Todos los family_tokens presentes.
    4. Mismas pulgadas exactas (screen_inches) sin tamaños conflictivos (ej. 55" vs 42"/65"/77").
    5. Mismo almacenamiento exacto (storage_gb) y RAM exacta (ram_gb) cuando apliquen.
    6. Misma red móvil (network='5g') cuando el producto canónico es 5G.
    """
    title_norm = _normalize_for_fingerprint(candidate_title)
    url_norm = _normalize_for_fingerprint(candidate_url)
    specs_text = ""
    if candidate_specs and isinstance(candidate_specs, dict):
        specs_text = _normalize_for_fingerprint(
            " ".join(f"{k} {v}" for k, v in candidate_specs.items())
        )

    combined_text = f"{title_norm} {specs_text} {url_norm}".strip()
    primary_text = title_norm if title_norm else url_norm
    if not primary_text:
        return False

    # 1. Bloqueo de accesorios y tokens prohibidos (forbidden_tokens)
    for acc in ACCESSORY_KEYWORDS:
        if _has_word(acc, title_norm) or _has_word(acc, url_norm):
            return False

    for forbidden in fingerprint.forbidden_tokens:
        f_clean = forbidden.lower().strip()
        if _has_word(f_clean, title_norm) or _has_word(f_clean, url_norm):
            return False

    # 2. Verificación de Marca (brand)
    brand_low = fingerprint.brand.lower().strip()
    allowed_brand_aliases = IMPLIED_BRAND_TOKENS.get(brand_low, {brand_low})
    if not any(_has_word(alias, combined_text) for alias in allowed_brand_aliases):
        return False

    # 3. Verificación de todos los family_tokens
    for f_tok in fingerprint.family_tokens:
        tok_low = f_tok.lower().strip()
        if not (_has_word(tok_low, primary_text) or _has_word(tok_low, specs_text)):
            return False

    # Bloquear sufijos de otra gama cuando no están en family_tokens
    family_set = {t.lower().strip() for t in fingerprint.family_tokens}
    for strict_suffix in ("pro", "ultra", "fe", "lite", "mini", "fold", "flip"):
        if strict_suffix not in family_set and _has_word(strict_suffix, title_norm):
            return False

    # 4. Verificación estricta de Pulgadas (screen_inches)
    if fingerprint.screen_inches is not None:
        req_inches = int(fingerprint.screen_inches)
        if not _has_word(str(req_inches), combined_text):
            return False

        # Regla crítica: un TV de 55" jamás puede emparejarse con el mismo modelo en 42", 48", 65" o 77"
        if req_inches in TV_SCREEN_SIZES:
            other_tv_sizes = TV_SCREEN_SIZES - {req_inches}
            for other_sz in other_tv_sizes:
                # Si otro tamaño de TV aparece en el título o URL (ej. 42, 48, 65, 77, 83)
                if _has_word(str(other_sz), title_norm) or _has_word(str(other_sz), url_norm):
                    return False

    # 5. Verificación estricta de Almacenamiento (storage_gb)
    if fingerprint.storage_gb is not None:
        req_stor = int(fingerprint.storage_gb)
        req_stor_tokens = (
            {"1024gb", "1tb"} if req_stor == 1024 else {f"{req_stor}gb"}
        )

        # Extraer todos los tokens de almacenamiento mencionados en título, specs y URL
        found_storages_title = {
            m
            for m in re.findall(r"\b(\d+(?:gb|tb))\b", title_norm)
            if m in {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}
        }
        found_storages_url = {
            m
            for m in re.findall(r"\b(\d+(?:gb|tb))\b", url_norm)
            if m in {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}
        }
        found_storages_specs = {
            m
            for m in re.findall(r"\b(\d+(?:gb|tb))\b", specs_text)
            if m in {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}
        }

        if found_storages_title and not (found_storages_title & req_stor_tokens):
            return False
        if found_storages_url and not (found_storages_url & req_stor_tokens):
            return False

        all_found_storages = found_storages_title | found_storages_url | found_storages_specs
        if not (all_found_storages & req_stor_tokens):
            return False

    # 6. Verificación estricta de Memoria RAM (ram_gb) cuando el SKU la exige
    if fingerprint.ram_gb is not None:
        req_ram_tok = f"{int(fingerprint.ram_gb)}gb"
        ram_tokens_set = {f"{r}gb" for r in STANDARD_RAM_GB if r < 64}

        found_rams_title = {
            m for m in re.findall(r"\b(\d+gb)\b", title_norm) if m in ram_tokens_set
        }
        found_rams_url = {
            m for m in re.findall(r"\b(\d+gb)\b", url_norm) if m in ram_tokens_set
        }
        found_rams_specs = {
            m for m in re.findall(r"\b(\d+gb)\b", specs_text) if m in ram_tokens_set
        }

        # Si el candidato declara explícitamente otra RAM (ej. 8GB o 4GB cuando se exige 12GB), rechazar
        if found_rams_title and req_ram_tok not in found_rams_title:
            return False
        if found_rams_url and req_ram_tok not in found_rams_url:
            return False
        if found_rams_specs and req_ram_tok not in found_rams_specs:
            return False

    # 7. Verificación de Red (network='5g')
    if fingerprint.network and fingerprint.network.lower() == "5g":
        # Si el candidato indica explícitamente 4G y no 5G, o no menciona 5G en título/URL/specs
        if _has_word("4g", title_norm) and not _has_word("5g", title_norm):
            return False
        if not _has_word("5g", combined_text):
            return False

    return True


def build_fingerprint_from_catalog_item(item: Dict[str, Any]) -> ProductFingerprint:
    """Construye o recupera el ProductFingerprint oficial de un producto del catálogo."""
    if "fingerprint" in item and isinstance(item["fingerprint"], dict):
        return ProductFingerprint(**item["fingerprint"])
    if "fingerprint" in item and isinstance(item["fingerprint"], ProductFingerprint):
        return item["fingerprint"]

    title = str(item.get("title") or "")
    brand = str(item.get("brand") or "").lower().strip()
    norm = _normalize_for_fingerprint(title)

    # Inferir almacenamiento y RAM
    storage_gb: Optional[int] = None
    ram_gb: Optional[int] = None
    for num_s, unit_s in re.findall(r"\b(\d+)\s*(gb|tb)\b", norm):
        val = int(num_s) * (1024 if unit_s == "tb" else 1)
        if val >= 64 and storage_gb is None:
            storage_gb = val
        elif val < 64 and ram_gb is None:
            ram_gb = val

    network = "5g" if _has_word("5g", norm) else None

    # Inferir pulgadas si es TV, Laptop o Tablet
    screen_inches: Optional[int] = None
    inch_m = re.search(r"\b(\d{2})(?:\.\d)?\s*(?:pulgadas|\")\b", title, flags=re.IGNORECASE)
    if inch_m:
        screen_inches = int(inch_m.group(1))
    elif item.get("category") == "TVs":
        for sz in TV_SCREEN_SIZES:
            if _has_word(str(sz), norm):
                screen_inches = sz
                break

    # Extraer family_tokens excluyendo stopwords de marketing, marca, capacidades y pulgadas
    words = re.findall(r"\b[a-z0-9]+\b", norm)
    family_tokens: List[str] = []
    excluded = set(MARKETING_STOPWORDS) | {brand, "4k", "5g", "4g"}
    if storage_gb:
        excluded.add(f"{storage_gb}gb")
    if ram_gb:
        excluded.add(f"{ram_gb}gb")
    if screen_inches:
        excluded.add(str(screen_inches))

    for w in words:
        if w in excluded:
            continue
        if w not in family_tokens:
            family_tokens.append(w)

    return ProductFingerprint(
        brand=brand,
        family_tokens=family_tokens,
        screen_inches=screen_inches,
        storage_gb=storage_gb,
        ram_gb=ram_gb,
        network=network,
    )


async def discover_product_across_8_stores(
    fingerprint: ProductFingerprint,
    direct_store_urls: Optional[Dict[str, str]] = None,
    canonical_title: Optional[str] = None,
    tech_specs: Optional[Dict[str, Any]] = None,
    scrape_fn: Optional[Callable[..., Any]] = None,
    stores_to_check: Optional[Sequence[str]] = None,
    enable_live_search_discovery: bool = True,
) -> List[Dict[str, Any]]:
    """
    Evalúa concurrentemente las 8 tiendas del retail peruano
    (falabella, ripley, efe, curacao, hiraoka, tottus, metro, wong):
    - Si la tienda ya tiene una URL directa verificada en direct_store_urls, la usa directamente
      previa canonicalización con canonicalize_store_url.
    - Si no tiene URL directa y enable_live_search_discovery=True, ejecuta una búsqueda compacta
      basada en la Huella Técnica (build_compact_search_query) y evalúa el resultado con matches_fingerprint.
    - Si encuentra una coincidencia exacta al 100% con el ProductFingerprint, canonicaliza su URL,
      extrae su precio real y la incluye en la lista de ofertas verificadas.
    - Si ningún resultado cumple el 100% del ProductFingerprint (ej. cuando Tottus, Metro o Wong
      no tienen el modelo exacto LG OLED C6 55"), omite esa tienda limpiamente sin inventar links
      ni mezclar con otro modelo o tamaño.
    """
    from app.collectors.catalog_urls import STORES_INFO

    if scrape_fn is None:
        from app.collectors.orchestrator import orchestrator
        scrape_fn = orchestrator.scrape_store_url

    stores = list(stores_to_check) if stores_to_check is not None else list(ALL_8_STORE_IDS)
    direct_urls = direct_store_urls or {}
    compact_query = build_compact_search_query(fingerprint)
    effective_title = canonical_title or compact_query

    async def _evaluate_single_store(store_id: str) -> Optional[Dict[str, Any]]:
        has_direct_url = bool(store_id in direct_urls and direct_urls[store_id])
        if has_direct_url:
            _, target_url = canonicalize_store_url(direct_urls[store_id])
        elif enable_live_search_discovery:
            target_url = build_store_search_url(store_id, compact_query)
        else:
            return None

        if not target_url:
            return None

        try:
            res = await scrape_fn(
                store_id=store_id,
                url=target_url,
                canonical_title=effective_title,
                tech_specs=tech_specs,
            )
        except TypeError:
            # Soporte para funciones de scraping de prueba con firma simplificada (store_id, url)
            res = await scrape_fn(store_id, target_url)
        except Exception as e:
            logger.debug(f"Error consultando tienda '{store_id}' ({target_url}): {e}")
            return None

        if not isinstance(res, dict):
            return None

        price = res.get("price")
        if not price or float(price) <= 0:
            return None

        raw_offer_url = str(res.get("offer_url") or (target_url if has_direct_url else "")).strip()
        if not raw_offer_url:
            return None

        detected_store, clean_offer_url = canonicalize_store_url(raw_offer_url)
        if detected_store != "unknown" and detected_store != store_id:
            return None

        # Rechazar si el link devuelto sigue siendo una URL de búsqueda en lugar de una ficha de producto
        if any(
            marker in clean_offer_url
            for marker in ("/catalogsearch/result", "/api/catalog_system/", "?q=", "?ft=", "?s=")
        ):
            return None

        cand_title = str(res.get("title") or "").strip()
        cand_specs = res.get("tech_specs") if isinstance(res.get("tech_specs"), dict) else (tech_specs or {})

        if not matches_fingerprint(
            fingerprint=fingerprint,
            candidate_title=cand_title,
            candidate_specs=cand_specs,
            candidate_url=clean_offer_url,
        ):
            logger.info(
                f"[FINGERPRINT_REJECTED] Tienda '{store_id}' omitida: "
                f"candidato='{cand_title}' ({clean_offer_url}) no cumple huella {fingerprint.model_dump()}"
            )
            return None

        store_meta = STORES_INFO.get(store_id, {})
        return {
            "store_id": store_id,
            "store_name": res.get("store_name") or store_meta.get("name", store_id.title()),
            "title": cand_title or effective_title,
            "price": round(float(price), 2),
            "original_price": res.get("original_price"),
            "offer_url": clean_offer_url,
            "image_url": res.get("image_url"),
            "brand": res.get("brand"),
            "tech_specs": res.get("tech_specs") or {},
            "features": res.get("features") or [],
        }

    tasks = [_evaluate_single_store(s_id) for s_id in stores]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    verified_offers: List[Dict[str, Any]] = []
    for item in raw_results:
        if isinstance(item, dict) and item.get("price"):
            verified_offers.append(item)

    verified_offers.sort(key=lambda x: x["price"])
    return verified_offers

