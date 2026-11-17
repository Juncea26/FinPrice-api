"""
Extractor real para Ripley Perú (simple.ripley.com.pe).
Extrae título real y precios desde __NEXT_DATA__ (detailProps.data.product.parentpricestock) y JSON-LD,
aislando el nodo del producto principal e ignorando carruseles de recomendados.
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.url_utils import canonicalize_store_url, is_valid_product_image_url
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

    for neg_bool_key in ("isOutOfStock", "outOfStock", "isUnavailable", "unavailable", "soldOut"):
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
            if isinstance(q_val, dict):
                nested = _is_ripley_node_in_stock(q_val, _depth + 1)
                if nested is False:
                    return False
            elif not isinstance(q_val, bool):
                try:
                    if float(q_val) <= 0:
                        return False
                except (TypeError, ValueError):
                    pass

    for avail_key in ("availability", "stockStatus", "status"):
        if avail_key in node and isinstance(node[avail_key], str):
            av_low = node[avail_key].strip().lower()
            if any(
                tok in av_low
                for tok in ("outofstock", "out_of_stock", "soldout", "discontinued", "unavailable", "sin stock", "agotado")
            ):
                return False

    if "parentpricestock" in node and isinstance(node["parentpricestock"], dict):
        pps_state = _is_ripley_node_in_stock(node["parentpricestock"], _depth + 1)
        if pps_state is False:
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
            if isinstance(q_val, dict):
                if _is_ripley_node_in_stock(q_val, _depth + 1) is True:
                    has_positive = True
            elif not isinstance(q_val, bool):
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
        return clean_number(
            raw_node.get("valueNumber")
            or raw_node.get("value")
            or raw_node.get("amount")
            or raw_node.get("price")
        )
    return clean_number(raw_node)


def _extract_prices_from_dict(price_dict: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not isinstance(price_dict, dict):
        return (None, None, None)

    ripley_p: Optional[float] = None
    for k_card in ("ripley", "card", "cardPrice", "ripleyPrice", "formattedCardPrice"):
        if k_card in price_dict and price_dict[k_card] is not None:
            cand = _extract_price_node_value(price_dict[k_card])
            if cand:
                ripley_p = cand
                break

    sale_p: Optional[float] = None
    for k_sale in ("sale", "offerPrice", "internet", "internetPrice", "formattedOfferPrice"):
        if k_sale in price_dict and price_dict[k_sale] is not None:
            cand = _extract_price_node_value(price_dict[k_sale])
            if cand:
                sale_p = cand
                break

    orig_p: Optional[float] = None
    for k_orig in ("master", "listPrice", "normalPrice", "formattedListPrice"):
        if k_orig in price_dict and price_dict[k_orig] is not None:
            cand = _extract_price_node_value(price_dict[k_orig])
            if cand:
                orig_p = cand
                break

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


def parse_ripley(
    html: str, offer_url: str, canonical_title: Optional[str] = None
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

    if not is_official_store_seller("ripley", html, offer_url):
        return None

    soup = BeautifulSoup(html, "lxml")

    # Eliminar carruseles de recomendados / relacionados en el DOM
    for carousel in soup.select(".carousel, .related-products, .product-carousel, aside, footer"):
        carousel.decompose()

    h1_el = soup.select_one("section.product-header h1, .product-info h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

    url_sku = _extract_url_sku_token(offer_url)
    ld_in_stock, ld_active_prices, ld_list_prices, ld_title_fallback = _extract_json_ld_info(soup, url_sku)

    # 1. Estrategia __NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})
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

    # 3. Selectores CSS aislados al contenedor de producto
    main_scope = soup.select_one(".product-info, .product-header, #product-page") or soup
    price_elem = main_scope.select_one(
        ".catalog-prices__card-price, .catalog-prices__offer-price, .product-price"
    )
    if price_elem:
        p = clean_number(price_elem.get_text())
        if p:
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
