"""
Extractor real de precios y metadatos para Falabella Perú (falabella.com.pe).
Extrae datos desde __NEXT_DATA__ (productData.variants.prices) y JSON-LD estructurado,
aislando el nodo del producto principal y validando resultados si proviene de búsquedas.
"""
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.url_utils import canonicalize_store_url, is_marketplace_url, is_valid_product_image_url
from app.collectors.validators import check_is_in_stock, is_official_store_seller, validate_product_identity

logger = get_logger("parsers.falabella")


def clean_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return round(float(val), 2) if float(val) > 0 else None
    s = str(val).strip()
    s = re.sub(r"[^\d.,]", "", s).strip(".,")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "")
    try:
        f = float(s)
        return round(f, 2) if f > 0 else None
    except ValueError:
        return None


def extract_falabella_prices(prices_list: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    """
    Extrae (lowest_active_price, list_price) de Falabella / Tottus:
    - Toma TODOS los precios de venta vigentes no tachados (incluyendo cmrPrice, eventPriceCMR,
      internetPrice, onlinePrice, eventPrice) y retorna min(active_prices) como mejor precio.
    - Toma el precio regular/normal tachado más alto (normalPrice o crossed=True) como list_price.
    """
    active_prices: List[float] = []
    regular_prices: List[float] = []
    all_prices: List[float] = []

    for p_item in prices_list:
        if not isinstance(p_item, dict):
            continue
        p_type = str(p_item.get("type", "")).lower()
        p_label = str(p_item.get("label", "")).lower()
        is_crossed = bool(p_item.get("crossed", False))

        p_val = p_item.get("price", [])
        if isinstance(p_val, list):
            parsed_nums = [clean_number(x) for x in p_val]
            valid_nums = [n for n in parsed_nums if n is not None]
            num = min(valid_nums) if valid_nums else None
        else:
            num = clean_number(p_val)
        if not num:
            continue

        all_prices.append(num)
        if (
            is_crossed
            or any(tok in p_type for tok in ("normal", "list", "regular"))
            or any(tok in p_label for tok in ("lista", "normal", "antes", "regular"))
        ):
            regular_prices.append(num)
        else:
            active_prices.append(num)

    best_p = min(active_prices) if active_prices else (min(all_prices) if all_prices else None)
    list_p = max(regular_prices) if regular_prices else (max(all_prices) if all_prices else best_p)

    if list_p and best_p and list_p < best_p:
        list_p = best_p

    return best_p, list_p


def _is_falabella_item_official(item: Dict[str, Any], eff_store: str) -> bool:
    """
    Valida el vendedor directamente desde los campos estructurados del ítem o variante
    (`sellerName`, `sellerId`, `seller`, `offerings`), sin contaminarse con filtros laterales.
    """
    if not isinstance(item, dict):
        return False
    if item.get("isMarketplace") is True:
        return False

    expected_tok = "tottus" if eff_store == "tottus" else "falabella"
    direct_sellers: List[str] = []
    for key in ("sellerName", "sellerId"):
        val = item.get(key)
        if val is not None and str(val).strip():
            direct_sellers.append(str(val).strip().lower())

    seller_obj = item.get("seller")
    if isinstance(seller_obj, dict):
        for key in ("name", "sellerName", "id", "sellerId"):
            val = seller_obj.get(key)
            if val is not None and str(val).strip():
                direct_sellers.append(str(val).strip().lower())
    elif isinstance(seller_obj, str) and seller_obj.strip():
        direct_sellers.append(seller_obj.strip().lower())

    if direct_sellers:
        return any(expected_tok in s for s in direct_sellers)

    offering_sellers: List[str] = []
    for off in item.get("offerings") or item.get("offers") or []:
        if not isinstance(off, dict):
            continue
        for key in ("sellerName", "sellerId"):
            val = off.get(key)
            if val is not None and str(val).strip():
                offering_sellers.append(str(val).strip().lower())
    if offering_sellers:
        return any(expected_tok in s for s in offering_sellers)

    return True


def _is_falabella_variant_available(v_obj: Dict[str, Any]) -> bool:
    """Verifica disponibilidad comercial de una variante cuando el payload declara flags de stock."""
    if not isinstance(v_obj, dict):
        return False
    if v_obj.get("isPurchaseable") is False:
        return False
    delivery_flags = [
        v_obj.get("isOnlineSellable"),
        v_obj.get("isHDAvailable"),
        v_obj.get("isCCAvailable"),
    ]
    if all(flag is False for flag in delivery_flags):
        return False
    return True


FORBIDDEN_ERROR_PHRASES_FALABELLA = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock",
)


def _parse_falabella_dom_search_cards(
    soup: BeautifulSoup,
    offer_url: str,
    eff_store: str,
    canonical_title: Optional[str],
    local_seen: Set[str],
) -> Optional[Dict[str, Any]]:
    """Fallback de tarjetas DOM en búsquedas de Falabella/Tottus evaluando vendedor solo dentro de cada pod."""
    if not canonical_title:
        return None

    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "aside, nav, header, footer, [class*='filter'], [class*='facet'], [id*='filter'], [class*='sidebar']"
    ):
        noise.decompose()

    pods = clean_soup.select(
        ".search-results--products .pod, [data-pod='catalyst-pod'], div.pod, article.pod-item"
    )
    best_candidate: Optional[Dict[str, Any]] = None
    for pod in pods:
        link_el = pod.select_one("a[href*='/product/'], a[href*='/articulo/'], a[href]")
        if not link_el:
            continue
        raw_href = str(link_el.get("href") or "").strip()
        if not raw_href:
            continue
        full_href = urljoin(offer_url, raw_href)
        _, clean_item_url = canonicalize_store_url(full_href)
        item_url = clean_item_url or full_href
        if is_marketplace_url(eff_store, item_url):
            continue

        dedup_key = f"{eff_store}:{item_url.rstrip('/').lower()}"
        if dedup_key in local_seen:
            continue
        local_seen.add(dedup_key)

        seller_el = pod.select_one(".pod-sellerText, [id*='displaySellerText'], [class*='seller']")
        if seller_el:
            seller_txt = seller_el.get_text(" ", strip=True).lower()
            if seller_txt and not is_official_store_seller(eff_store, seller_txt, item_url):
                continue
        elif not is_official_store_seller(eff_store, str(pod), item_url):
            continue

        title_el = pod.select_one(".pod-subTitle, [class*='subTitle'], [data-testid='pod-title'], b.title, h2, h3")
        brand_el = pod.select_one(".pod-title, [class*='brand']")
        item_title = title_el.get_text(" ", strip=True) if title_el else link_el.get_text(" ", strip=True)
        item_brand = brand_el.get_text(" ", strip=True) if brand_el else ""
        full_title = (
            f"{item_brand} {item_title}".strip()
            if item_brand and item_brand.lower() not in item_title.lower()
            else item_title
        )
        if not full_title or not validate_product_identity(canonical_title, full_title, item_url, store_id=eff_store):
            continue

        active_p_list: List[float] = []
        reg_p_list: List[float] = []
        for p_el in pod.select("[data-cmr-price], [data-internet-price], [data-event-price], .prices-0 span, .copy10"):
            p_num = clean_number(
                p_el.get("data-cmr-price")
                or p_el.get("data-internet-price")
                or p_el.get("data-event-price")
                or p_el.get_text(" ", strip=True)
            )
            if p_num:
                cls_str = " ".join(p_el.get("class") or []).lower()
                if "crossed" in cls_str or "normal" in cls_str:
                    reg_p_list.append(p_num)
                else:
                    active_p_list.append(p_num)
        if not active_p_list:
            continue
        best_p = min(active_p_list)
        list_p = max(reg_p_list) if reg_p_list else best_p
        img_el = pod.select_one("img")
        img_u = (img_el.get("src") or img_el.get("data-src")) if img_el else None
        cand = {
            "title": full_title,
            "brand": item_brand,
            "price": best_p,
            "original_price": list_p if list_p > best_p else best_p,
            "image_url": img_u,
            "offer_url": item_url,
            "in_stock": True,
        }
        if best_candidate is None or best_p < best_candidate["price"]:
            best_candidate = cand

    return best_candidate


def parse_falabella(
    html: str,
    offer_url: str,
    canonical_title: Optional[str] = None,
    seen_candidate_urls: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, precio más bajo vigente (incluyendo CMR/Internet), precio de lista e imagen oficial desde el HTML de Falabella.
    """
    if not html:
        return None

    vis_html = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ).lower()
    if any(phrase in vis_html for phrase in FORBIDDEN_ERROR_PHRASES_FALABELLA):
        return None

    detected_store, clean_offer_url = canonicalize_store_url(offer_url)
    offer_url = clean_offer_url or offer_url
    eff_store = "tottus" if detected_store == "tottus" else "falabella"
    is_search_url = any(seg in offer_url.lower() for seg in ("/search", "/buscar", "ntt="))
    local_seen = seen_candidate_urls if seen_candidate_urls is not None else set()

    soup = BeautifulSoup(html, "lxml")
    h1_el = soup.select_one("h1.jsx-product-name, .product-name h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

    # 1. Estrategia __NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})

            # Si es una página de resultados de búsqueda en __NEXT_DATA__, validar vendedor por ítem y elegir el menor precio vigente
            search_results = props.get("results")
            if isinstance(search_results, list) and search_results and not props.get("productData"):
                if not canonical_title:
                    return None
                best_search_candidate: Optional[Dict[str, Any]] = None
                for item in search_results:
                    if not isinstance(item, dict):
                        continue
                    if not _is_falabella_item_official(item, eff_store):
                        continue
                    item_brand = str(item.get("brand") or "").strip()
                    item_title = str(item.get("displayName") or item.get("name") or "").strip()
                    full_item_title = (
                        f"{item_brand} {item_title}".strip()
                        if item_brand and item_brand.lower() not in item_title.lower()
                        else item_title
                    )
                    raw_item_url = str(item.get("url") or offer_url).strip()
                    item_sku_id = str(item.get("skuId") or "").strip()
                    if item_sku_id and re.match(
                        r"^https?://[^/]+/(?:falabella-pe|tottus-pe)/(?:product|articulo)/[^/]+/[^/?#]+/?$",
                        raw_item_url,
                        flags=re.IGNORECASE,
                    ):
                        raw_item_url = f"{raw_item_url.rstrip('/')}/{item_sku_id}"
                    _, clean_item_url = canonicalize_store_url(raw_item_url)
                    item_url = clean_item_url or raw_item_url
                    if is_marketplace_url(eff_store, item_url):
                        continue

                    dedup_key = f"{eff_store}:{item_url.rstrip('/').lower()}"
                    if dedup_key in local_seen:
                        continue
                    local_seen.add(dedup_key)

                    if not validate_product_identity(
                        canonical_title, full_item_title, item_url, store_id=eff_store
                    ):
                        continue
                    prices = item.get("prices", [])
                    best_p, list_p = extract_falabella_prices(prices)
                    if best_p:
                        media_urls = item.get("mediaUrls", [])
                        img_u = media_urls[0] if isinstance(media_urls, list) and media_urls else None
                        cand_dict = {
                            "title": full_item_title,
                            "brand": item_brand,
                            "price": best_p,
                            "original_price": list_p if (list_p and list_p > best_p) else best_p,
                            "image_url": img_u,
                            "offer_url": item_url,
                            "in_stock": True,
                        }
                        if best_search_candidate is None or best_p < best_search_candidate["price"]:
                            best_search_candidate = cand_dict
                return best_search_candidate

            prod = props.get("productData", {}) or props.get("product", {})
            if is_search_url and not prod:
                return _parse_falabella_dom_search_cards(
                    soup, offer_url, eff_store, canonical_title, local_seen
                )

            if not is_official_store_seller(eff_store, html, offer_url):
                return None

            prod_brand = str(prod.get("brandName") or prod.get("brand") or "").strip()
            prod_title = str(prod.get("name") or prod.get("displayName") or h1_title).strip()
            if prod_brand and prod_title and prod_brand.lower() not in prod_title.lower():
                prod_title = f"{prod_brand} {prod_title}".strip()

            # Si offer_url era una URL de búsqueda que redirigió directamente a la ficha del producto, extraer la URL canónica real
            if is_search_url:
                canon_link = soup.find("link", rel="canonical")
                og_url_meta = soup.find("meta", property="og:url")
                redirected_u = (
                    (canon_link.get("href") if canon_link else None)
                    or (og_url_meta.get("content") if og_url_meta else None)
                )
                if redirected_u and not any(seg in str(redirected_u).lower() for seg in ("/search", "/buscar", "ntt=")):
                    _, clean_red = canonicalize_store_url(str(redirected_u))
                    offer_url = clean_red or str(redirected_u)
            prod_desc = " ".join(
                filter(
                    None,
                    [
                        str(prod.get("description") or "").strip(),
                        str(prod.get("longDescription") or "").strip(),
                    ],
                )
            )
            variants = prod.get("variants", [])
            variant_best_p: Optional[float] = None
            variant_list_p: Optional[float] = None
            official_img = None
            variant_name = ""
            variant_id = ""

            if not variants and prod.get("prices"):
                variant_best_p, variant_list_p = extract_falabella_prices(prod.get("prices", []))

            if variants and isinstance(variants, list):
                # Multi-SKU & Multi-Color Variant Resolution:
                # Evaluar TODAS las variantes (todos los colores) oficiales y disponibles que cumplan la capacidad buscada
                # y seleccionar la que tenga el PRECIO MÁS BARATO.
                url_parts = [p for p in offer_url.split("/") if p]
                url_tail_sku = url_parts[-1] if len(url_parts) >= 6 else ""

                req_storage_tok = None
                if canonical_title:
                    m_st = re.search(r"\b(\d{2,4}\s*(?:GB|TB))\b", canonical_title, flags=re.IGNORECASE)
                    if m_st:
                        req_storage_tok = re.sub(r"\s+", "", m_st.group(1)).lower()

                all_storage_tokens = {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}

                def _variant_min_price(v_obj: Dict[str, Any]) -> Optional[float]:
                    b_p, _ = extract_falabella_prices(v_obj.get("prices", []) or [])
                    return b_p

                official_variants = [
                    v_c for v_c in variants if isinstance(v_c, dict) and _is_falabella_item_official(v_c, eff_store)
                ]
                available_variants = [v_c for v_c in official_variants if _is_falabella_variant_available(v_c)]
                if official_variants and not available_variants and all(
                    v_c.get("isPurchaseable") is False for v_c in official_variants
                ):
                    return None
                candidate_variants = available_variants or official_variants

                priced_variants = [
                    v_c for v_c in candidate_variants if _variant_min_price(v_c) is not None
                ]

                matching_capacity_variants = []
                if req_storage_tok and priced_variants:
                    # 1. Variantes que declaran explícitamente la capacidad buscada (ej. 128gb)
                    explicit_cap = [
                        v_c
                        for v_c in priced_variants
                        if req_storage_tok in json.dumps(v_c, ensure_ascii=False).lower().replace(" ", "")
                    ]
                    if explicit_cap:
                        matching_capacity_variants = explicit_cap
                    else:
                        # 2. Variantes que no declaran una capacidad conflictiva distinta
                        other_caps = all_storage_tokens - {req_storage_tok}
                        matching_capacity_variants = [
                            v_c
                            for v_c in priced_variants
                            if not any(
                                oc in json.dumps(v_c, ensure_ascii=False).lower().replace(" ", "")
                                for oc in other_caps
                            )
                        ]
                else:
                    matching_capacity_variants = priced_variants

                selected_v = None
                if matching_capacity_variants:
                    # Ordenar por menor precio vigente; en caso de empate de precio, priorizar el SKU de la URL
                    matching_capacity_variants.sort(
                        key=lambda v_c: (
                            _variant_min_price(v_c) or float("inf"),
                            0 if str(v_c.get("id") or "") == url_tail_sku else 1,
                        )
                    )
                    selected_v = matching_capacity_variants[0]
                elif priced_variants:
                    selected_v = priced_variants[0]
                elif candidate_variants:
                    selected_v = candidate_variants[0]
                else:
                    selected_v = variants[0]

                v = selected_v
                variant_id = str(v.get("id") or "").strip()
                variant_name = str(v.get("name") or "").strip()
                if not prod_title and variant_name:
                    prod_title = variant_name

                prices = v.get("prices", [])
                variant_best_p, variant_list_p = extract_falabella_prices(prices)

                medias = v.get("medias", []) or prod.get("medias", [])
                if medias and isinstance(medias[0], dict) and medias[0].get("url"):
                    official_img = str(medias[0]["url"])
                    if "media.falabella.com" in official_img and official_img.endswith("/public"):
                        official_img = official_img[:-7] + "/w=800,h=800,fit=pad"

                # Si la variante tiene SKU ID explícito y la URL tiene formato /product/{id}/{slug}/{sku}, actualizar al SKU de la variante
                if variant_id:
                    m_url = re.match(
                        r"^(https://www\.(?:falabella|tottus)\.com\.pe/(?:falabella-pe|tottus-pe)/(?:product|articulo)/[^/]+/[^/]+)(?:/[^/?#]+)?$",
                        offer_url,
                    )
                    if m_url:
                        offer_url = f"{m_url.group(1)}/{variant_id}"
                    elif is_search_url:
                        prod_id = str(prod.get("id") or variant_id).strip()
                        slug = re.sub(r"[^a-z0-9]+", "-", prod_title.lower()).strip("-") or "producto"
                        if eff_store == "tottus":
                            offer_url = f"https://www.tottus.com.pe/tottus-pe/articulo/{prod_id}/{slug}/{variant_id}"
                        else:
                            offer_url = f"https://www.falabella.com.pe/falabella-pe/product/{prod_id}/{slug}/{variant_id}"

            if variant_best_p is not None:
                if not check_is_in_stock(eff_store, html, status_code=200, has_valid_price=True):
                    return None
                full_desc = " ".join(filter(None, [prod_desc, variant_name])).strip()
                extracted_meta = extract_product_specs(
                    html,
                    title=f"{prod_title} {variant_name}".strip(),
                    store_id="tottus" if "tottus.com.pe" in offer_url else "falabella",
                )
                if canonical_title and not validate_product_identity(
                    canonical_title,
                    prod_title,
                    offer_url,
                    store_id="tottus" if "tottus.com.pe" in offer_url else "falabella",
                    tech_specs=extracted_meta["tech_specs"],
                    description=full_desc,
                ):
                    return None

                return {
                    "title": prod_title,
                    "price": variant_best_p,
                    "original_price": variant_list_p if (variant_list_p and variant_list_p > variant_best_p) else variant_best_p,
                    "image_url": official_img,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"] or prod_brand,
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                    "description": full_desc,
                    "variant_sku_id": variant_id,
                    "in_stock": True,
                }
        except Exception as e:
            logger.debug(f"Error parseando __NEXT_DATA__ en Falabella: {e}")

    if is_search_url:
        return _parse_falabella_dom_search_cards(
            soup, offer_url, eff_store, canonical_title, local_seen
        )

    if not is_official_store_seller(eff_store, html, offer_url):
        return None

    # 2. Estrategia JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            if isinstance(j, dict) and j.get("@type") == "Product":
                ld_title = str(j.get("name") or h1_title).strip()
                offers = j.get("offers", [])
                offers_list = offers if isinstance(offers, list) else [offers]
                prices_found = []
                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            prices_found.append(p)
                if prices_found:
                    if canonical_title and not validate_product_identity(
                        canonical_title, ld_title, offer_url, store_id="falabella"
                    ):
                        return None

                    return {
                        "title": ld_title,
                        "price": min(prices_found),
                        "original_price": max(prices_found),
                        "image_url": j.get("image") if isinstance(j.get("image"), str) else None,
                        "offer_url": offer_url,
                    }
        except Exception:
            pass

    return None
