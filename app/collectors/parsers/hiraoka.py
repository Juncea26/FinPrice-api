"""
Extractor real para Hiraoka Perú (hiraoka.com.pe).
Extrae título real, precios desde Magento 2 JSON-LD (SalePrice / ListPrice) y contenedor .product-info-main,
aislando completamente los carruseles de productos relacionados (.block.related, .block.upsell).
"""
import json
import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag

from app.core.logging import get_logger
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.validators import validate_product_identity

logger = get_logger("parsers.hiraoka")

CAROUSEL_AND_RELATED_SELECTORS = (
    ".block.upsell, .block.related, .block.crosssell, "
    ".products-upsell, .products-related, .products-crosssell, "
    "[data-content-type='products'], .widget.block-products-list, "
    "aside, footer, nav"
)


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


def _extract_main_h1_title(soup: BeautifulSoup) -> str:
    h1_span = soup.select_one(
        'h1.page-title span[data-ui-id="page-title-wrapper"], '
        "h1.page-title span.base, "
        ".product-info-main h1.page-title, "
        "h1.page-title"
    )
    if h1_span:
        return h1_span.get_text(strip=True)
    return ""


def _parse_search_results(
    soup: BeautifulSoup, search_url: str, canonical_title: Optional[str]
) -> Optional[Dict[str, Any]]:
    """
    Itera sobre resultados de búsqueda en Hiraoka y selecciona únicamente aquel cuyo título
    apruebe validate_product_identity(canonical_title, item_title, item_url).
    """
    if not canonical_title:
        logger.warning(f"Búsqueda en {search_url} rechazada: se requiere canonical_title.")
        return None

    cards = soup.select(".product-item-info, li.product-item")
    for card in cards:
        # En Hiraoka puede haber un primer link con la marca y un segundo con el nombre del producto
        links = card.select("a.product-item-link")
        item_title = ""
        item_url = search_url
        for lk in links:
            txt = lk.get_text(strip=True)
            if len(txt) > len(item_title):
                item_title = txt
                raw_href = lk.get("href") or ""
                item_url = urljoin(search_url, raw_href) if raw_href else search_url

        if not item_title:
            continue

        if not validate_product_identity(canonical_title, item_title, item_url, store_id="hiraoka"):
            continue

        price_el = card.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            ".special-price [data-price-amount], "
            "[data-price-amount], "
            '[data-price-type="finalPrice"] .price, '
            ".special-price .price"
        )
        if not price_el:
            continue

        raw_price = price_el.get("data-price-amount") or price_el.get_text()
        current_p = clean_number(raw_price)
        if not current_p:
            continue

        old_el = card.select_one(
            '[data-price-type="oldPrice"][data-price-amount], '
            ".old-price [data-price-amount], "
            '[data-price-type="oldPrice"] .price, '
            ".old-price .price"
        )
        raw_old = (old_el.get("data-price-amount") or old_el.get_text()) if old_el else None
        old_p = clean_number(raw_old)

        img_el = card.select_one("img.product-image-photo, img")
        img_url = (img_el.get("src") or img_el.get("data-src")) if img_el else None

        return {
            "title": item_title,
            "price": current_p,
            "original_price": old_p if (old_p and old_p > current_p) else current_p,
            "image_url": img_url,
            "offer_url": item_url,
        }

    return None


def parse_hiraoka(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, precio oferta, precio de lista e imagen oficial de Hiraoka.
    Aísla el contenedor .product-info-main y el JSON-LD principal ignorando carruseles.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    is_search_url = "/catalogsearch/result" in offer_url or "?q=" in offer_url or "&q=" in offer_url
    if not is_search_url:
        _, clean_offer_url = canonicalize_store_url(offer_url)
        offer_url = clean_offer_url or offer_url
    main_info_box: Optional[Tag] = soup.select_one(".product-info-main")

    if is_search_url or (not main_info_box and soup.select(".product-item-info, li.product-item")):
        return _parse_search_results(soup, offer_url, canonical_title)

    # Eliminar carruseles de productos relacionados, upsell y crosssell
    for unwanted in soup.select(CAROUSEL_AND_RELATED_SELECTORS):
        unwanted.decompose()

    h1_title = _extract_main_h1_title(soup)
    extracted_meta = extract_product_specs(html, title=h1_title, store_id="hiraoka")
    desc_el = soup.select_one(
        ".product.attribute.description .value, "
        ".product.attribute.overview .value, "
        ".product.attribute.description, "
        ".product.attribute.overview"
    )
    meta_desc = soup.find("meta", attrs={"name": "description"})
    page_desc = (
        desc_el.get_text(" ", strip=True)
        if desc_el
        else (str(meta_desc.get("content") or "").strip() if meta_desc else "")
    )

    # 1. Estrategia JSON-LD del Producto Principal
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            items = j if isinstance(j, list) else [j]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue

                ld_name = str(item.get("name") or "").strip()
                effective_title = h1_title or ld_name
                if h1_title and ld_name and h1_title.lower()[:12] not in ld_name.lower() and ld_name.lower()[:12] not in h1_title.lower():
                    continue

                offers = item.get("offers", [])
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

                official_img = item.get("image")
                if isinstance(official_img, list) and official_img:
                    official_img = official_img[0]

                if prices_found or sale_price:
                    best = sale_price or min(prices_found)
                    orig = list_price or max(prices_found)

                    if not h1_title and effective_title:
                        extracted_meta = extract_product_specs(
                            html, title=effective_title, store_id="hiraoka"
                        )
                    ld_desc = str(item.get("description") or page_desc).strip()
                    if canonical_title and not validate_product_identity(
                        canonical_title,
                        effective_title,
                        offer_url,
                        store_id="hiraoka",
                        tech_specs=extracted_meta["tech_specs"],
                        description=ld_desc,
                    ):
                        return None

                    return {
                        "title": effective_title,
                        "price": best,
                        "original_price": orig if orig and orig > best else best,
                        "image_url": official_img if isinstance(official_img, str) else None,
                        "offer_url": offer_url,
                        "brand": extracted_meta["brand"],
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                        "description": ld_desc,
                    }
        except Exception as e:
            logger.debug(f"Error parseando JSON-LD en Hiraoka: {e}")

    # Determinar el alcance de precios en el DOM principal
    has_full_page_layout = bool(soup.select_one(".page-wrapper, #maincontent, .columns"))
    if main_info_box is not None:
        price_scope: Optional[Tag] = main_info_box
    elif not has_full_page_layout:
        price_scope = soup
    else:
        price_scope = None

    # 2. Selectores CSS Magento 2 estrictamente dentro de .product-info-main
    if price_scope is not None:
        price_elem = price_scope.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            '[data-price-type="finalPrice"] .price, '
            ".special-price .price, "
            ".price-box .price"
        )
        if price_elem:
            raw_p = price_elem.get("data-price-amount") or price_elem.get_text()
            p = clean_number(raw_p)
            if p:
                old_elem = price_scope.select_one(
                    '[data-price-type="oldPrice"][data-price-amount], '
                    '[data-price-type="oldPrice"] .price, '
                    ".old-price .price"
                )
                raw_old = (old_elem.get("data-price-amount") or old_elem.get_text()) if old_elem else None
                orig = clean_number(raw_old) or p
                og_img = soup.find("meta", property="og:image")

                if canonical_title and not validate_product_identity(
                    canonical_title, h1_title, offer_url, store_id="hiraoka"
                ):
                    return None

                return {
                    "title": h1_title,
                    "price": p,
                    "original_price": orig if orig and orig > p else p,
                    "image_url": og_img.get("content") if og_img else None,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"],
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                }

    # 3. Estrategia Meta tags Open Graph de la ficha de producto
    meta_price = soup.find("meta", property="product:price:amount")
    if meta_price and meta_price.get("content"):
        p = clean_number(meta_price["content"])
        if p:
            og_img = soup.find("meta", property="og:image")
            og_title_el = soup.find("meta", property="og:title")
            effective_title = h1_title or (og_title_el.get("content") if og_title_el else "")

            if canonical_title and not validate_product_identity(
                canonical_title, str(effective_title), offer_url, store_id="hiraoka"
            ):
                return None

            return {
                "title": str(effective_title),
                "price": p,
                "original_price": p,
                "image_url": og_img.get("content") if og_img else None,
                "offer_url": offer_url,
            }

    return None
