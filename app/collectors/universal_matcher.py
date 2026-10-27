"""
Validador Universal sobre el Corpus Completo y Resolvedor Multi-Tienda (universal_matcher.py).
Implementa:
1. match_product_universal(target_product, candidate_page_data) -> bool
   Evalúa el Corpus Completo del Candidato:
   full_corpus = f"{candidate.title} {candidate.url} {json.dumps(candidate.tech_specs, ensure_ascii=False)} {candidate.description}".lower()
   aplicando las 6 reglas universales (colores ignorados, modelo/chip exacto sin sub-modelos intrusos,
   almacenamiento en corpus completo, pulgadas con tolerancia comercial en tablets/laptops y exactitud en TVs,
   conectividad Wi-Fi vs Cellular/5G y 5G vs 4G).
2. filter_offers_by_price_sanity(offers) -> List[Dict[str, Any]]
   Filtro estadístico de cordura de precio (0.55 <= price / median_price <= 1.65).
3. UniversalProductResolver
   Motor asíncrono que resuelve cualquier producto en las 8 tiendas del retail peruano
   usando consultas en cascada (specific_query -> broad_model_query), resolución de variantes
   multi-SKU y validación sobre el corpus completo.
"""
import asyncio
import json
import re
import statistics
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.core.logging import get_logger
from app.collectors.color_stripper import strip_color_tokens
from app.collectors.query_builder import (
    FORBIDDEN_QUERY_COLORS,
    FORBIDDEN_QUERY_MARKETING_WORDS,
    SUBBRAND_LINE_TO_PARENT_BRAND,
    TV_SCREEN_INCHES,
    VALID_RAM_GB,
    VALID_STORAGE_GB,
    build_search_queries,
)
from app.collectors.url_utils import (
    build_store_search_url,
    canonicalize_store_url,
)

logger = get_logger("collectors.universal_matcher")

ALL_8_PERU_STORES: Tuple[str, ...] = (
    "falabella",
    "tottus",
    "ripley",
    "efe",
    "curacao",
    "hiraoka",
    "metro",
    "wong",
)

# Palabras de accesorios y reacondicionados que deben bloquearse cuando el producto objetivo es nuevo
UNIVERSAL_ACCESSORY_KEYWORDS: Tuple[str, ...] = (
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
    "keyboard",
    "trackpad",
    "folio",
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

# Sufijos de gama/sub-modelo mutuamente excluyentes
STRICT_SUBMODEL_TIERS: Tuple[str, ...] = (
    "pro",
    "air",
    "mini",
    "max",
    "ultra",
    "plus",
    "fe",
    "lite",
    "fold",
    "flip",
    "neo",
    "16e",
    "15e",
)

# Grupos de equivalencia comercial de pulgadas en Tablets y Laptops
COMMERCIAL_SCREEN_EQUIVALENTS: List[Set[str]] = [
    {"10.8", "10.9", "11", "11.0"},
    {"13", "13.0", "13.3", "13.6"},
    {"15", "15.0", "15.3", "15.6"},
]

# Tamaños de pantalla de Tablets/Laptops competidores (para rechazar iPad 13" cuando se busca 11", o MacBook 15" cuando se busca 13.6")
CONFLICTING_TABLET_LAPTOP_SIZES: Set[str] = {
    "8.3", "8.7", "10.9", "11", "12.4", "12.9", "13", "13.3", "13.6", "14", "15", "15.3", "15.6", "16", "17"
}


def _normalize_corpus_text(text: str) -> str:
    """
    Normaliza texto eliminando tildes, expandiendo códigos de modelo compuestos de retail
    (ej. 'oled55c6psaotb' -> 'oled 55 c6 psaotb', 'note15pro' -> 'note 15 pro', '128gb' <-> '128 gb')
    y convirtiendo puntuación en espacios.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"\.(html?|php|aspx?)\b", " ", no_accents)

    # Conservar decimales de pulgadas temporalmente antes de limpiar signos de puntuación
    cleaned = re.sub(r"(\d{1,2})\.(\d)\b", r"\1_DEC_\2", cleaned)
    cleaned = re.sub(r"[/\-_\.+%=&?,:;()\[\]\"'{}]+", " ", cleaned)
    cleaned = cleaned.replace(" DEC ", ".")

    # Expandir códigos de TVs LG/Samsung pegados: 'oled55c6psaotb' -> 'oled 55 c6 psaotb'
    cleaned = re.sub(
        r"\b(oled|qned|nanocell)(\d{2})([bcgmrwz]\d)([a-z0-9]*)\b",
        r"\1 \2 \3 \4",
        cleaned,
    )
    # Expandir 'note15pro5g' / 'a7pro' / 'magic8lite'
    cleaned = re.sub(r"\b(note|magic)(\d+)(pro|lite|ultra|plus)?(5g)?\b", r"\1 \2 \3 \4", cleaned)
    cleaned = re.sub(r"\b([a-z]\d+)(pro|plus|ultra|max|fe|lite)\b", r"\1 \2", cleaned)
    cleaned = re.sub(r"\b(\d+)(pro|plus|ultra|max|fe|lite)(5g)?\b", r"\1 \2 \3", cleaned)
    cleaned = re.sub(r"\b(\d{1,4})\s+(gb|tb)\b", r"\1\2", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _has_word(token: str, normalized_text: str) -> bool:
    if not token or not normalized_text:
        return False
    return bool(re.search(rf"\b{re.escape(token.lower())}\b", normalized_text))


def _extract_target_profile(target_product: Any) -> Dict[str, Any]:
    """
    Extrae el perfil técnico normalizado de cualquier producto objetivo
    (sea un dict de CATALOG_PRODUCTS, un ProductEntity o un string de título).
    """
    if isinstance(target_product, str):
        title = target_product
        category = ""
        brand = ""
        tech_specs: Dict[str, Any] = {}
        fp_dict: Dict[str, Any] = {}
    elif isinstance(target_product, dict):
        title = str(target_product.get("title") or "")
        category = str(target_product.get("category") or "")
        brand = str(target_product.get("brand") or "")
        tech_specs = target_product.get("tech_specs") or target_product.get("techSpecs") or {}
        fp_dict = target_product.get("fingerprint") or {}
        if hasattr(fp_dict, "model_dump"):
            fp_dict = fp_dict.model_dump()
    else:
        title = str(getattr(target_product, "title", "") or "")
        category = str(getattr(target_product, "category", "") or "")
        brand = str(getattr(target_product, "brand", "") or "")
        raw_specs = getattr(target_product, "tech_specs_json", None) or getattr(target_product, "tech_specs", None)
        if isinstance(raw_specs, str):
            try:
                tech_specs = json.loads(raw_specs)
            except Exception:
                tech_specs = {}
        elif isinstance(raw_specs, dict):
            tech_specs = raw_specs
        else:
            tech_specs = {}
        fp_dict = {}

    title = strip_color_tokens(title)
    norm_title = _normalize_corpus_text(title)
    norm_specs = _normalize_corpus_text(json.dumps(tech_specs, ensure_ascii=False))

    # 1. Almacenamiento objetivo (storage_gb)
    storage_gb: Optional[int] = fp_dict.get("storage_gb")
    if storage_gb is None:
        for num_s, unit_s in re.findall(r"\b(\d{1,4})(gb|tb)\b", f"{norm_title} {norm_specs}"):
            val = int(num_s) * (1024 if unit_s == "tb" else 1)
            if val >= 64 and val in VALID_STORAGE_GB:
                storage_gb = val
                break

    # 2. Memoria RAM objetivo (ram_gb) - solo obligatoria si aparece explícitamente en el título canónico
    ram_gb: Optional[int] = fp_dict.get("ram_gb")
    if ram_gb is None:
        for num_s, unit_s in re.findall(r"\b(\d{1,2})(gb)\b", norm_title):
            val = int(num_s)
            if val < 64 and val in VALID_RAM_GB:
                ram_gb = val
                break

    # 3. Pulgadas de pantalla (screen_inches)
    screen_inches: Optional[float] = (
        float(fp_dict["screen_inches"]) if fp_dict.get("screen_inches") is not None else None
    )
    if screen_inches is None:
        inch_m = re.search(
            r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|''|pulgadas|pulg|inch)\b",
            title,
            flags=re.IGNORECASE,
        )
        if inch_m:
            screen_inches = float(inch_m.group(1))
        else:
            for sz in TV_SCREEN_INCHES:
                if _has_word(str(sz), norm_title):
                    screen_inches = float(sz)
                    break

    is_tv = (
        category.lower() in {"tvs", "televisores", "tv"}
        or (screen_inches is not None and int(screen_inches) in TV_SCREEN_INCHES)
        or _has_word("oled", norm_title)
        or _has_word("qled", norm_title)
    )
    is_tablet_or_ipad = (
        category.lower() in {"tablets", "tablet"}
        or _has_word("ipad", norm_title)
        or _has_word("tab", norm_title)
        or _has_word("tablet", norm_title)
    )

    # 4. Conectividad objetivo
    requires_wifi_only_tablet = False
    requires_5g = False
    if is_tablet_or_ipad:
        has_cellular_in_target = any(
            _has_word(w, norm_title) for w in ("5g", "cellular", "lte", "4g")
        )
        if not has_cellular_in_target:
            requires_wifi_only_tablet = True
        else:
            requires_5g = _has_word("5g", norm_title)
    else:
        requires_5g = bool(fp_dict.get("network") == "5g" or _has_word("5g", norm_title))

    # 5. Tokens de línea, modelo y chip (excluyendo colores, marketing, capacidades y pulgadas)
    if fp_dict.get("family_tokens"):
        model_tokens = [str(t).lower() for t in fp_dict["family_tokens"]]
    else:
        excluded = (
            set(FORBIDDEN_QUERY_COLORS)
            | set(FORBIDDEN_QUERY_MARKETING_WORDS)
            | {"apple", "samsung", "xiaomi"}
        )
        if storage_gb:
            excluded.add(f"{storage_gb}gb")
            excluded.add(str(storage_gb))
        if ram_gb:
            excluded.add(f"{ram_gb}gb")
            excluded.add(str(ram_gb))
        if screen_inches is not None:
            s_int = str(int(screen_inches))
            s_flt = f"{screen_inches:.1f}".rstrip("0").rstrip(".")
            excluded.add(s_int)
            excluded.add(s_flt)

        model_tokens = []
        for w in re.findall(r"\b[a-z0-9]+\b", norm_title):
            if w in excluded:
                continue
            if w not in model_tokens:
                model_tokens.append(w)

    # Marca requerida
    brand_low = str(fp_dict.get("brand") or brand).lower().strip()
    if not brand_low:
        for w in re.findall(r"\b[a-z0-9]+\b", norm_title):
            if w in SUBBRAND_LINE_TO_PARENT_BRAND:
                brand_low = SUBBRAND_LINE_TO_PARENT_BRAND[w]
                break
            if w in {
                "apple", "samsung", "xiaomi", "lg", "asus", "lenovo", "hp",
                "sony", "honor", "motorola", "epson", "canon", "brother", "jvc", "hisense", "tcl"
            }:
                brand_low = w
                break

    # Si brand_low ya fue detectado, no exigir la marca padre explícitamente como model_token cuando hay línea/código
    if brand_low and brand_low in model_tokens and len(model_tokens) > 1:
        model_tokens = [t for t in model_tokens if t != brand_low]

    forbidden_tokens = [str(t).lower() for t in (fp_dict.get("forbidden_tokens") or [])]

    return {
        "title": title,
        "brand": brand_low,
        "model_tokens": model_tokens,
        "storage_gb": storage_gb,
        "ram_gb": ram_gb,
        "screen_inches": screen_inches,
        "is_tv": is_tv,
        "is_tablet_or_ipad": is_tablet_or_ipad,
        "requires_wifi_only_tablet": requires_wifi_only_tablet,
        "requires_5g": requires_5g,
        "forbidden_tokens": forbidden_tokens,
    }


def extract_search_candidate_links(
    html: str,
    search_url: str,
    broad_model_query: str,
    limit: int = 5,
) -> List[str]:
    """
    Extrae de la grilla de resultados de búsqueda (.product-item-info a.product-item-link
    o #__NEXT_DATA__ props.pageProps.results) los links de los primeros `limit` (5)
    productos cuyo título tenga coincidencia parcial con `broad_model_query` y no sean accesorios.
    """
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup

    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    query_tokens = [
        t
        for t in re.findall(r"\b[a-z0-9]+\b", _normalize_corpus_text(broad_model_query))
        if len(t) >= 2
    ]
    links: List[str] = []

    # 1. Grilla Magento 2 (Tiendas Efe, La Curacao, Hiraoka)
    for card in soup.select(".product-item-info, li.product-item"):
        anchors = card.select("a.product-item-link")
        best_title = ""
        best_href = ""
        for a in anchors:
            txt = a.get_text(" ", strip=True)
            if len(txt) > len(best_title):
                best_title = txt
                best_href = str(a.get("href") or "")
        if not best_title or not best_href:
            continue

        norm_t = _normalize_corpus_text(best_title)
        if any(_has_word(acc, norm_t) for acc in UNIVERSAL_ACCESSORY_KEYWORDS):
            continue

        if query_tokens and not all(_has_word(qt, norm_t) for qt in query_tokens):
            continue

        full_url = urljoin(search_url, best_href)
        if full_url not in links:
            links.append(full_url)
        if len(links) >= limit:
            return links

    # 2. Resultados Next.js (Falabella, Tottus)
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            data = json.loads(nd.string)
            results = data.get("props", {}).get("pageProps", {}).get("results") or []
            if isinstance(results, list):
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    item_title = str(item.get("displayName") or item.get("name") or "")
                    item_url = str(item.get("url") or "")
                    if not item_title or not item_url:
                        continue
                    norm_t = _normalize_corpus_text(item_title)
                    if any(_has_word(acc, norm_t) for acc in UNIVERSAL_ACCESSORY_KEYWORDS):
                        continue
                    if query_tokens and not all(_has_word(qt, norm_t) for qt in query_tokens):
                        continue
                    full_u = urljoin(search_url, item_url)
                    if full_u not in links:
                        links.append(full_u)
                    if len(links) >= limit:
                        return links
        except Exception:
            pass

    return links


def _get_commercial_screen_group(inches: float) -> Set[str]:
    s_clean = f"{inches:.1f}".rstrip("0").rstrip(".")
    for grp in COMMERCIAL_SCREEN_EQUIVALENTS:
        if s_clean in grp:
            return grp
    return {s_clean, str(int(round(inches)))}


def match_product_universal(target_product: Any, candidate_page_data: Any) -> bool:
    """
    Validador Universal sobre el Corpus Completo del Candidato:
    full_corpus = f"{candidate.title} {candidate.url} {json.dumps(candidate.tech_specs, ensure_ascii=False)} {candidate.description}".lower()
    Evalúa las 6 reglas universales de emparejamiento multi-tienda.
    """
    if not target_product or not candidate_page_data:
        return False

    profile = _extract_target_profile(target_product)

    if isinstance(candidate_page_data, dict):
        cand_title = str(candidate_page_data.get("title") or "")
        cand_url = str(candidate_page_data.get("offer_url") or candidate_page_data.get("url") or "")
        cand_specs = candidate_page_data.get("tech_specs") or {}
        cand_desc = str(candidate_page_data.get("description") or "")
    else:
        cand_title = str(getattr(candidate_page_data, "title", "") or "")
        cand_url = str(getattr(candidate_page_data, "offer_url", "") or getattr(candidate_page_data, "url", "") or "")
        cand_specs = getattr(candidate_page_data, "tech_specs", None) or {}
        cand_desc = str(getattr(candidate_page_data, "description", "") or "")

    if not isinstance(cand_specs, dict):
        cand_specs = {}

    full_corpus_raw = (
        f"{cand_title} {cand_url} {json.dumps(cand_specs, ensure_ascii=False)} {cand_desc}"
    ).lower()

    title_norm = _normalize_corpus_text(cand_title)
    url_norm = _normalize_corpus_text(cand_url)
    specs_norm = _normalize_corpus_text(json.dumps(cand_specs, ensure_ascii=False))
    desc_norm = _normalize_corpus_text(cand_desc)
    full_corpus = _normalize_corpus_text(full_corpus_raw)

    if not title_norm and not url_norm:
        return False

    target_norm = _normalize_corpus_text(profile["title"])

    # --------------------------------------------------------------------------
    # REGLA 0: Bloqueo de Accesorios, Reacondicionados y Tokens Prohibidos (en title y url)
    # --------------------------------------------------------------------------
    if "open box" in title_norm or "open box" in url_norm:
        return False

    for acc_kw in UNIVERSAL_ACCESSORY_KEYWORDS:
        if (_has_word(acc_kw, title_norm) or _has_word(acc_kw, url_norm)) and not _has_word(acc_kw, target_norm):
            return False

    for f_tok in profile["forbidden_tokens"]:
        f_norm = _normalize_corpus_text(f_tok)
        if _has_word(f_norm, title_norm) or _has_word(f_norm, url_norm):
            return False

    # --------------------------------------------------------------------------
    # REGLA 1: Ignorar Colores y Palabras de Marketing
    # (Los colores jamás descartan un candidato del mismo SKU técnico)
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    # REGLA 2: Coincidencia Estricta de Línea y Código de Modelo / Chip
    # en title + tech_specs (o url si title está vacío), con Bloqueo de Sub-modelos Intrusos
    # --------------------------------------------------------------------------
    primary_title_or_url = title_norm if title_norm else url_norm
    identity_zone = f"{primary_title_or_url} {specs_norm}".strip()
    primary_zone = f"{title_norm} {url_norm}".strip()

    # Verificar marca (o línea implícita: ipad/iphone/macbook -> apple, galaxy -> samsung, redmi -> xiaomi)
    brand_low = profile["brand"]
    if brand_low:
        brand_aliases = {brand_low}
        for sub_line, parent_b in SUBBRAND_LINE_TO_PARENT_BRAND.items():
            if parent_b == brand_low:
                brand_aliases.add(sub_line)
        if not any(_has_word(alias, full_corpus) for alias in brand_aliases):
            return False

    # Todos los tokens de línea/modelo/chip (ej. ['ipad', 'a16'], ['oled', 'c6'], ['redmi', 'note', '15', 'pro'])
    # deben estar presentes en title + tech_specs + url
    for m_tok in profile["model_tokens"]:
        if not _has_word(m_tok, identity_zone):
            return False

    # Bloqueo de Sub-modelos Intrusos:
    # Si el objetivo es "iPad" estándar (A16), rechazar "iPad Air", "iPad Pro", "iPad Mini".
    # Si el objetivo es "Pro" (sin "Max"), rechazar "Pro Max", "Lite", "FE", etc.
    target_model_set = set(profile["model_tokens"])
    for tier_tok in STRICT_SUBMODEL_TIERS:
        if tier_tok not in target_model_set:
            if _has_word(tier_tok, title_norm) or _has_word(tier_tok, url_norm):
                return False
        else:
            # Si el objetivo EXIGE el tier (ej. 'pro', 'ultra', 'air', 'fe'), debe aparecer en title o url
            if not (_has_word(tier_tok, title_norm) or _has_word(tier_tok, url_norm)):
                return False

    # Si tanto title como url están presentes y url tiene un modelo explícito de otra serie, bloquear
    # (ej. title falsificado o inyectado pero URL dice 'redmi-a7' cuando se busca 'note 15')
    if title_norm and url_norm:
        if "note" in target_model_set and "redmi" in url_norm and not _has_word("note", url_norm):
            return False

    # --------------------------------------------------------------------------
    # REGLA 3: Validación de Almacenamiento (storage_gb) en el Corpus Completo
    # --------------------------------------------------------------------------
    req_storage = profile["storage_gb"]
    if req_storage is not None:
        req_stor_tokens = {"1024gb", "1tb"} if req_storage == 1024 else {f"{req_storage}gb"}
        all_valid_stor_tokens = {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}

        # 3a. Verificar que en candidate.title, candidate.url o campos de almacenamiento de tech_specs
        # NO aparezca explícitamente OTRA capacidad de almacenamiento distinta
        title_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", title_norm) if m in all_valid_stor_tokens
        }
        url_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", url_norm) if m in all_valid_stor_tokens
        }

        spec_storage_fields_text = _normalize_corpus_text(
            " ".join(
                str(v)
                for k, v in cand_specs.items()
                if any(
                    sk in k.lower()
                    for sk in ("almacenamiento", "memoria interna", "disco", "ssd", "rom", "capacidad")
                )
                and "ram" not in k.lower()
                and "bateria" not in k.lower()
                and "batería" not in k.lower()
            )
        )
        spec_storages = {
            m
            for m in re.findall(r"\b(\d+(?:gb|tb))\b", spec_storage_fields_text)
            if m in all_valid_stor_tokens
        }

        if title_storages and not (title_storages & req_stor_tokens):
            return False
        if url_storages and not (url_storages & req_stor_tokens):
            return False
        if spec_storages and not (spec_storages & req_stor_tokens):
            return False

        # 3b. Verificar que la capacidad requerida aparezca en CUALQUIER parte del full_corpus
        # (title, url, tech_specs o description)
        corpus_storages = {
            m for m in re.findall(r"\b(\d+(?:gb|tb))\b", full_corpus) if m in all_valid_stor_tokens
        }
        if not (corpus_storages & req_stor_tokens):
            return False

    # Validación de RAM si el producto objetivo la exige y el candidato declara otra RAM explícita en título/URL
    req_ram = profile["ram_gb"]
    if req_ram is not None:
        req_ram_tok = f"{req_ram}gb"
        ram_tokens_set = {f"{r}gb" for r in VALID_RAM_GB if r < 64}
        title_rams = {m for m in re.findall(r"\b(\d+gb)\b", title_norm) if m in ram_tokens_set}
        url_rams = {m for m in re.findall(r"\b(\d+gb)\b", url_norm) if m in ram_tokens_set}
        if title_rams and req_ram_tok not in title_rams:
            return False
        if url_rams and req_ram_tok not in url_rams:
            return False

    # --------------------------------------------------------------------------
    # REGLA 4: Validación de Tamaño de Pantalla (screen_inches) en el Corpus Completo
    # con Exactitud en TVs y Tolerancia de Redondeo Comercial en Tablets/Laptops
    # --------------------------------------------------------------------------
    req_inches = profile["screen_inches"]
    if req_inches is not None:
        if profile["is_tv"]:
            req_tv_sz = str(int(round(req_inches)))
            # En TVs, bloquear cualquier otro tamaño de TV en title, url o specs de pantalla
            other_tv_sizes = TV_SCREEN_INCHES - {int(round(req_inches))}
            for other_sz in other_tv_sizes:
                if _has_word(str(other_sz), title_norm) or _has_word(str(other_sz), url_norm):
                    return False
            if not _has_word(req_tv_sz, full_corpus):
                return False
        else:
            # En Tablets y Laptops: equivalencia comercial (10.9" == 11", 13.3" == 13.6")
            allowed_sizes = _get_commercial_screen_group(req_inches)
            conflicting_sizes = CONFLICTING_TABLET_LAPTOP_SIZES - allowed_sizes

            # Bloquear si el título o la tabla de pantalla declara otro tamaño conflictivo (ej. 12.9" o 13" vs 11")
            screen_spec_text = _normalize_corpus_text(
                " ".join(
                    str(v)
                    for k, v in cand_specs.items()
                    if any(sk in k.lower() for sk in ("pantalla", "tamaño", "tamano", "diagonal", "pulgadas"))
                )
            )
            for bad_sz in conflicting_sizes:
                # En título o URL, verificar cuando va acompañado de contexto de pantalla o decimal
                if "." in bad_sz:
                    if _has_word(bad_sz, title_norm) or _has_word(bad_sz, screen_spec_text):
                        return False
                else:
                    # Evitar confundir '16' de 'A16' o '16GB' con 16 pulgadas
                    if re.search(rf"\b{re.escape(bad_sz)}\s*(?:pulgadas|pulg|inch)\b", f"{cand_title} {cand_desc}", flags=re.IGNORECASE):
                        return False
                    if _has_word(bad_sz, screen_spec_text):
                        return False

            # Verificar presencia de alguna medida equivalente en full_corpus
            has_screen_in_corpus = any(_has_word(sz, full_corpus) for sz in allowed_sizes)
            if not has_screen_in_corpus:
                return False

    # --------------------------------------------------------------------------
    # REGLA 5: Validación de Conectividad (Wi-Fi vs Cellular/5G en Tablets; 5G vs 4G en Smartphones)
    # --------------------------------------------------------------------------
    if profile["requires_wifi_only_tablet"]:
        # Si la tablet objetivo es solo Wi-Fi, rechazar versiones Cellular / + 5G / LTE
        if any(_has_word(cell_tok, primary_zone) for cell_tok in ("cellular", "lte", "5g", "4g")):
            return False

    if profile["requires_5g"]:
        if _has_word("4g", title_norm) and not _has_word("5g", title_norm):
            return False
        if not _has_word("5g", full_corpus):
            return False

    return True


def filter_offers_by_price_sanity(offers: Sequence[Any]) -> List[Any]:
    """
    Regla 6: Filtro Estadístico de Cordura de Precio (0.55 <= price / median_price <= 1.65).
    Descarta accesorios o errores de parseo cuyo precio se desvíe fuera del rango estadístico
    respecto a la mediana de las tiendas verificadas.
    """
    if not offers:
        return []

    def _get_p(o: Any) -> float:
        if isinstance(o, dict):
            return float(o.get("price") or 0.0)
        return float(getattr(o, "price", 0.0) or 0.0)

    def _get_store(o: Any) -> str:
        if isinstance(o, dict):
            return str(o.get("store_id") or o.get("storeId") or o.get("store_name") or "unknown")
        return str(getattr(o, "store_id", None) or getattr(o, "store_name", None) or "unknown")

    valid = [o for o in offers if _get_p(o) > 0]
    if len(valid) <= 1:
        return list(valid)

    prices = [_get_p(o) for o in valid]
    reference_price = max(prices) if len(prices) == 2 else float(statistics.median(prices))

    min_allowed = reference_price * 0.55
    max_allowed = reference_price * 1.65

    filtered: List[Any] = []
    for off in valid:
        p = _get_p(off)
        s_id = _get_store(off)
        if p < min_allowed or p > max_allowed:
            logger.warning(
                f"[PRICE_OUTLIER_REJECTED] {s_id}: S/ {p} fuera de rango de cordura "
                f"[0.55x={min_allowed:.2f}, 1.65x={max_allowed:.2f}] vs mediana S/ {reference_price:.2f}"
            )
            continue
        filtered.append(off)

    return filtered


class UniversalProductResolver:
    """
    Motor Universal de Búsqueda en Cascada, Resolución Multi-SKU y Validación sobre Corpus Completo
    para las 8 tiendas del retail peruano (falabella, tottus, ripley, efe, curacao, hiraoka, metro, wong).
    """

    def __init__(self, scrape_fn: Optional[Callable[..., Any]] = None):
        self._scrape_fn = scrape_fn

    async def resolve_store_offer(
        self,
        store_id: str,
        target_product: Dict[str, Any],
        direct_url: Optional[str] = None,
        enable_cascade_search: bool = True,
        scrape_fn: Optional[Callable[..., Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resuelve la oferta de un producto en una tienda específica:
        1. Si existe direct_url verificada, la descarga y evalúa con match_product_universal.
        2. Si no existe direct_url (o falla) y enable_cascade_search=True:
           - Ejecuta specific_query ("{marca_o_linea} {modelo_y_chip} {almacenamiento_o_pulgadas}")
           - Si no devuelve candidato válido, ejecuta inmediatamente broad_model_query ("{marca_o_linea} {modelo_y_chip}")
             y evalúa las páginas/variantes de los primeros 5 productos devueltos.
        """
        from app.collectors.catalog_urls import STORES_INFO

        active_scraper = scrape_fn or self._scrape_fn
        if active_scraper is None:
            from app.collectors.orchestrator import orchestrator
            active_scraper = orchestrator.scrape_store_url

        canonical_title = str(target_product.get("title") or "")
        tech_specs = target_product.get("tech_specs") or {}

        # Paso 1: Intentar URL directa si está configurada
        if direct_url:
            _, clean_direct = canonicalize_store_url(direct_url)
            target_u = clean_direct or direct_url
            try:
                res = await active_scraper(
                    store_id=store_id,
                    url=target_u,
                    canonical_title=canonical_title,
                    tech_specs=tech_specs,
                    target_product=target_product,
                )
            except TypeError:
                res = await active_scraper(
                    store_id=store_id,
                    url=target_u,
                    canonical_title=canonical_title,
                    tech_specs=tech_specs,
                )
            if isinstance(res, dict) and res.get("price") and float(res["price"]) > 0:
                if match_product_universal(target_product, res):
                    _, clean_offer = canonicalize_store_url(res.get("offer_url") or target_u)
                    store_meta = STORES_INFO.get(store_id, {})
                    return {
                        "store_id": store_id,
                        "store_name": res.get("store_name") or store_meta.get("name", store_id.title()),
                        "title": res.get("title") or canonical_title,
                        "price": round(float(res["price"]), 2),
                        "original_price": res.get("original_price"),
                        "offer_url": clean_offer or target_u,
                        "image_url": res.get("image_url"),
                        "brand": res.get("brand"),
                        "tech_specs": res.get("tech_specs") or {},
                        "features": res.get("features") or [],
                        "description": res.get("description") or "",
                    }

        if not enable_cascade_search:
            return None

        # Paso 2: Búsqueda en cascada (specific_query -> broad_model_query)
        queries = build_search_queries(canonical_title, tech_specs)
        for query in queries:
            search_url = build_store_search_url(store_id, query)
            if not search_url:
                continue
            try:
                res = await active_scraper(
                    store_id=store_id,
                    url=search_url,
                    canonical_title=canonical_title,
                    tech_specs=tech_specs,
                    target_product=target_product,
                )
            except TypeError:
                res = await active_scraper(
                    store_id=store_id,
                    url=search_url,
                    canonical_title=canonical_title,
                    tech_specs=tech_specs,
                )

            if not isinstance(res, dict) or not res.get("price") or float(res["price"]) <= 0:
                continue

            raw_offer_url = str(res.get("offer_url") or "").strip()
            if not raw_offer_url or any(
                m in raw_offer_url
                for m in ("/catalogsearch/result", "/api/catalog_system/", "?q=", "?ft=", "?s=")
            ):
                continue

            _, clean_offer = canonicalize_store_url(raw_offer_url)
            res["offer_url"] = clean_offer or raw_offer_url

            if match_product_universal(target_product, res):
                store_meta = STORES_INFO.get(store_id, {})
                return {
                    "store_id": store_id,
                    "store_name": res.get("store_name") or store_meta.get("name", store_id.title()),
                    "title": res.get("title") or canonical_title,
                    "price": round(float(res["price"]), 2),
                    "original_price": res.get("original_price"),
                    "offer_url": res["offer_url"],
                    "image_url": res.get("image_url"),
                    "brand": res.get("brand"),
                    "tech_specs": res.get("tech_specs") or {},
                    "features": res.get("features") or [],
                    "description": res.get("description") or "",
                }

        return None

    async def resolve_product_across_8_stores(
        self,
        target_product: Dict[str, Any],
        stores_to_check: Optional[Sequence[str]] = None,
        enable_cascade_search: bool = False,
        scrape_fn: Optional[Callable[..., Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evalúa concurrentemente las tiendas configuradas o las 8 tiendas del retail peruano,
        validando cada candidato sobre su corpus completo (match_product_universal)
        y aplicando el filtro de cordura de precios (0.55 <= price / median <= 1.65).
        """
        direct_urls: Dict[str, str] = target_product.get("store_urls") or {}
        if stores_to_check is not None:
            stores = list(stores_to_check)
        elif enable_cascade_search:
            stores = list(ALL_8_PERU_STORES)
        else:
            stores = list(direct_urls.keys())

        tasks = [
            self.resolve_store_offer(
                store_id=s_id,
                target_product=target_product,
                direct_url=direct_urls.get(s_id),
                enable_cascade_search=enable_cascade_search,
                scrape_fn=scrape_fn,
            )
            for s_id in stores
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        matched_offers: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict) and r.get("price"):
                matched_offers.append(r)

        clean_offers = filter_offers_by_price_sanity(matched_offers)
        clean_offers.sort(key=lambda x: x["price"])
        return clean_offers


universal_resolver = UniversalProductResolver()
