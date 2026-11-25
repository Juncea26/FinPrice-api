"""
Motor genérico, extensible y orientado a datos para barrer listados de categorías
tecnológicas en las 8 tiendas oficiales 1P del Perú (`falabella`, `ripley`, `tottus`,
`efe`, `curacao`, `hiraoka`, `metro`, `wong`).

Reutiliza:
- `http_client.py` (`curl_cffi` + `httpx` + soporte selectivo `PERU_PROXY_URL`)
- `tech_normalizer.py` (normalización unificada y extracción de MPN/EAN)
- `parsers/*.py` y `validators.py` (extracción de precios vigentes y filtro estricto 1P)
- `category_registry.py` (registro declarativo de categorías y paginación)
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.category_registry import (
    ALL_TECH_STORES,
    CategorySpec,
    StoreCategorySource,
    build_paginated_category_url,
    get_category_spec,
    get_store_category_sources,
    infer_tech_category,
    is_valid_storage_or_network_item,
)
from app.collectors.http_client import fetch_page
from app.collectors.parsers.falabella import (
    _is_falabella_item_official,
    clean_number as clean_falabella_number,
    extract_falabella_prices,
)
from app.collectors.parsers.hiraoka import (
    _select_hiraoka_main_search_cards,
    clean_number as clean_hiraoka_number,
)
from app.collectors.parsers.ripley import (
    _build_ripley_item_url,
    _extract_ripley_search_item_prices,
    _index_ripley_dom_links,
    _is_ripley_node_in_stock,
    _is_ripley_search_item_official,
    clean_number as clean_ripley_number,
)
from app.collectors.parsers.vtex_cencosud import (
    _extract_cencosud_card_price_from_offer,
    clean_number as clean_vtex_number,
)
from app.collectors.spec_extractor import normalize_brand
from app.collectors.tech_normalizer import (
    _normalize_mpn,
    _strip_bundles_and_colors,
    build_canonical_product_signature,
    extract_product_codes,
    is_strict_tech_product,
    normalize_tech_text,
    strip_accents_lower,
)
from app.collectors.url_utils import (
    canonicalize_store_url,
    ensure_https_image_url,
    is_marketplace_url,
    is_valid_product_image_url,
)
from app.collectors.validators import is_official_store_seller
from app.core.database import WriterSessionLocal
from app.core.logging import get_logger
from app.models.entities import StoreListing, utc_now_naive

logger = get_logger("collectors.category_crawler")

_REFURBISHED_MARKERS: Tuple[str, ...] = (
    "reacondicionado",
    "reacondicionada",
    "reacondicionados",
    "refurbished",
    "renovado",
    "renovada",
    "seminuevo",
    "seminueva",
    "openbox",
    "open box",
)

_MAIN_CATEGORY_ACCESSORY_KEYWORDS: Tuple[str, ...] = (
    "funda",
    "fundas",
    "cover",
    "covers",
    "case",
    "cases",
    "carcasa",
    "carcasas",
    "estuche",
    "estuches",
    "teclado",
    "teclados",
    "mica",
    "micas",
    "vidrio templado",
    "protector de pantalla",
    "protector pantalla",
    "cable",
    "cables",
    "cargador",
    "cargadores",
    "adaptador",
    "adaptadores",
    "botella de tinta",
    "botellas de tinta",
    "cartucho",
    "cartuchos",
    "toner",
    "cabezal",
    "tambor",
    "cinta",
    "rack",
    "soporte",
    "soportes",
    "mochila",
    "maletin",
    "cooler",
    "mousepad",
    "mouse pad",
    "correa",
    "correas",
)

_CONSOLE_NON_HARDWARE_RE = re.compile(
    r"^(?:juego|videojuego|gift\s+card|membresia|tarjeta\s+de\s+regalo|mando|control|dualsense|joy-?con|estuche|funda|cargador|base\s+de\s+carga|soporte)\b"
)

_GIFT_TAIL_RE = re.compile(
    r"\s*(?:\+|\bcon\b|\bincluye\b)\s*(?:funda|case|folio|book\s*cover|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|lapiz|pen|stylus|combo|pack|tags?|regalo|watch|buds|soporte|juego|videojuego|mando|control|ea\s+sports)\b.*$",
    flags=re.IGNORECASE,
)

_STORE_DISPLAY_SELLER_NAMES: Dict[str, str] = {
    "falabella": "Falabella",
    "ripley": "Ripley",
    "tottus": "Tottus",
    "efe": "Tiendas Efe",
    "curacao": "La Curacao",
    "hiraoka": "Hiraoka",
    "metro": "Metro",
    "wong": "Wong",
}

_MAGENTO_ALLOWED_SELLER_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "efe": ("tiendas efe", "efe"),
    "curacao": ("la curacao", "curacao"),
    "hiraoka": ("hiraoka",),
}


@dataclass
class ScrapedListing:
    """Representación normalizada de un listing 1P listo para persistir en `store_listings`."""

    store: str
    store_sku: str
    category: str
    title: str
    brand: str
    price: float
    original_price: Optional[float]
    currency: str
    url: str
    image_url: Optional[str] = None
    in_stock: bool = True
    seller_name: Optional[str] = None
    mpn: Optional[str] = None
    ean: Optional[str] = None
    normalized_signature: str = ""


@dataclass
class ListingPageParseResult:
    """Resultado de parsear una página de listado de categoría."""

    listings: List[ScrapedListing] = field(default_factory=list)
    raw_cards_seen: int = 0
    discarded_marketplace: int = 0
    discarded_filtered: int = 0


@dataclass
class SourceCrawlStats:
    """Métricas por combinación `(store, category)`."""

    store: str
    category: str
    pages_fetched: int = 0
    raw_cards_seen: int = 0
    extracted_1p: int = 0
    inserted: int = 0
    updated: int = 0
    discarded_marketplace: int = 0
    discarded_filtered: int = 0


@dataclass
class CategoryCrawlSummary:
    """Resumen completo de un barrido de categorías tech."""

    sources_processed: int = 0
    pages_fetched: int = 0
    extracted_1p: int = 0
    inserted: int = 0
    updated: int = 0
    discarded_marketplace: int = 0
    discarded_filtered: int = 0
    dry_run: bool = False
    by_source: List[SourceCrawlStats] = field(default_factory=list)
    by_store: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)
    listings: List[ScrapedListing] = field(default_factory=list)


def build_listing_signature(
    title: str,
    brand: str = "",
    url: str = "",
    category: str = "",
) -> str:
    """
    Genera una firma técnica normalizada (`normalized_signature`) mediante `tech_normalizer.py`
    para facilitar el matching en Fase 2B sin sensibilidad a colores ni palabras de marketing.
    """
    return build_canonical_product_signature(
        title=title,
        brand=brand,
        url=url,
        category=category,
    )


def compute_fallback_sku(store: str, url: str) -> str:
    """Extrae un SKU estable desde la URL canónica o genera un hash SHA-256 determinista."""
    clean_u = str(url or "").strip()
    path = urlparse(clean_u).path.rstrip("/")

    if store in {"falabella", "tottus"}:
        m = re.search(r"/(?:product|articulo)/[^/]+/[^/]+/([^/?#]+)$", path, flags=re.I)
        if m:
            return m.group(1)[:120]
    elif store == "ripley":
        m = re.search(r"-([a-z0-9]+p|\d{6,15})$", path, flags=re.I)
        if m:
            return m.group(1).upper()[:120]
    elif store in {"metro", "wong"}:
        m = re.search(r"-(\d{4,12})/p$", path, flags=re.I)
        if m:
            return m.group(1)[:120]

    digest = hashlib.sha256(f"{store}:{clean_u}".encode("utf-8")).hexdigest()[:16]
    return f"url_{digest}"


def _clean_base_title_for_filter(title: str) -> str:
    base = _GIFT_TAIL_RE.sub("", strip_accents_lower(title or "")).strip()
    return re.sub(r"\s+", " ", base).strip()


def _is_non_hardware_for_category(title: str, category_spec: CategorySpec) -> bool:
    """Rechaza reacondicionados y accesorios/consumibles intrusos en categorías de equipos principales."""
    base_low = _clean_base_title_for_filter(title)
    if not base_low:
        return True

    if any(ref in base_low for ref in _REFURBISHED_MARKERS):
        return True

    if category_spec.is_accessory_category:
        return False

    for kw in _MAIN_CATEGORY_ACCESSORY_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", base_low):
            return True

    if category_spec.slug == "impresoras":
        if any(tok in base_low for tok in ("botella", "cartucho", "toner", "tinta para", "recarga", "repuesto")):
            if not any(pr in base_low for pr in ("impresora", "multifuncional", "escaner")):
                return True

    if category_spec.slug == "consolas":
        if _CONSOLE_NON_HARDWARE_RE.match(base_low):
            return True

    return False


def _is_search_like_url(url: str) -> bool:
    u_low = (url or "").lower()
    return any(
        marker in u_low
        for marker in ("/search", "/buscar", "/catalogsearch/", "ntt=", "?ft=", "&ft=", "?q=", "&q=")
    )


def _normalize_image_candidate(raw_img: Optional[str], page_url: str = "") -> Optional[str]:
    return ensure_https_image_url(raw_img, page_url=page_url)


def _extract_best_img_from_element(container: Optional[Tag], page_url: str = "") -> Optional[str]:
    """Recorre todos los <img> y atributos lazy/srcset de una tarjeta hasta encontrar la primera imagen HTTPS válida."""
    if container is None:
        return None
    img_tags = container.select("img")
    for img_el in img_tags:
        candidates: List[str] = []
        for attr in ("data-src", "data-original", "data-lazy", "data-zoom-image", "src"):
            val = img_el.get(attr)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())
        for srcset_attr in ("data-srcset", "srcset"):
            ss = img_el.get(srcset_attr)
            if isinstance(ss, str) and ss.strip():
                for part in ss.split(","):
                    u_tok = part.strip().split(" ", 1)[0].strip()
                    if u_tok:
                        candidates.append(u_tok)
        for cand in candidates:
            valid = ensure_https_image_url(cand, page_url=page_url)
            if valid:
                return valid
    return None


def _is_falabella_listing_in_stock(item: Dict[str, Any]) -> bool:
    """Verifica disponibilidad real en ítems de listado Falabella/Tottus, rechazando 'Pronto disponible' y agotados."""
    if item.get("isOutOfStock") is True or item.get("outOfStock") is True:
        return False
    for pos_k in ("inStock", "sellable", "hasStock", "isAvailable", "available"):
        if pos_k in item and item[pos_k] is False:
            return False
    avail_str = " ".join(
        str(item.get(k) or "")
        for k in ("availability", "stockStatus", "status", "badge", "badgeText", "shippingBadge")
    ).lower()
    for b_key in ("badges", "flags", "ribbons"):
        b_val = item.get(b_key)
        if isinstance(b_val, list):
            avail_str += " " + " ".join(str(x) for x in b_val).lower()
    if any(tok in avail_str for tok in ("outofstock", "out_of_stock", "agotado", "sin stock", "pronto disponible", "no disponible")):
        return False
    return True


def _finalize_candidate_listing(
    *,
    store: str,
    raw_sku: Optional[str],
    raw_title: str,
    raw_brand: str,
    price: Optional[float],
    original_price: Optional[float],
    raw_url: str,
    image_url: Optional[str],
    in_stock: bool,
    seller_name: Optional[str],
    category_spec: CategorySpec,
    page_url: str,
    is_broad_category: bool,
    explicit_mpn: Optional[str] = None,
    explicit_ean: Optional[str] = None,
) -> Tuple[Optional[ScrapedListing], str]:
    """
    Aplica filtros comunes de calidad, clasificación de categoría, extracción de códigos
    y generación de `normalized_signature`. Retorna `(listing, reject_reason)`.
    """
    title = re.sub(r"\s+", " ", str(raw_title or "")).strip()
    if not title:
        return (None, "filtered")

    if price is None or float(price) <= 0.0:
        return (None, "filtered")
    price_val = round(float(price), 2)
    if price_val < category_spec.min_valid_price_pen:
        return (None, "filtered")

    _, clean_u = canonicalize_store_url(raw_url)
    eff_url = (clean_u or raw_url or "").strip()
    if not eff_url.startswith("http"):
        return (None, "filtered")
    if is_marketplace_url(store, eff_url):
        return (None, "marketplace")

    if _is_non_hardware_for_category(title, category_spec):
        return (None, "filtered")

    inferred = infer_tech_category(title=title, url=eff_url, default_category=category_spec.slug)
    if is_broad_category:
        final_category = inferred if inferred != "otros_tech" else category_spec.slug
    elif category_spec.slug == "almacenamiento_redes" and inferred not in {"almacenamiento_redes", "otros_tech"}:
        final_category = inferred
    else:
        if _is_search_like_url(page_url) and inferred not in {category_spec.slug, "otros_tech"}:
            return (None, "filtered")
        final_category = category_spec.slug

    if final_category == "almacenamiento_redes" and not is_valid_storage_or_network_item(title, eff_url):
        return (None, "filtered")

    if not is_strict_tech_product(title=title, category=final_category, url=eff_url, brand=raw_brand):
        return (None, "filtered")

    brand = normalize_brand(raw_brand, title)
    if brand and brand.lower() not in title.lower():
        full_title = f"{brand} {title}".strip()
    else:
        full_title = title

    codes = extract_product_codes(title=full_title, url=eff_url)
    mpn_val = _normalize_mpn(explicit_mpn) if explicit_mpn else None
    if not mpn_val and codes.get("mpn"):
        mpn_val = codes["mpn"][0]

    ean_val = str(explicit_ean or "").strip() or None
    if ean_val and not re.match(r"^\d{8,14}$", ean_val):
        ean_val = None
    if not ean_val and codes.get("gtin"):
        ean_val = codes["gtin"][0]

    orig_val = round(float(original_price), 2) if (original_price and float(original_price) > price_val) else price_val
    sku_val = str(raw_sku or "").strip()[:120] or compute_fallback_sku(store, eff_url)
    sig = build_listing_signature(title=full_title, brand=brand, url=eff_url, category=final_category)

    return (
        ScrapedListing(
            store=store,
            store_sku=sku_val,
            category=final_category,
            title=full_title[:500],
            brand=brand[:120],
            price=price_val,
            original_price=orig_val,
            currency="PEN",
            url=eff_url[:700],
            image_url=_normalize_image_candidate(image_url, page_url=page_url),
            in_stock=bool(in_stock),
            seller_name=(seller_name or _STORE_DISPLAY_SELLER_NAMES.get(store, store.title()))[:120],
            mpn=mpn_val[:120] if mpn_val else None,
            ean=ean_val[:32] if ean_val else None,
            normalized_signature=sig[:500],
        ),
        "",
    )


def _extract_falabella_group_listings(
    store: str,
    html: str,
    page_url: str,
    category_spec: CategorySpec,
    is_broad_category: bool,
) -> ListingPageParseResult:
    """Extrae en bloque los productos 1P de Falabella o Tottus desde `__NEXT_DATA__` o pods DOM."""
    result = ListingPageParseResult()
    soup = BeautifulSoup(html, "lxml")

    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            data = json.loads(nd.string)
            props = data.get("props", {}).get("pageProps", {})
            pagination = props.get("pagination") or {}
            total_res = props.get("totalResults")
            if total_res is None:
                total_res = pagination.get("count")
            if _is_search_like_url(page_url) and total_res == 0:
                return result
            results = props.get("results") or (props.get("serverData") or {}).get("results") or []
            if isinstance(results, list) and results:
                expected_tok = "tottus" if store == "tottus" else "falabella"
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    result.raw_cards_seen += 1

                    raw_url = str(item.get("url") or "").strip()
                    if not raw_url:
                        continue
                    full_u = urljoin(page_url, raw_url)
                    sku_id = str(item.get("skuId") or item.get("productId") or "").strip()
                    if sku_id and re.match(
                        r"^https?://[^/]+/(?:falabella-pe|tottus-pe)/(?:product|articulo)/[^/]+/[^/?#]+/?$",
                        full_u,
                        flags=re.I,
                    ):
                        full_u = f"{full_u.rstrip('/')}/{sku_id}"

                    if not _is_falabella_item_official(item, store) or is_marketplace_url(store, full_u):
                        result.discarded_marketplace += 1
                        continue

                    seller_raw = str(item.get("sellerName") or item.get("sellerId") or "").strip()
                    if seller_raw and expected_tok not in seller_raw.lower():
                        result.discarded_marketplace += 1
                        continue

                    best_p, list_p = extract_falabella_prices(item.get("prices") or [])
                    if not best_p:
                        result.discarded_filtered += 1
                        continue

                    media_urls = item.get("mediaUrls") or []
                    img_u = media_urls[0] if isinstance(media_urls, list) and media_urls else None
                    if not img_u and isinstance(item.get("media"), dict):
                        img_u = item["media"].get("url")

                    in_stock = _is_falabella_listing_in_stock(item)
                    listing, reason = _finalize_candidate_listing(
                        store=store,
                        raw_sku=sku_id,
                        raw_title=str(item.get("displayName") or item.get("name") or ""),
                        raw_brand=str(item.get("brand") or ""),
                        price=best_p,
                        original_price=list_p,
                        raw_url=full_u,
                        image_url=img_u,
                        in_stock=in_stock,
                        seller_name=seller_raw or _STORE_DISPLAY_SELLER_NAMES[store],
                        category_spec=category_spec,
                        page_url=page_url,
                        is_broad_category=is_broad_category,
                    )
                    if listing:
                        result.listings.append(listing)
                    elif reason == "marketplace":
                        result.discarded_marketplace += 1
                    else:
                        result.discarded_filtered += 1
                return result
        except Exception as exc:
            logger.debug(f"Error parseando __NEXT_DATA__ listado en {store}: {exc}")

    # Fallback DOM si la página no incluye results en __NEXT_DATA__
    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "aside, nav, header, footer, [class*='filter'], [class*='facet'], [id*='filter'], [class*='sidebar']"
    ):
        noise.decompose()

    pods = clean_soup.select(
        ".search-results--products .pod, [data-pod='catalyst-pod'], div.pod, article.pod-item"
    )
    for pod in pods:
        link_el = pod.select_one("a[href*='/product/'], a[href*='/articulo/'], a[href]")
        if not link_el:
            continue
        raw_href = str(link_el.get("href") or "").strip()
        if not raw_href:
            continue
        result.raw_cards_seen += 1
        item_url = urljoin(page_url, raw_href)
        if is_marketplace_url(store, item_url):
            result.discarded_marketplace += 1
            continue

        seller_el = pod.select_one(".pod-sellerText, [id*='displaySellerText'], [class*='seller']")
        seller_txt = seller_el.get_text(" ", strip=True) if seller_el else ""
        if seller_txt and not is_official_store_seller(store, seller_txt, item_url):
            result.discarded_marketplace += 1
            continue
        if not seller_txt and not is_official_store_seller(store, str(pod), item_url):
            result.discarded_marketplace += 1
            continue

        title_el = pod.select_one(".pod-subTitle, [class*='subTitle'], [data-testid='pod-title'], b.title, h2, h3")
        brand_el = pod.select_one(".pod-title, [class*='brand']")
        item_title = title_el.get_text(" ", strip=True) if title_el else link_el.get_text(" ", strip=True)
        item_brand = brand_el.get_text(" ", strip=True) if brand_el else ""

        active_prices: List[float] = []
        reg_prices: List[float] = []
        for p_el in pod.select("[data-cmr-price], [data-internet-price], [data-event-price], .prices-0 span, .copy10"):
            p_num = clean_falabella_number(
                p_el.get("data-cmr-price")
                or p_el.get("data-internet-price")
                or p_el.get("data-event-price")
                or p_el.get_text(" ", strip=True)
            )
            if p_num:
                cls_str = " ".join(p_el.get("class") or []).lower()
                if "crossed" in cls_str or "normal" in cls_str:
                    reg_prices.append(p_num)
                else:
                    active_prices.append(p_num)

        best_p = min(active_prices) if active_prices else None
        list_p = max(reg_prices) if reg_prices else best_p
        img_u = _extract_best_img_from_element(pod, page_url)
        pod_text_low = pod.get_text(" ", strip=True).lower()
        in_stock = not (
            bool(pod.select_one(".out-of-stock, .pod-out-of-stock"))
            or any(tok in pod_text_low for tok in ("pronto disponible", "sin stock", "agotado", "no disponible"))
        )

        listing, reason = _finalize_candidate_listing(
            store=store,
            raw_sku=pod.get("data-key") or pod.get("data-sku"),
            raw_title=item_title,
            raw_brand=item_brand,
            price=best_p,
            original_price=list_p,
            raw_url=item_url,
            image_url=img_u,
            in_stock=in_stock,
            seller_name=seller_txt or _STORE_DISPLAY_SELLER_NAMES[store],
            category_spec=category_spec,
            page_url=page_url,
            is_broad_category=is_broad_category,
        )
        if listing:
            result.listings.append(listing)
        elif reason == "marketplace":
            result.discarded_marketplace += 1
        else:
            result.discarded_filtered += 1

    return result


def _extract_ripley_listings(
    html: str,
    page_url: str,
    category_spec: CategorySpec,
    is_broad_category: bool,
) -> ListingPageParseResult:
    """Extrae en bloque los productos 1P de Ripley desde `__NEXT_DATA__` (`findabilityProps`) o DOM."""
    result = ListingPageParseResult()
    soup = BeautifulSoup(html, "lxml")

    search_items: List[Dict[str, Any]] = []
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            data = json.loads(nd.string)
            pp = data.get("props", {}).get("pageProps", {})
            fp_prods = ((pp.get("findabilityProps") or {}).get("data") or {}).get("products")
            if isinstance(fp_prods, list) and fp_prods:
                search_items = [x for x in fp_prods if isinstance(x, dict)]
            elif isinstance(pp.get("results"), list) and pp.get("results"):
                search_items = [x for x in pp["results"] if isinstance(x, dict)]
            elif isinstance(pp.get("products"), list) and pp.get("products"):
                search_items = [x for x in pp["products"] if isinstance(x, dict)]
        except Exception as exc:
            logger.debug(f"Error parseando __NEXT_DATA__ listado en ripley: {exc}")

    if search_items:
        url_by_sku = _index_ripley_dom_links(soup, page_url)
        for item in search_items:
            result.raw_cards_seen += 1
            item_url = _build_ripley_item_url(item, url_by_sku, page_url)
            if not _is_ripley_search_item_official(item, item_url):
                result.discarded_marketplace += 1
                continue

            best_p, list_p = _extract_ripley_search_item_prices(item)
            if not best_p:
                result.discarded_filtered += 1
                continue

            in_stock = item.get("inStock") is not False and _is_ripley_node_in_stock(item) is not False
            img_u = None
            raw_primary = item.get("primaryImage")
            if isinstance(raw_primary, str):
                img_u = ensure_https_image_url(raw_primary, page_url=page_url)
            elif isinstance(raw_primary, dict):
                img_u = ensure_https_image_url(
                    raw_primary.get("src") or raw_primary.get("full") or raw_primary.get("url"),
                    page_url=page_url,
                )
            if not img_u:
                for cand_i in item.get("images") or []:
                    cand_s = (
                        cand_i.get("src") or cand_i.get("full") or cand_i.get("url")
                        if isinstance(cand_i, dict)
                        else cand_i
                    )
                    if isinstance(cand_s, str):
                        img_u = ensure_https_image_url(cand_s, page_url=page_url)
                        if img_u:
                            break

            raw_sku = str(
                item.get("partNumber") or item.get("parentProductID") or item.get("sku") or ""
            ).strip()
            seller_val = str(item.get("seller") or item.get("sellerName") or "Ripley").strip()

            listing, reason = _finalize_candidate_listing(
                store="ripley",
                raw_sku=raw_sku,
                raw_title=str(item.get("name") or item.get("displayName") or ""),
                raw_brand=str(item.get("brand") or ""),
                price=best_p,
                original_price=list_p,
                raw_url=item_url,
                image_url=img_u if isinstance(img_u, str) else None,
                in_stock=in_stock,
                seller_name=seller_val,
                category_spec=category_spec,
                page_url=page_url,
                is_broad_category=is_broad_category,
            )
            if listing:
                result.listings.append(listing)
            elif reason == "marketplace":
                result.discarded_marketplace += 1
            else:
                result.discarded_filtered += 1
        return result

    # Fallback DOM tarjetas Ripley
    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "aside, nav, header, footer, [class*='filter'], [class*='facet'], [id*='filter'], [class*='sidebar']"
    ):
        noise.decompose()

    for card in clean_soup.select(".catalog-product-item, [data-partnumber]"):
        link_el = card if card.name == "a" else card.select_one("a[href]")
        raw_href = str(link_el.get("href") or "").strip() if link_el else ""
        if not raw_href:
            continue
        result.raw_cards_seen += 1
        item_url = urljoin(page_url, raw_href)
        if not is_official_store_seller("ripley", str(card), item_url):
            result.discarded_marketplace += 1
            continue

        title_el = card.select_one(".catalog-product-details__name, .product-name, h2, h3")
        item_title = title_el.get_text(" ", strip=True) if title_el else card.get_text(" ", strip=True)
        card_prices: List[float] = []
        for sel in (".catalog-prices__card-price", ".catalog-prices__offer-price", ".catalog-prices__price"):
            for p_el in card.select(sel):
                p_num = clean_ripley_number(p_el.get_text(" ", strip=True))
                if p_num:
                    card_prices.append(p_num)
        best_p = min(card_prices) if card_prices else None
        list_el = card.select_one(".catalog-prices__list-price")
        list_p = clean_ripley_number(list_el.get_text(" ", strip=True)) if list_el else best_p
        img_u = _extract_best_img_from_element(card, page_url)
        card_text_low = card.get_text(" ", strip=True).lower()
        in_stock = not (
            bool(card.select_one(".out-of-stock, .product-out-of-stock, [class*='out-of-stock']"))
            or any(tok in card_text_low for tok in ("pronto disponible", "sin stock", "agotado", "no disponible"))
        )

        listing, reason = _finalize_candidate_listing(
            store="ripley",
            raw_sku=card.get("data-partnumber"),
            raw_title=item_title,
            raw_brand="",
            price=best_p,
            original_price=list_p,
            raw_url=item_url,
            image_url=img_u,
            in_stock=in_stock,
            seller_name="Ripley",
            category_spec=category_spec,
            page_url=page_url,
            is_broad_category=is_broad_category,
        )
        if listing:
            result.listings.append(listing)
        elif reason == "marketplace":
            result.discarded_marketplace += 1
        else:
            result.discarded_filtered += 1

    return result


def _extract_magento_card_seller(card: Tag) -> Optional[str]:
    for el in card.select(
        ".label-sold-by, .product-item-seller, .wk-seller, [class*='sold-by'], [class*='seller']"
    ):
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not txt:
            continue
        cleaned = re.sub(r"^(?:vendido\s+por|por)\s*[:\-]?\s*", "", txt, flags=re.I).strip()
        if cleaned:
            return cleaned
    return None


def _is_magento_card_official(store: str, card: Tag, item_url: str) -> Tuple[bool, str]:
    if is_marketplace_url(store, item_url):
        return (False, "")

    seller_txt = _extract_magento_card_seller(card)
    if seller_txt:
        s_low = seller_txt.lower()
        allowed = _MAGENTO_ALLOWED_SELLER_PREFIXES.get(store, (store,))
        if not any(pref in s_low for pref in allowed):
            return (False, seller_txt)

    if not is_official_store_seller(store, str(card), item_url):
        return (False, seller_txt or "")

    return (True, seller_txt or _STORE_DISPLAY_SELLER_NAMES.get(store, store.title()))


def _select_magento_listing_cards(store: str, soup: BeautifulSoup) -> List[Tag]:
    if store == "hiraoka":
        cards = _select_hiraoka_main_search_cards(soup)
        if cards:
            return cards

    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "header, nav, aside, footer, .block.upsell, .block.related, .block.crosssell, "
        "[data-content-type='products'], .widget.block-products-list, "
        ".owl-carousel, .slick-slider, .swiper, [class*='carousel'], [class*='banner']"
    ):
        noise.decompose()

    has_layout = bool(clean_soup.select_one("main, #maincontent, .column.main, .page-wrapper, .columns"))
    if has_layout:
        containers = clean_soup.select(
            "main .products.wrapper, #maincontent .products.wrapper, .column.main .products.wrapper, "
            "main .search.results, #maincontent .search.results, .column.main .search.results"
        )
    else:
        containers = [clean_soup]

    cards: List[Tag] = []
    seen_ids: Set[int] = set()
    for cont in containers:
        for card in cont.select("li.product-item") or cont.select(".product-item-info"):
            cid = id(card)
            if cid not in seen_ids:
                seen_ids.add(cid)
                cards.append(card)
    return cards


def _extract_magento_listings(
    store: str,
    html: str,
    page_url: str,
    category_spec: CategorySpec,
    is_broad_category: bool,
) -> ListingPageParseResult:
    """Extrae en bloque los productos 1P de Magento 2 (`efe`, `curacao`, `hiraoka`)."""
    result = ListingPageParseResult()
    soup = BeautifulSoup(html, "lxml")
    cards = _select_magento_listing_cards(store, soup)

    for card in cards:
        links = card.select("a.product-item-link")
        if not links:
            fallback_a = card.select_one("a[href]")
            if fallback_a:
                links = [fallback_a]
        if not links:
            continue

        item_title = ""
        card_brand = ""
        raw_href = ""
        for lk in links:
            txt = lk.get_text(" ", strip=True)
            href_cand = str(lk.get("href") or "").strip()
            if len(txt) > len(item_title):
                if item_title and not card_brand:
                    card_brand = item_title
                item_title = txt
                if href_cand:
                    raw_href = href_cand
            elif txt and not card_brand:
                card_brand = txt
            if not raw_href and href_cand:
                raw_href = href_cand

        if not card_brand:
            brand_el = card.select_one(".product-item-brand .brand-name, .brand-name, .product-brand")
            if brand_el:
                card_brand = brand_el.get_text(" ", strip=True)

        if not raw_href or not item_title:
            continue

        result.raw_cards_seen += 1
        item_url = urljoin(page_url, raw_href)

        is_1p, seller_label = _is_magento_card_official(store, card, item_url)
        if not is_1p:
            result.discarded_marketplace += 1
            continue

        price_el = card.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            ".special-price [data-price-amount], "
            ".hiraoka-online-price [data-price-amount], "
            "[data-price-amount], "
            '[data-price-type="finalPrice"] .price, '
            ".special-price .price, "
            ".hiraoka-online-price .price, "
            ".price-box .price"
        )
        best_p = (
            clean_hiraoka_number(price_el.get("data-price-amount") or price_el.get_text())
            if price_el
            else None
        )
        if not best_p:
            result.discarded_filtered += 1
            continue

        old_el = card.select_one(
            '[data-price-type="oldPrice"][data-price-amount], '
            ".old-price [data-price-amount], "
            '[data-price-type="oldPrice"] .price, '
            ".old-price .price"
        )
        old_p = (
            clean_hiraoka_number(old_el.get("data-price-amount") or old_el.get_text())
            if old_el
            else None
        )

        img_u = _extract_best_img_from_element(card, page_url)

        sku_val = (
            card.get("data-product-sku")
            or (card.select_one("[data-product-sku]") or {}).get("data-product-sku")
        )
        if not sku_val:
            code_match = re.search(r"c[oó]digo\s*[:#]?\s*([a-z0-9\-]+)", card.get_text(" ", strip=True), flags=re.I)
            if code_match:
                sku_val = code_match.group(1)
        if not sku_val:
            pbox = card.select_one(".price-box[data-product-id], [data-product-id]")
            if pbox and pbox.get("data-product-id"):
                sku_val = str(pbox["data-product-id"])

        card_text_low = card.get_text(" ", strip=True).lower()
        in_stock = not (
            bool(card.select_one(".stock.unavailable, .out-of-stock, .actions-primary .unavailable, button.tocart[disabled]"))
            or any(tok in card_text_low for tok in ("agotado", "sin stock", "pronto disponible", "no disponible"))
        )

        listing, reason = _finalize_candidate_listing(
            store=store,
            raw_sku=str(sku_val) if sku_val else None,
            raw_title=item_title,
            raw_brand=card_brand,
            price=best_p,
            original_price=old_p,
            raw_url=item_url,
            image_url=img_u,
            in_stock=in_stock,
            seller_name=seller_label,
            category_spec=category_spec,
            page_url=page_url,
            is_broad_category=is_broad_category,
        )
        if listing:
            result.listings.append(listing)
        elif reason == "marketplace":
            result.discarded_marketplace += 1
        else:
            result.discarded_filtered += 1

    return result


def _extract_vtex_listings(
    store: str,
    html_or_json: str,
    page_url: str,
    category_spec: CategorySpec,
    is_broad_category: bool,
) -> ListingPageParseResult:
    """Extrae en bloque productos 1P (`sellerId == '1'`) de VTEX Cencosud (`metro`, `wong`)."""
    result = ListingPageParseResult()
    stripped = (html_or_json or "").strip()

    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except Exception:
            return result
        items = payload if isinstance(payload, list) else [payload]

        for item_dict in items:
            if not isinstance(item_dict, dict):
                continue
            result.raw_cards_seen += 1

            raw_title = str(item_dict.get("productName") or item_dict.get("productTitle") or "").strip()
            raw_brand = str(item_dict.get("brand") or "").strip()
            raw_link = str(item_dict.get("link") or "").strip()
            if not raw_link and item_dict.get("linkText"):
                host = urlparse(page_url).netloc or ("www.metro.pe" if store == "metro" else "www.wong.pe")
                raw_link = f"https://{host}/{str(item_dict['linkText']).strip('/')}/p"
            if not raw_link:
                result.discarded_filtered += 1
                continue
            item_url = urljoin(page_url, raw_link)

            sku_list = item_dict.get("items") or []
            saw_any_seller = False
            best_1p_price: Optional[float] = None
            orig_1p_price: Optional[float] = None
            best_in_stock = False
            chosen_sku_id: Optional[str] = None
            chosen_ean: Optional[str] = None
            chosen_img: Optional[str] = None
            chosen_seller_name: Optional[str] = None

            fallback_1p_price: Optional[float] = None
            fallback_1p_orig: Optional[float] = None
            fallback_sku_id: Optional[str] = None

            for sku_item in sku_list:
                if not isinstance(sku_item, dict):
                    continue
                imgs = sku_item.get("images") or []
                sku_img = None
                for im_obj in imgs:
                    if isinstance(im_obj, dict):
                        cand_url = ensure_https_image_url(im_obj.get("imageUrl"), page_url=page_url)
                        if cand_url:
                            sku_img = cand_url
                            break
                if not chosen_img and sku_img:
                    chosen_img = sku_img

                sku_id = str(sku_item.get("itemId") or "").strip() or None
                sku_ean = str(sku_item.get("ean") or "").strip() or None
                if not chosen_ean and sku_ean:
                    chosen_ean = sku_ean

                for seller in sku_item.get("sellers") or []:
                    if not isinstance(seller, dict):
                        continue
                    saw_any_seller = True
                    sid = str(seller.get("sellerId") or "").strip()
                    if sid != "1":
                        continue

                    offer = seller.get("commertialOffer") or {}
                    avail_qty = offer.get("AvailableQuantity", 1)
                    is_avail_flag = offer.get("IsAvailable", True)
                    seller_in_stock = (avail_qty is None or int(avail_qty) > 0) and (is_avail_flag is not False)

                    p = clean_vtex_number(offer.get("Price") or offer.get("spotPrice"))
                    lp = clean_vtex_number(offer.get("ListPrice") or offer.get("PriceWithoutDiscount"))
                    if p and p > 0:
                        card_p = _extract_cencosud_card_price_from_offer(offer, p)
                        eff_p = min(p, card_p) if card_p else p
                        eff_lp = lp if (lp and lp > eff_p) else max(p, eff_p)

                        if seller_in_stock:
                            best_in_stock = True
                            if best_1p_price is None or eff_p < best_1p_price:
                                best_1p_price = eff_p
                                orig_1p_price = eff_lp
                                chosen_sku_id = sku_id
                                chosen_ean = sku_ean or chosen_ean
                                chosen_img = sku_img or chosen_img
                                chosen_seller_name = str(
                                    seller.get("sellerName") or _STORE_DISPLAY_SELLER_NAMES[store]
                                )
                        elif fallback_1p_price is None or eff_p < fallback_1p_price:
                            fallback_1p_price = eff_p
                            fallback_1p_orig = eff_lp
                            fallback_sku_id = sku_id

            if not best_1p_price and fallback_1p_price:
                best_1p_price = fallback_1p_price
                orig_1p_price = fallback_1p_orig
                chosen_sku_id = fallback_sku_id
                best_in_stock = False

            if best_1p_price is None:
                if saw_any_seller:
                    result.discarded_marketplace += 1
                else:
                    result.discarded_filtered += 1
                continue

            listing, reason = _finalize_candidate_listing(
                store=store,
                raw_sku=chosen_sku_id or str(item_dict.get("productId") or ""),
                raw_title=raw_title,
                raw_brand=raw_brand,
                price=best_1p_price,
                original_price=orig_1p_price,
                raw_url=item_url,
                image_url=chosen_img,
                in_stock=best_in_stock,
                seller_name=chosen_seller_name or _STORE_DISPLAY_SELLER_NAMES[store],
                category_spec=category_spec,
                page_url=page_url,
                is_broad_category=is_broad_category,
                explicit_mpn=str(item_dict.get("productReference") or "").strip() or None,
                explicit_ean=chosen_ean,
            )
            if listing:
                result.listings.append(listing)
            elif reason == "marketplace":
                result.discarded_marketplace += 1
            else:
                result.discarded_filtered += 1

        return result

    return result


def parse_category_listing_page(
    store: str,
    html_or_json: str,
    page_url: str,
    category_spec: CategorySpec,
    is_broad_category: bool = False,
) -> ListingPageParseResult:
    """
    Despacha el parseo en bloque hacia la estrategia de la tienda (`falabella`/`tottus`,
    `ripley`, `efe`/`curacao`/`hiraoka`, `metro`/`wong`) aplicando el filtro estricto 1P.
    """
    if not html_or_json or not html_or_json.strip():
        return ListingPageParseResult()

    s_id = (store or "").strip().lower()
    if s_id in {"falabella", "tottus"}:
        return _extract_falabella_group_listings(
            store=s_id,
            html=html_or_json,
            page_url=page_url,
            category_spec=category_spec,
            is_broad_category=is_broad_category,
        )
    if s_id == "ripley":
        return _extract_ripley_listings(
            html=html_or_json,
            page_url=page_url,
            category_spec=category_spec,
            is_broad_category=is_broad_category,
        )
    if s_id in {"efe", "curacao", "hiraoka"}:
        return _extract_magento_listings(
            store=s_id,
            html=html_or_json,
            page_url=page_url,
            category_spec=category_spec,
            is_broad_category=is_broad_category,
        )
    if s_id in {"metro", "wong"}:
        return _extract_vtex_listings(
            store=s_id,
            html_or_json=html_or_json,
            page_url=page_url,
            category_spec=category_spec,
            is_broad_category=is_broad_category,
        )

    raise ValueError(f"Tienda no soportada en category_crawler: {store!r}")


def _deduplicate_listing_batch(listings: Sequence[ScrapedListing]) -> List[ScrapedListing]:
    """Deduplica un lote por `(store, store_sku)` y `(store, url)`, conservando menor precio."""
    by_sku: Dict[Tuple[str, str], ScrapedListing] = {}
    by_url: Dict[Tuple[str, str], ScrapedListing] = {}

    for item in listings:
        sku_key = (item.store, item.store_sku)
        url_key = (item.store, item.url)

        prev_sku = by_sku.get(sku_key)
        prev_url = by_url.get(url_key)
        prev = prev_sku or prev_url
        if prev is not None and prev.price <= item.price:
            continue

        if prev is not None:
            by_sku.pop((prev.store, prev.store_sku), None)
            by_url.pop((prev.store, prev.url), None)

        by_sku[sku_key] = item
        by_url[url_key] = item

    return list(by_sku.values())


async def upsert_store_listings(
    session: AsyncSession,
    listings: Sequence[ScrapedListing],
) -> Tuple[int, int]:
    """
    Inserta o actualiza listings 1P en `store_listings` de manera idempotente:
    - Sin duplicados por `(store, store_sku)` ni `(store, url)`
    - Actualiza `price`, `original_price`, `in_stock`, `title`, `brand`, `category`,
      `normalized_signature`, `seller_name` y `last_seen_at`
    - Preserva intactos `first_seen_at` y `canonical_product_id`
    Retorna `(inserted_count, updated_count)`.
    """
    deduped = _deduplicate_listing_batch(listings)
    if not deduped:
        return (0, 0)

    by_store: Dict[str, List[ScrapedListing]] = {}
    for item in deduped:
        by_store.setdefault(item.store, []).append(item)

    now = utc_now_naive()
    inserted = 0
    updated = 0

    for store_id, store_items in by_store.items():
        skus = [it.store_sku for it in store_items]
        urls = [it.url for it in store_items]
        stmt = select(StoreListing).where(
            StoreListing.store == store_id,
            or_(StoreListing.store_sku.in_(skus), StoreListing.url.in_(urls)),
        )
        res = await session.execute(stmt)
        existing_rows = list(res.scalars().all())

        row_by_sku: Dict[str, StoreListing] = {r.store_sku: r for r in existing_rows}
        row_by_url: Dict[str, StoreListing] = {r.url: r for r in existing_rows}

        for item in store_items:
            existing = row_by_sku.get(item.store_sku) or row_by_url.get(item.url)
            if existing is not None:
                existing.category = item.category
                existing.title = item.title
                existing.brand = item.brand
                existing.price = item.price
                existing.original_price = item.original_price
                existing.currency = item.currency
                existing.in_stock = item.in_stock
                existing.seller_name = item.seller_name
                existing.normalized_signature = item.normalized_signature
                existing.last_seen_at = now
                if item.image_url:
                    existing.image_url = item.image_url
                if item.mpn:
                    existing.mpn = item.mpn
                if item.ean:
                    existing.ean = item.ean

                if item.url != existing.url and item.url not in row_by_url:
                    row_by_url.pop(existing.url, None)
                    existing.url = item.url
                    row_by_url[item.url] = existing
                if item.store_sku != existing.store_sku and item.store_sku not in row_by_sku:
                    row_by_sku.pop(existing.store_sku, None)
                    existing.store_sku = item.store_sku
                    row_by_sku[item.store_sku] = existing

                updated += 1
            else:
                new_row = StoreListing(
                    store=item.store,
                    store_sku=item.store_sku,
                    category=item.category,
                    title=item.title,
                    brand=item.brand,
                    price=item.price,
                    original_price=item.original_price,
                    currency=item.currency,
                    url=item.url,
                    image_url=item.image_url,
                    in_stock=item.in_stock,
                    seller_name=item.seller_name,
                    mpn=item.mpn,
                    ean=item.ean,
                    normalized_signature=item.normalized_signature,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(new_row)
                row_by_sku[item.store_sku] = new_row
                row_by_url[item.url] = new_row
                inserted += 1

    await session.commit()
    return (inserted, updated)


def _bump_bucket(bucket: Dict[str, Dict[str, int]], key: str, stats: SourceCrawlStats) -> None:
    if key not in bucket:
        bucket[key] = {
            "pages_fetched": 0,
            "extracted_1p": 0,
            "inserted": 0,
            "updated": 0,
            "discarded_marketplace": 0,
            "discarded_filtered": 0,
        }
    b = bucket[key]
    b["pages_fetched"] += stats.pages_fetched
    b["extracted_1p"] += stats.extracted_1p
    b["inserted"] += stats.inserted
    b["updated"] += stats.updated
    b["discarded_marketplace"] += stats.discarded_marketplace
    b["discarded_filtered"] += stats.discarded_filtered


async def crawl_categories(
    stores: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    max_pages: int = 2,
    dry_run: bool = False,
    session_factory: Optional[Callable[[], AsyncSession]] = None,
    fetch_fn: Optional[Callable[[str], Any]] = None,
    session: Optional[AsyncSession] = None,
) -> CategoryCrawlSummary:
    """
    Barre páginas de categorías tech para las tiendas y categorías indicadas,
    filtrando estrictamente vendedores 1P y haciendo upsert idempotente en `store_listings`
    (salvo cuando `dry_run=True`, en cuyo caso no escribe en base de datos).
    """
    if max_pages < 1:
        raise ValueError("max_pages debe ser >= 1.")

    eff_session_factory = session_factory or WriterSessionLocal
    eff_fetch_fn = fetch_fn or fetch_page
    target_stores = [s.strip().lower() for s in stores] if stores is not None else list(ALL_TECH_STORES)
    sources = get_store_category_sources(stores=target_stores, categories=categories)

    summary = CategoryCrawlSummary(dry_run=dry_run)
    all_listings: List[ScrapedListing] = []
    source_stats_map: Dict[Tuple[str, str], SourceCrawlStats] = {}

    for source in sources:
        spec = get_category_spec(source.category)
        if spec is None:
            continue

        key = (source.store, source.category)
        st = source_stats_map.get(key)
        if st is None:
            st = SourceCrawlStats(store=source.store, category=source.category)
            source_stats_map[key] = st
            summary.by_source.append(st)

        seen_in_source: Set[str] = set()
        source_listings: List[ScrapedListing] = []

        for page_num in range(1, max_pages + 1):
            page_url = build_paginated_category_url(source, page_num)
            try:
                raw_payload = await eff_fetch_fn(page_url)
            except Exception as exc:
                logger.warning(
                    f"Error descargando listado {source.store}/{source.category} p.{page_num} ({page_url}): {exc}"
                )
                break

            if not raw_payload:
                break

            st.pages_fetched += 1
            parsed = parse_category_listing_page(
                store=source.store,
                html_or_json=raw_payload,
                page_url=page_url,
                category_spec=spec,
                is_broad_category=source.is_broad_category,
            )

            st.raw_cards_seen += parsed.raw_cards_seen
            st.discarded_marketplace += parsed.discarded_marketplace
            st.discarded_filtered += parsed.discarded_filtered

            new_in_page = 0
            for item in parsed.listings:
                dedup_tok = f"{item.store_sku}|{item.url}"
                if dedup_tok in seen_in_source:
                    continue
                seen_in_source.add(dedup_tok)
                source_listings.append(item)
                new_in_page += 1

            if parsed.raw_cards_seen == 0 or new_in_page == 0:
                break

        st.extracted_1p += len(source_listings)
        all_listings.extend(source_listings)

    if not dry_run and all_listings:
        # Persistir por fuente para contabilizar inserted/updated exactos por (store, category)
        listings_by_src: Dict[Tuple[str, str], List[ScrapedListing]] = {}
        for item in all_listings:
            # Asociar al bucket (store, category) o al original si fue reclasificado
            b_key = (item.store, item.category)
            if b_key not in source_stats_map:
                # Buscar primera fuente de esa tienda si fue reclasificado desde categoría amplia
                b_key = next(
                    (k for k in source_stats_map if k[0] == item.store),
                    b_key,
                )
            listings_by_src.setdefault(b_key, []).append(item)

        async def _persist_with_session(target_session: AsyncSession) -> None:
            for b_key, src_items in listings_by_src.items():
                ins, upd = await upsert_store_listings(target_session, src_items)
                if b_key in source_stats_map:
                    source_stats_map[b_key].inserted += ins
                    source_stats_map[b_key].updated += upd
                else:
                    summary.inserted += ins
                    summary.updated += upd

        if session is not None:
            await _persist_with_session(session)
        else:
            async with eff_session_factory() as owned_session:
                await _persist_with_session(owned_session)

    summary.sources_processed = len(summary.by_source)
    summary.listings = all_listings

    for st in summary.by_source:
        summary.pages_fetched += st.pages_fetched
        summary.extracted_1p += st.extracted_1p
        summary.inserted += st.inserted
        summary.updated += st.updated
        summary.discarded_marketplace += st.discarded_marketplace
        summary.discarded_filtered += st.discarded_filtered
        _bump_bucket(summary.by_store, st.store, st)
        _bump_bucket(summary.by_category, st.category, st)

    return summary
