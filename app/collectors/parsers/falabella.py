"""
Extractor real de precios y metadatos para Falabella Perú (falabella.com.pe).
Extrae datos desde __NEXT_DATA__ (productData.variants.prices) y JSON-LD estructurado,
aislando el nodo del producto principal y validando resultados si proviene de búsquedas.
"""
import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.validators import validate_product_identity

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


def parse_falabella(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, precio actual, precio de lista e imagen oficial desde el HTML de Falabella.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    h1_el = soup.select_one("h1.jsx-product-name, .product-name h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

    # 1. Estrategia __NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})

            # Si es una página de resultados de búsqueda en __NEXT_DATA__, validar cada resultado
            search_results = props.get("results")
            if isinstance(search_results, list) and search_results and not props.get("productData"):
                if not canonical_title:
                    return None
                for item in search_results:
                    if not isinstance(item, dict):
                        continue
                    item_title = str(item.get("displayName") or item.get("name") or "").strip()
                    item_url = str(item.get("url") or offer_url).strip()
                    if not validate_product_identity(
                        canonical_title, item_title, item_url, store_id="falabella"
                    ):
                        continue
                    prices = item.get("prices", [])
                    extracted_p = []
                    orig_p = None
                    for p_item in prices:
                        p_val = p_item.get("price", [])
                        raw = p_val[0] if isinstance(p_val, list) and p_val else p_val
                        num = clean_number(raw)
                        if num:
                            extracted_p.append(num)
                            if p_item.get("type") == "normalPrice" or p_item.get("crossed"):
                                orig_p = num
                    if extracted_p:
                        best_p = min(extracted_p)
                        list_p = orig_p or max(extracted_p)
                        media_urls = item.get("mediaUrls", [])
                        img_u = media_urls[0] if isinstance(media_urls, list) and media_urls else None
                        return {
                            "title": item_title,
                            "price": best_p,
                            "original_price": list_p if list_p > best_p else best_p,
                            "image_url": img_u,
                            "offer_url": item_url,
                        }
                return None

            prod = props.get("productData", {}) or props.get("product", {})
            prod_title = str(prod.get("name") or prod.get("displayName") or h1_title).strip()
            variants = prod.get("variants", [])
            extracted_prices = []
            orig_price = None
            official_img = None

            if variants:
                v = variants[0]
                if not prod_title and v.get("name"):
                    prod_title = str(v["name"]).strip()
                prices = v.get("prices", [])
                for p_item in prices:
                    p_type = p_item.get("type", "")
                    p_val = p_item.get("price", [])
                    raw = p_val[0] if isinstance(p_val, list) and p_val else p_val
                    num = clean_number(raw)
                    if num:
                        extracted_prices.append(num)
                        if p_type == "normalPrice" or p_item.get("crossed"):
                            orig_price = num

                medias = v.get("medias", [])
                if medias and isinstance(medias[0], dict) and medias[0].get("url"):
                    official_img = medias[0]["url"]

            if extracted_prices:
                if canonical_title and not validate_product_identity(
                    canonical_title, prod_title, offer_url, store_id="falabella"
                ):
                    return None

                best_p = min(extracted_prices)
                list_p = orig_price or max(extracted_prices)
                return {
                    "title": prod_title,
                    "price": best_p,
                    "original_price": list_p if list_p > best_p else best_p,
                    "image_url": official_img,
                    "offer_url": offer_url,
                }
        except Exception as e:
            logger.debug(f"Error parseando __NEXT_DATA__ en Falabella: {e}")

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
