"""
Extractor real para Ripley Perú (simple.ripley.com.pe).
Extrae título real y precios desde __NEXT_DATA__ (detailProps.data.product.parentpricestock) y JSON-LD,
aislando el nodo del producto principal e ignorando carruseles de recomendados.
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

logger = get_logger("parsers.ripley")


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


FORBIDDEN_ERROR_PHRASES_RIPLEY = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock",
    "pronto disponible",
    "sin stock disponible",
    "producto agotado",
)


def _extract_url_sku_token(offer_url: str) -> str:
    """Extrae el partNumber/SKU del final de una URL canónica de Ripley (ej. '2004367413754p')."""
    path = (offer_url or "").split("?", 1)[0].rstrip("/")
    if not path:
        return ""
    last_seg = path.rsplit("/", 1)[-1]
    m = re.search(r"-([0-9]+p?|[a-z0-9]+p)$", last_seg, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m2 = re.search(r"(\d{7,15}p?)$", last_seg, flags=re.IGNORECASE)
    return m2.group(1).lower() if m2 else ""


def _sku_matches_url(sku_node: Dict[str, Any], url_sku: str) -> bool:
    if not url_sku or not isinstance(sku_node, dict):
        return False
    url_base = url_sku.rstrip("p")
    for k in ("partNumber", "sku", "id", "uniqueID", "skuId", "catalogEntryId"):
        val = str(sku_node.get(k) or "").strip().lower()
        if not val:
            continue
        if val == url_sku or val.rstrip("p") == url_base:
            return True
    return False


def _is_ripley_node_in_stock(node: Any, _depth: int = 0) -> Optional[bool]:
    """
    Evalúa los campos reales de disponibilidad/stock en nodos JSON de Ripley
    (__NEXT_DATA__, __PRELOADED_STATE__, SKUs y parentpricestock).
    Retorna False si está explícitamente agotado, True si está disponible, o None si no hay campos de stock.
    """
    if not isinstance(node, dict) or _depth > 3:
        return None

    for neg_bool_key in (
        "isOutOfStock",
        "outOfStock",
        "out_of_stock",
        "isUnavailable",
        "unavailable",
        "soldOut",
        "notBuyable",
        "notSelectable",
    ):
        if neg_bool_key in node and node[neg_bool_key] is True:
            return False

    for pos_bool_key in ("buyable", "inStock", "in_stock", "isAvailable", "available", "active"):
        if pos_bool_key in node:
            val = node[pos_bool_key]
            if val is False or (isinstance(val, str) and val.strip().lower() in {"false", "0", "no"}):
                return False

    for qty_key in ("stock", "quantity", "availableQuantity", "stockQuantity", "inventory", "availableStock"):
        if qty_key in node and node[qty_key] is not None:
            q_val = node[qty_key]
            if isinstance(q_val, bool):
                if q_val is False:
                    return False
            elif isinstance(q_val, dict):
                nested = _is_ripley_node_in_stock(q_val, _depth + 1)
                if nested is False:
                    return False
            else:
                try:
                    if float(q_val) <= 0:
                        return False
                except (TypeError, ValueError):
                    pass

    for avail_key in ("availability", "stockStatus", "status", "statusUI", "badgeText", "stockMessage", "availabilityText"):
        if avail_key in node and isinstance(node[avail_key], str):
            av_low = node[avail_key].strip().lower()
            if any(
                tok in av_low
                for tok in (
                    "outofstock",
                    "out_of_stock",
                    "soldout",
                    "discontinued",
                    "unavailable",
                    "sin stock",
                    "agotado",
                    "pronto disponible",
                    "no disponible",
                )
            ):
                return False

    for list_key in ("badges", "flags", "ribbons", "tags", "labels"):
        badge_vals = node.get(list_key)
        if isinstance(badge_vals, list):
            joined_badges = " ".join(str(b) for b in badge_vals).lower()
            if any(tok in joined_badges for tok in ("sin stock", "agotado", "pronto disponible", "no disponible", "outofstock")):
                return False

    if "parentpricestock" in node and isinstance(node["parentpricestock"], dict):
        pps_state = _is_ripley_node_in_stock(node["parentpricestock"], _depth + 1)
        if pps_state is False:
            return False

    for var_key in ("variants", "skus"):
        var_list = node.get(var_key)
        if isinstance(var_list, list) and var_list and _depth < 2:
            var_states = [
                _is_ripley_node_in_stock(v, _depth + 1)
                for v in var_list
                if isinstance(v, dict)
            ]
            if var_states and all(vs is False for vs in var_states):
                return False

    has_positive = False
    for neg_bool_key in ("isOutOfStock", "outOfStock", "isUnavailable", "unavailable"):
        if neg_bool_key in node and node[neg_bool_key] is False:
            has_positive = True
    for pos_bool_key in ("buyable", "inStock", "in_stock", "isAvailable", "available"):
        if pos_bool_key in node:
            val = node[pos_bool_key]
            if val is True or (isinstance(val, str) and val.strip().lower() in {"true", "1", "yes"}):
                has_positive = True
    for qty_key in ("stock", "quantity", "availableQuantity", "stockQuantity", "inventory", "availableStock"):
        if qty_key in node and node[qty_key] is not None:
            q_val = node[qty_key]
            if isinstance(q_val, bool):
                if q_val is True:
                    has_positive = True
            elif isinstance(q_val, dict):
                if _is_ripley_node_in_stock(q_val, _depth + 1) is True:
                    has_positive = True
            else:
                try:
                    if float(q_val) > 0:
                        has_positive = True
                except (TypeError, ValueError):
                    pass
    for avail_key in ("availability", "stockStatus", "status"):
        if avail_key in node and isinstance(node[avail_key], str):
            av_low = node[avail_key].strip().lower()
            if any(tok in av_low for tok in ("instock", "in_stock", "available", "limitedavailability")):
                has_positive = True

    if has_positive:
        return True
    if "parentpricestock" in node and isinstance(node["parentpricestock"], dict):
        return _is_ripley_node_in_stock(node["parentpricestock"], _depth + 1)
    return None


def _extract_price_node_value(raw_node: Any) -> Optional[float]:
    if isinstance(raw_node, dict):
        if _is_ripley_node_in_stock(raw_node) is False:
            return None
        if (
            raw_node.get("crossed") is True
            or raw_node.get("isCrossed") is True
            or raw_node.get("strikethrough") is True
        ):
            return None
        return clean_number(
            raw_node.get("valueNumber")
            or raw_node.get("value")
            or raw_node.get("amount")
            or raw_node.get("price")
            or raw_node.get("formattedPrice")
        )
    return clean_number(raw_node)


def _extract_prices_from_dict(price_dict: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not isinstance(price_dict, dict):
        return (None, None, None)

    card_cands: List[float] = []
    for k_card in (
        "ripley",
        "card",
        "cardPrice",
        "cardPriceNumber",
        "ripleyPrice",
        "ripleyPriceNumber",
        "tarjetaRipley",
        "creditPrice",
        "creditCardPrice",
        "opex",
        "opexPrice",
        "opexPriceNumber",
        "promoPrice",
        "formattedCardPrice",
        "formattedRipleyPrice",
    ):
        if k_card in price_dict and price_dict[k_card] is not None:
            cand = _extract_price_node_value(price_dict[k_card])
            if cand and cand > 0:
                card_cands.append(cand)
    ripley_p: Optional[float] = min(card_cands) if card_cands else None

    sale_cands: List[float] = []
    for k_sale in (
        "sale",
        "salePrice",
        "salePriceNumber",
        "offer",
        "offerPrice",
        "offerPriceNumber",
        "internet",
        "internetPrice",
        "internetPriceNumber",
        "bestPrice",
        "priceNumber",
        "formattedOfferPrice",
    ):
        if k_sale in price_dict and price_dict[k_sale] is not None:
            cand = _extract_price_node_value(price_dict[k_sale])
            if cand and cand > 0:
                sale_cands.append(cand)
    sale_p: Optional[float] = min(sale_cands) if sale_cands else None

    orig_cands: List[float] = []
    for k_orig in (
        "master",
        "masterPrice",
        "masterPriceNumber",
        "list",
        "listPrice",
        "listPriceNumber",
        "normal",
        "normalPrice",
        "normalPriceNumber",
        "oldPrice",
        "formattedListPrice",
    ):
        if k_orig in price_dict and price_dict[k_orig] is not None:
            # Para precio de lista/normal sí aceptar aunque venga marcado como tachado (es el precio original)
            raw_v = price_dict[k_orig]
            if isinstance(raw_v, dict):
                cand = clean_number(
                    raw_v.get("valueNumber")
                    or raw_v.get("value")
                    or raw_v.get("amount")
                    or raw_v.get("price")
                )
            else:
                cand = clean_number(raw_v)
            if cand and cand > 0:
                orig_cands.append(cand)
    orig_p: Optional[float] = max(orig_cands) if orig_cands else None

    return (ripley_p, sale_p, orig_p)


def _extract_json_ld_info(
    soup: BeautifulSoup, url_sku: str
) -> Tuple[Optional[bool], List[float], List[float], str]:
    """
    Inspecciona JSON-LD (@type == 'Product') para validar offers.availability (InStock vs OutOfStock)
    y extraer precios activos sin mezclar variantes agotadas.
    """
    ld_avail_signals: List[bool] = []
    active_prices: List[float] = []
    list_prices: List[float] = []
    ld_title = ""

    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            candidates = []
            if isinstance(j, dict) and isinstance(j.get("@graph"), list):
                candidates.extend(j["@graph"])
            elif isinstance(j, list):
                candidates.extend(j)
            else:
                candidates.append(j)

            for item in candidates:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                if not ld_title and item.get("name"):
                    ld_title = str(item["name"]).strip()
                offers = item.get("offers", [])
                offers_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
                for off in offers_list:
                    if not isinstance(off, dict):
                        continue
                    off_sku = str(off.get("sku") or "").strip().lower()
                    if url_sku and off_sku and len(offers_list) > 1:
                        if off_sku != url_sku and off_sku.rstrip("p") != url_sku.rstrip("p"):
                            continue
                    avail_raw = str(off.get("availability") or "").strip().lower()
                    off_in_stock = True
                    if avail_raw:
                        if any(tok in avail_raw for tok in ("outofstock", "soldout", "discontinued")):
                            off_in_stock = False
                            ld_avail_signals.append(False)
                        elif any(tok in avail_raw for tok in ("instock", "limitedavailability", "onlineonly")):
                            off_in_stock = True
                            ld_avail_signals.append(True)
                    p = clean_number(off.get("price") or off.get("lowPrice"))
                    hp = clean_number(off.get("highPrice"))
                    if hp:
                        list_prices.append(hp)
                    if p and off_in_stock:
                        active_prices.append(p)
        except Exception:
            pass

    ld_in_stock: Optional[bool] = None
    if ld_avail_signals:
        ld_in_stock = any(ld_avail_signals)

    return (ld_in_stock, active_prices, list_prices, ld_title)


def _resolve_ripley_pricing_and_stock(
    prod: Dict[str, Any],
    offer_url: str,
    html: str,
    soup: BeautifulSoup,
    ld_in_stock: Optional[bool],
) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Resuelve el precio activo (cardPrice/offerPrice) y el estado real de stock para la variante
    de `offer_url`, priorizando los SKUs activos y precios vigentes sobre cachés agotadas.
    """
    url_sku = _extract_url_sku_token(offer_url)

    # 1. Evaluar SKUs / variantes si existen en el JSON
    raw_skus = prod.get("SKUs") or prod.get("skus") or prod.get("sKUs") or prod.get("variants") or []
    chosen_price_tuple: Optional[Tuple[Optional[float], Optional[float], Optional[float]]] = None
    sku_stock_signal: Optional[bool] = None

    if isinstance(raw_skus, list) and raw_skus:
        sku_dicts = [s for s in raw_skus if isinstance(s, dict)]
        if sku_dicts:
            url_matched_skus = [s for s in sku_dicts if _sku_matches_url(s, url_sku)] if url_sku else []
            if url_matched_skus:
                active_matched = [s for s in url_matched_skus if _is_ripley_node_in_stock(s) is not False]
                if not active_matched:
                    return (None, None, False)
                target_skus = active_matched
            else:
                active_skus = [s for s in sku_dicts if _is_ripley_node_in_stock(s) is not False]
                if not active_skus:
                    return (None, None, False)
                target_skus = active_skus

            best_sku_p: Optional[float] = None
            for s in target_skus:
                p_dict = (
                    s.get("prices")
                    or s.get("price")
                    or (s.get("parentpricestock") or {}).get("price")
                    or s
                )
                rip_p, sale_p, orig_p = _extract_prices_from_dict(p_dict)
                cands = [p for p in (rip_p, sale_p) if p is not None and p > 0]
                if cands:
                    cand_min = min(cands)
                    if best_sku_p is None or cand_min < best_sku_p:
                        best_sku_p = cand_min
                        chosen_price_tuple = (rip_p, sale_p, orig_p)
                        sku_stock_signal = _is_ripley_node_in_stock(s)

    # 2. Evaluar precios a nivel producto (priorizando `prod.prices` sobre caché `parentpricestock.price`)
    prod_stock_signal = _is_ripley_node_in_stock(prod)
    if prod_stock_signal is False:
        return (None, None, False)

    if chosen_price_tuple is None:
        direct_prices = prod.get("prices")
        pps = prod.get("parentpricestock")
        pps_prices = pps.get("price") if isinstance(pps, dict) else {}

        rip_d, sale_d, orig_d = _extract_prices_from_dict(direct_prices)
        if any(p is not None for p in (rip_d, sale_d)):
            chosen_price_tuple = (rip_d, sale_d, orig_d)
        else:
            chosen_price_tuple = _extract_prices_from_dict(pps_prices)

    ripley_p, sale_p, orig_p = chosen_price_tuple or (None, None, None)
    active_candidates = [p for p in (ripley_p, sale_p) if p is not None and p > 0]
    best_p = min(active_candidates) if active_candidates else None
    if best_p is None:
        return (None, None, False)

    all_candidates = [p for p in (orig_p, ripley_p, sale_p) if p is not None and p > 0]
    list_p = orig_p or (max(all_candidates) if all_candidates else best_p)
    if list_p < best_p:
        list_p = best_p

    # 3. Validación combinada de stock real (JSON + JSON-LD + HTML)
    is_in_stock = True
    if ld_in_stock is False or prod_stock_signal is False or sku_stock_signal is False:
        is_in_stock = False
    elif not check_is_in_stock("ripley", html, status_code=200, has_valid_price=True):
        is_in_stock = False
    elif soup.select_one(".out-of-stock, .product-out-of-stock, [data-testid='out-of-stock']") and not soup.select_one(
        ".btn-add-to-cart, [data-testid='add-to-cart'], button.add-to-cart"
    ):
        is_in_stock = False

    return (best_p, list_p, is_in_stock)


def _is_ripley_search_item_official(item: Dict[str, Any], item_url: str = "") -> bool:
    """
    Valida que un ítem de búsqueda de Ripley sea vendido 1P por Ripley,
    inspeccionando exclusivamente sus campos JSON estructurados y su URL.
    """
    if not isinstance(item, dict):
        return False
    if item_url and is_marketplace_url("ripley", item_url):
        return False

    parent_id = str(
        item.get("parentProductID") or item.get("partNumber") or item.get("sku") or ""
    ).strip().upper()
    if parent_id.startswith("PMP"):
        return False

    if item.get("isMarketplaceProduct") is True:
        return False

    seller_val = str(item.get("seller") or item.get("sellerName") or "").strip().lower()
    if seller_val and ("marketplace" in seller_val or "ripley" not in seller_val):
        return False

    mkt = item.get("marketplace")
    if isinstance(mkt, dict):
        m_name = str(mkt.get("shopName") or mkt.get("sellerName") or "").strip().lower()
        if m_name and "ripley" not in m_name and "ecsa" not in m_name:
            return False

    shop = item.get("shop")
    if isinstance(shop, dict) and not seller_val:
        s_id_num = str(shop.get("sellerId") or shop.get("id") or "").strip()
        s_name = str(shop.get("shopName") or "").strip().lower()
        if s_id_num not in {"", "1"} and "ripley" not in s_name and "ecsa" not in s_name:
            return False

    return True


def _index_ripley_dom_links(soup: BeautifulSoup, search_url: str) -> Dict[str, str]:
    """Mapea SKUs/partNumbers a enlaces reales dentro del área de resultados de Ripley (sin sidebars/nav)."""
    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "aside, nav, header, footer, [class*='filter'], [class*='facet'], [id*='filter'], [class*='sidebar']"
    ):
        noise.decompose()

    url_by_sku: Dict[str, str] = {}
    for a in clean_soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href or "/search" in href.lower():
            continue
        full_u = urljoin(search_url, href)
        _, clean_u = canonicalize_store_url(full_u)
        eff_u = clean_u or full_u
        tok = _extract_url_sku_token(eff_u)
        if tok:
            url_by_sku.setdefault(tok, eff_u)
            url_by_sku.setdefault(tok.rstrip("p"), eff_u)
    return url_by_sku


def _build_ripley_item_url(item: Dict[str, Any], url_by_sku: Dict[str, str], search_url: str) -> str:
    raw_u = str(item.get("url") or "").strip()
    if raw_u:
        full_u = urljoin(search_url, raw_u)
        _, clean_u = canonicalize_store_url(full_u)
        return clean_u or full_u

    for key in ("parentProductID", "partNumber", "sku"):
        tok = str(item.get(key) or "").strip().lower()
        if not tok:
            continue
        if tok in url_by_sku:
            return url_by_sku[tok]
        if tok.rstrip("p") in url_by_sku:
            return url_by_sku[tok.rstrip("p")]

    part_id = str(item.get("parentProductID") or item.get("partNumber") or item.get("sku") or "").strip().lower()
    if part_id and not part_id.endswith("p") and not part_id.startswith("pmp"):
        part_id = f"{part_id}p"
    raw_name = str(item.get("name") or "producto").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw_name).strip("-") or "producto"
    if part_id:
        return f"https://simple.ripley.com.pe/{slug}-{part_id}"
    return search_url


def _extract_ripley_search_item_prices(item: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extrae (best_active_price, list_price) de un ítem de búsqueda de Ripley."""
    active_cands: List[float] = []
    list_cands: List[float] = []

    p_dict = item.get("prices") or (item.get("parentpricestock") or {}).get("price")
    if isinstance(p_dict, dict):
        rip_p, sale_p, orig_p = _extract_prices_from_dict(p_dict)
        for cand in (rip_p, sale_p):
            if cand and cand > 0:
                active_cands.append(cand)
        if orig_p and orig_p > 0:
            list_cands.append(orig_p)

    for k_act in (
        "cardPriceNumber",
        "ripleyPriceNumber",
        "creditPriceNumber",
        "opexPriceNumber",
        "cardPrice",
        "ripleyPrice",
        "tarjetaRipley",
        "creditPrice",
        "creditCardPrice",
        "opexPrice",
        "salePriceNumber",
        "internetPriceNumber",
        "offerPrice",
        "internetPrice",
        "priceNumber",
        "price",
    ):
        val = clean_number(item.get(k_act))
        if val and val > 0:
            active_cands.append(val)

    for k_orig in (
        "masterPriceNumber",
        "listPriceNumber",
        "normalPriceNumber",
        "oldPrice",
        "masterPrice",
        "listPrice",
        "normalPrice",
    ):
        val = clean_number(item.get(k_orig))
        if val and val > 0:
            list_cands.append(val)

    if not active_cands:
        return (None, None)
    best_p = min(active_cands)
    list_p = max(list_cands) if list_cands else best_p
    if list_p < best_p:
        list_p = best_p
    return (best_p, list_p)


def _parse_ripley_search_results(
    soup: BeautifulSoup,
    next_data: Optional[Dict[str, Any]],
    search_url: str,
    canonical_title: Optional[str],
    seen_candidate_urls: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extrae el mejor candidato 1P oficial desde resultados de búsqueda en Ripley
    (`findabilityProps.data.products` o tarjetas DOM individuales), ignorando el sidebar de filtros.
    """
    if not canonical_title:
        return None

    local_seen = seen_candidate_urls if seen_candidate_urls is not None else set()
    best_candidate: Optional[Dict[str, Any]] = None

    # Estrategia A: JSON estructurado de búsqueda en __NEXT_DATA__
    search_items: List[Dict[str, Any]] = []
    if isinstance(next_data, dict):
        page_props = next_data.get("props", {}).get("pageProps", {})
        fp_prods = ((page_props.get("findabilityProps") or {}).get("data") or {}).get("products")
        if isinstance(fp_prods, list) and fp_prods:
            search_items = [x for x in fp_prods if isinstance(x, dict)]
        elif isinstance(page_props.get("results"), list) and page_props.get("results"):
            search_items = [x for x in page_props["results"] if isinstance(x, dict)]
        elif isinstance(page_props.get("products"), list) and page_props.get("products"):
            search_items = [x for x in page_props["products"] if isinstance(x, dict)]

    if search_items:
        url_by_sku = _index_ripley_dom_links(soup, search_url)
        for item in search_items:
            if item.get("inStock") is False or _is_ripley_node_in_stock(item) is False:
                continue
            item_url = _build_ripley_item_url(item, url_by_sku, search_url)
            if not _is_ripley_search_item_official(item, item_url):
                continue

            dedup_key = f"ripley:{item_url.rstrip('/').lower()}"
            if dedup_key in local_seen:
                continue
            local_seen.add(dedup_key)

            item_brand = str(item.get("brand") or "").strip()
            item_name = str(item.get("name") or item.get("displayName") or "").strip()
            full_title = (
                f"{item_brand} {item_name}".strip()
                if item_brand and item_name and item_brand.lower() not in item_name.lower()
                else item_name
            )
            if not full_title:
                continue
            item_desc = str(item.get("description") or item.get("shortDescription") or "").strip()
            if not validate_product_identity(
                canonical_title,
                full_title,
                item_url,
                store_id="ripley",
                description=item_desc,
            ):
                continue

            best_p, list_p = _extract_ripley_search_item_prices(item)
            if not best_p:
                continue

            img_u = item.get("primaryImage")
            if not img_u:
                imgs = item.get("images") or []
                img_u = imgs[0] if isinstance(imgs, list) and imgs else None
            if isinstance(img_u, dict):
                img_u = img_u.get("src") or img_u.get("full") or img_u.get("url")
            if isinstance(img_u, str) and img_u.startswith("//"):
                img_u = f"https:{img_u}"

            cand = {
                "title": full_title,
                "brand": item_brand,
                "price": best_p,
                "original_price": list_p if (list_p and list_p > best_p) else best_p,
                "image_url": img_u if is_valid_product_image_url(img_u) else None,
                "offer_url": item_url,
                "description": item_desc,
                "in_stock": True,
            }
            if best_candidate is None or best_p < best_candidate["price"]:
                best_candidate = cand
        return best_candidate

    # Estrategia B: Fallback DOM por tarjeta individual (sin leer facetas ni sidebar)
    clean_soup = BeautifulSoup(str(soup), "lxml")
    for noise in clean_soup.select(
        "aside, nav, header, footer, [class*='filter'], [class*='facet'], [id*='filter'], [class*='sidebar']"
    ):
        noise.decompose()

    cards = clean_soup.select(".catalog-product-item, [data-partnumber]")
    for card in cards:
        if card.select_one(".out-of-stock, .product-out-of-stock"):
            continue
        link_el = card if card.name == "a" else card.select_one("a[href]")
        raw_href = str(link_el.get("href") or "").strip() if link_el else ""
        if not raw_href:
            continue
        full_u = urljoin(search_url, raw_href)
        _, clean_u = canonicalize_store_url(full_u)
        item_url = clean_u or full_u
        if is_marketplace_url("ripley", item_url):
            continue

        dedup_key = f"ripley:{item_url.rstrip('/').lower()}"
        if dedup_key in local_seen:
            continue
        local_seen.add(dedup_key)

        if not is_official_store_seller("ripley", str(card), item_url):
            continue

        title_el = card.select_one(".catalog-product-details__name, .product-name, h2, h3")
        item_title = title_el.get_text(" ", strip=True) if title_el else card.get_text(" ", strip=True)
        if not item_title or not validate_product_identity(canonical_title, item_title, item_url, store_id="ripley"):
            continue

        card_p_list: List[float] = []
        for sel in (".catalog-prices__card-price", ".catalog-prices__offer-price", ".catalog-prices__price"):
            for p_el in card.select(sel):
                p_num = clean_number(p_el.get_text(" ", strip=True))
                if p_num:
                    card_p_list.append(p_num)
        if not card_p_list:
            continue
        best_p = min(card_p_list)
        list_el = card.select_one(".catalog-prices__list-price")
        list_p = clean_number(list_el.get_text(" ", strip=True)) if list_el else best_p
        img_el = card.select_one("img")
        img_u = (img_el.get("src") or img_el.get("data-src")) if img_el else None

        cand = {
            "title": item_title,
            "price": best_p,
            "original_price": list_p if (list_p and list_p > best_p) else best_p,
            "image_url": img_u if is_valid_product_image_url(img_u) else None,
            "offer_url": item_url,
            "in_stock": True,
        }
        if best_candidate is None or best_p < best_candidate["price"]:
            best_candidate = cand

    return best_candidate


def parse_ripley(
    html: str,
    offer_url: str,
    canonical_title: Optional[str] = None,
    seen_candidate_urls: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, el menor precio vigente (Tarjeta Ripley o Internet), precio lista e imagen oficial de Ripley.
    """
    if not html:
        return None

    vis_html = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ).lower()
    if any(phrase in vis_html for phrase in FORBIDDEN_ERROR_PHRASES_RIPLEY):
        return None

    _, clean_offer_url = canonicalize_store_url(offer_url)
    offer_url = clean_offer_url or offer_url
    is_search_url = any(seg in offer_url.lower() for seg in ("/search/", "/search?", "/buscar", "?q=", "&q="))

    soup = BeautifulSoup(html, "lxml")

    # Eliminar carruseles de recomendados / relacionados en el DOM
    for carousel in soup.select(".carousel, .related-products, .product-carousel, aside, footer"):
        carousel.decompose()

    h1_el = soup.select_one("section.product-header h1, .product-info h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

    url_sku = _extract_url_sku_token(offer_url)
    ld_in_stock, ld_active_prices, ld_list_prices, ld_title_fallback = _extract_json_ld_info(soup, url_sku)

    # 1. Estrategia __NEXT_DATA__
    next_data_obj: Optional[Dict[str, Any]] = None
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            next_data_obj = json.loads(next_script.string)
        except Exception as e:
            logger.debug(f"Error parseando __NEXT_DATA__ en Ripley: {e}")

    if isinstance(next_data_obj, dict):
        props = next_data_obj.get("props", {}).get("pageProps", {})
        prod = (
            props.get("detailProps", {}).get("data", {}).get("product", {})
            or props.get("product", {})
        )
        findability_prods = ((props.get("findabilityProps") or {}).get("data") or {}).get("products")
        if (is_search_url or (isinstance(findability_prods, list) and not prod)) and not prod:
            return _parse_ripley_search_results(
                soup=soup,
                next_data=next_data_obj,
                search_url=offer_url,
                canonical_title=canonical_title,
                seen_candidate_urls=seen_candidate_urls,
            )

    if is_search_url and not (
        isinstance(next_data_obj, dict)
        and (
            next_data_obj.get("props", {}).get("pageProps", {}).get("detailProps", {}).get("data", {}).get("product")
            or next_data_obj.get("props", {}).get("pageProps", {}).get("product")
        )
    ):
        return _parse_ripley_search_results(
            soup=soup,
            next_data=next_data_obj,
            search_url=offer_url,
            canonical_title=canonical_title,
            seen_candidate_urls=seen_candidate_urls,
        )

    if not is_official_store_seller("ripley", html, offer_url):
        return None

    if isinstance(next_data_obj, dict):
        try:
            props = next_data_obj.get("props", {}).get("pageProps", {})
            prod = (
                props.get("detailProps", {}).get("data", {}).get("product", {})
                or props.get("product", {})
            )
            if isinstance(prod, dict) and prod:
                prod_brand = str(prod.get("brand") or "").strip()
                prod_title = str(prod.get("name") or h1_title or ld_title_fallback).strip()
                if prod_brand and prod_title and prod_brand.lower() not in prod_title.lower():
                    prod_title = f"{prod_brand} {prod_title}".strip()

                best_p, list_p, is_in_stock = _resolve_ripley_pricing_and_stock(
                    prod=prod,
                    offer_url=offer_url,
                    html=html,
                    soup=soup,
                    ld_in_stock=ld_in_stock,
                )

                if not is_in_stock:
                    return None

                official_img = None
                images = prod.get("images", [])
                if images and isinstance(images, list):
                    official_img = images[0]
                elif prod.get("primaryImage"):
                    official_img = prod.get("primaryImage")
                if isinstance(official_img, dict):
                    official_img = official_img.get("src") or official_img.get("full") or official_img.get("url")
                if isinstance(official_img, str) and official_img.startswith("//"):
                    official_img = f"https:{official_img}"

                if best_p is not None and is_in_stock:
                    prod_desc = str(
                        prod.get("description") or prod.get("longDescription") or prod.get("shortDescription") or ""
                    ).strip()
                    extracted_meta = extract_product_specs(html, title=prod_title, store_id="ripley")
                    if canonical_title and not validate_product_identity(
                        canonical_title,
                        prod_title,
                        offer_url,
                        store_id="ripley",
                        tech_specs=extracted_meta["tech_specs"],
                        description=prod_desc,
                    ):
                        return None

                    return {
                        "title": prod_title,
                        "price": best_p,
                        "original_price": list_p if (list_p and list_p > best_p) else best_p,
                        "image_url": official_img,
                        "offer_url": offer_url,
                        "brand": extracted_meta["brand"] or prod_brand,
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                        "description": prod_desc,
                        "in_stock": is_in_stock,
                    }
        except Exception as e:
            logger.debug(f"Error parseando __NEXT_DATA__ en Ripley: {e}")

    # 1b. Estrategia window.__PRELOADED_STATE__.product.product
    preloaded_match = re.search(
        r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*(?:;|</script>)",
        html,
        flags=re.DOTALL,
    )
    if preloaded_match:
        try:
            state = json.loads(preloaded_match.group(1))
            prod = state.get("product", {}).get("product", {}) or state.get("product", {})
            if isinstance(prod, dict) and prod:
                prod_brand = str(prod.get("brand") or "").strip()
                prod_title = str(prod.get("name") or h1_title or ld_title_fallback).strip()
                if prod_brand and prod_title and prod_brand.lower() not in prod_title.lower():
                    prod_title = f"{prod_brand} {prod_title}".strip()
                prod_desc = str(prod.get("description") or prod.get("shortDescription") or "").strip()

                best_p, list_p, is_in_stock = _resolve_ripley_pricing_and_stock(
                    prod=prod,
                    offer_url=offer_url,
                    html=html,
                    soup=soup,
                    ld_in_stock=ld_in_stock,
                )

                if not is_in_stock:
                    return None

                if best_p is not None and is_in_stock:
                    extracted_meta = extract_product_specs(html, title=prod_title, store_id="ripley")
                    if canonical_title and not validate_product_identity(
                        canonical_title,
                        prod_title,
                        offer_url,
                        store_id="ripley",
                        tech_specs=extracted_meta["tech_specs"],
                        description=prod_desc,
                    ):
                        return None
                    imgs = prod.get("images") or []
                    img_u = imgs[0] if isinstance(imgs, list) and imgs else prod.get("fullImage")
                    if isinstance(img_u, dict):
                        img_u = img_u.get("src") or img_u.get("full") or img_u.get("url")
                    if isinstance(img_u, str) and img_u.startswith("//"):
                        img_u = f"https:{img_u}"
                    return {
                        "title": prod_title,
                        "price": best_p,
                        "original_price": list_p if (list_p and list_p > best_p) else best_p,
                        "image_url": img_u,
                        "offer_url": offer_url,
                        "brand": extracted_meta["brand"] or prod_brand,
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                        "description": prod_desc,
                        "in_stock": is_in_stock,
                    }
        except Exception as e:
            logger.debug(f"Error parseando __PRELOADED_STATE__ en Ripley: {e}")

    # 2. Estrategia JSON-LD (validando offers.availability)
    if ld_active_prices:
        if ld_in_stock is False or not check_is_in_stock("ripley", html, status_code=200, has_valid_price=True):
            return None
        ld_title = ld_title_fallback or h1_title
        if canonical_title and not validate_product_identity(
            canonical_title, ld_title, offer_url, store_id="ripley"
        ):
            return None
        best_ld_p = min(ld_active_prices)
        orig_ld_p = max(ld_list_prices or ld_active_prices)
        og_img = soup.find("meta", property="og:image")
        return {
            "title": ld_title,
            "price": best_ld_p,
            "original_price": orig_ld_p if orig_ld_p > best_ld_p else best_ld_p,
            "image_url": og_img.get("content") if og_img else None,
            "offer_url": offer_url,
            "in_stock": True,
        }

    # 3. Selectores CSS aislados al contenedor de producto (siempre el menor precio promocional no tachado)
    main_scope = soup.select_one(".product-info, .product-header, #product-page") or soup
    css_active_prices: List[float] = []
    for sel in (
        ".catalog-prices__card-price",
        ".catalog-prices__offer-price",
        ".product-price:not(.catalog-prices__list-price)",
    ):
        for price_elem in main_scope.select(sel):
            if price_elem.find_parent(["del", "s"]) is not None:
                continue
            p_cand = clean_number(price_elem.get_text(" ", strip=True))
            if p_cand and p_cand > 0:
                css_active_prices.append(p_cand)

    if css_active_prices:
        p = min(css_active_prices)
        if ld_in_stock is False or not check_is_in_stock("ripley", html, status_code=200, has_valid_price=True):
            return None
        list_elem = main_scope.select_one(".catalog-prices__list-price")
        orig = clean_number(list_elem.get_text()) if list_elem else p
        og_img = soup.find("meta", property="og:image")

        if canonical_title and not validate_product_identity(
            canonical_title, h1_title, offer_url, store_id="ripley"
        ):
            return None

        return {
            "title": h1_title,
            "price": p,
            "original_price": orig if orig and orig > p else p,
            "image_url": og_img.get("content") if og_img else None,
            "offer_url": offer_url,
            "in_stock": True,
        }

    return None
