"""
Extractor real para Hiraoka Perú (hiraoka.com.pe).
Extrae precios desde Magento 2 JSON-LD (SalePrice / ListPrice) y meta tags product:price:amount.
"""
import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger("parsers.hiraoka")


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


def parse_hiraoka(html: str, offer_url: str) -> Optional[Dict[str, Any]]:
    """
    Extrae precio oferta, precio de lista e imagen oficial de Hiraoka.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. Estrategia JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            if j.get("@type") == "Product":
                offers = j.get("offers", [])
                offers_list = offers if isinstance(offers, list) else [offers]
                prices_found = []
                sale_price = None
                list_price = None

                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            prices_found.append(p)
                        price_spec = off.get("priceSpecification", {})
                        if isinstance(price_spec, dict):
                            p_type = price_spec.get("priceType", "")
                            spec_price = clean_number(price_spec.get("price"))
                            if "SalePrice" in p_type and spec_price:
                                sale_price = spec_price
                            elif "ListPrice" in p_type and spec_price:
                                list_price = spec_price

                official_img = j.get("image")
                if isinstance(official_img, list) and official_img:
                    official_img = official_img[0]

                if prices_found or sale_price:
                    best = sale_price or min(prices_found)
                    orig = list_price or max(prices_found)
                    return {
                        "price": best,
                        "original_price": orig if orig and orig > best else best,
                        "image_url": official_img if isinstance(official_img, str) else None,
                        "offer_url": offer_url,
                    }
        except Exception as e:
            logger.debug(f"Error parseando JSON-LD en Hiraoka: {e}")

    # 2. Estrategia Meta tags Open Graph
    meta_price = soup.find("meta", property="product:price:amount")
    if meta_price and meta_price.get("content"):
        p = clean_number(meta_price["content"])
        if p:
            og_img = soup.find("meta", property="og:image")
            return {
                "price": p,
                "original_price": p,
                "image_url": og_img.get("content") if og_img else None,
                "offer_url": offer_url,
            }

    # 3. Selectores CSS Magento 2
    price_elem = soup.select_one(".special-price .price, [data-price-type='finalPrice'] .price, .price-box .price")
    if price_elem:
        p = clean_number(price_elem.get_text())
        if p:
            old_elem = soup.select_one(".old-price .price, [data-price-type='oldPrice'] .price")
            orig = clean_number(old_elem.get_text()) if old_elem else p
            og_img = soup.find("meta", property="og:image")
            return {
                "price": p,
                "original_price": orig if orig and orig > p else p,
                "image_url": og_img.get("content") if og_img else None,
                "offer_url": offer_url,
            }

    return None
