"""
Extractor real de precios y metadatos para Falabella Perú (falabella.com.pe).
Extrae datos desde __NEXT_DATA__ (productData.variants.prices) y JSON-LD estructurado.
"""
import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from app.core.logging import get_logger

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


def parse_falabella(html: str, offer_url: str) -> Optional[Dict[str, Any]]:
    """
    Extrae precio actual, precio de lista e imagen oficial desde el HTML de Falabella.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. Estrategia __NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})
            prod = props.get("productData", {}) or props.get("product", {})
            variants = prod.get("variants", [])
            extracted_prices = []
            orig_price = None
            official_img = None

            if variants:
                v = variants[0]
                # Buscar precios en v.prices
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

                # Imagen oficial
                medias = v.get("medias", [])
                if medias and isinstance(medias[0], dict) and medias[0].get("url"):
                    official_img = medias[0]["url"]

            if extracted_prices:
                best_p = min(extracted_prices)
                list_p = orig_price or max(extracted_prices)
                return {
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
            if j.get("@type") == "Product":
                offers = j.get("offers", [])
                offers_list = offers if isinstance(offers, list) else [offers]
                prices_found = []
                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            prices_found.append(p)
                if prices_found:
                    return {
                        "price": min(prices_found),
                        "original_price": max(prices_found),
                        "image_url": j.get("image") if isinstance(j.get("image"), str) else None,
                        "offer_url": offer_url,
                    }
        except Exception:
            pass

    return None
