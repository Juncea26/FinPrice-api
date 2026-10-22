"""
Extractor real para Conecta Retail (Tiendas Efe y La Curacao).
Soporta tiendas basadas en Magento 2 mediante data-price-amount, JSON-LD y selectores de precio.
"""
import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger("parsers.conectaretail")


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


def parse_conectaretail(html: str, offer_url: str) -> Optional[Dict[str, Any]]:
    """
    Extrae precio real, precio original e imagen oficial desde efe.com.pe o lacuracao.pe.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. Estrategia Magento 2: data-price-amount
    price_span = soup.select_one("[data-price-amount]")
    if price_span and price_span.get("data-price-amount"):
        current_p = clean_number(price_span["data-price-amount"])
        if current_p:
            # Buscar precio antiguo tachado si existe
            old_span = soup.select_one(".old-price [data-price-amount]")
            old_p = clean_number(old_span.get("data-price-amount")) if old_span else None

            # Imagen oficial
            og_img = soup.find("meta", property="og:image")
            img_url = og_img.get("content") if og_img else None

            return {
                "price": current_p,
                "original_price": old_p if (old_p and old_p > current_p) else current_p,
                "image_url": img_url,
                "offer_url": offer_url,
            }

    # 2. Estrategia JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            if j.get("@type") == "Product":
                offers = j.get("offers")
                if isinstance(offers, dict):
                    p = clean_number(offers.get("price"))
                    if p:
                        return {
                            "price": p,
                            "original_price": clean_number(offers.get("highPrice")) or p,
                            "image_url": j.get("image") if isinstance(j.get("image"), str) else None,
                            "offer_url": offer_url,
                        }
        except Exception:
            pass

    # 3. Selectores CSS de respaldo
    price_text_elem = soup.select_one(".special-price .price, .price-wrapper .price, .final-price .price")
    if price_text_elem:
        p = clean_number(price_text_elem.get_text())
        if p:
            old_text_elem = soup.select_one(".old-price .price")
            old_p = clean_number(old_text_elem.get_text()) if old_text_elem else None
            og_img = soup.find("meta", property="og:image")
            return {
                "price": p,
                "original_price": old_p if (old_p and old_p > p) else p,
                "image_url": og_img.get("content") if og_img else None,
                "offer_url": offer_url,
            }

    return None
