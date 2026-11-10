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
from app.collectors.url_utils import canonicalize_store_url, is_valid_product_image_url
from app.collectors.validators import check_is_in_stock, is_official_store_seller, validate_product_identity

logger = get_logger("parsers.hiraoka")

CAROUSEL_AND_RELATED_SELECTORS = (
    ".block.upsell, .block.related, .block.crosssell, "
    ".products-upsell, .products-related, .products-crosssell, "
    "[data-content-type='products'], .widget.block-products-list, "
    ".warranty, .garantia, .garantia-extendida, .asistencia-plus, "
    "[class*='warranty'], [class*='garantia'], [id*='warranty'], [id*='garantia'], "
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
    Itera sobre TODOS los resultados de búsqueda en Hiraoka (todos los colores disponibles),
    filtra aquellos que aprueben validate_product_identity(canonical_title, item_title, item_url)
    y selecciona el que tenga el MENOR precio vigente.
    """
    if not canonical_title:
        logger.warning(f"Búsqueda en {search_url} rechazada: se requiere canonical_title.")
        return None

    best_candidate: Optional[Dict[str, Any]] = None
    cards = soup.select(".product-item-info, li.product-item")
    for card in cards:
        if card.select_one(".stock.unavailable"):
            continue
        # En Hiraoka puede haber un primer link con la marca y un segundo con el nombre del producto
        links = card.select("a.product-item-link")
        item_title = ""
        card_brand = ""
        item_url = search_url
        for lk in links:
            txt = lk.get_text(strip=True)
            if len(txt) > len(item_title):
                if item_title and not card_brand:
                    card_brand = item_title
                item_title = txt
                raw_href = lk.get("href") or ""
                item_url = urljoin(search_url, raw_href) if raw_href else search_url
            elif txt and not card_brand:
                card_brand = txt

        if not item_title:
            continue

        if card_brand and card_brand.lower() not in item_title.lower():
            item_title = f"{card_brand} {item_title}".strip()

        _, clean_card_url = canonicalize_store_url(item_url)
        item_url = clean_card_url or item_url

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

        cand = {
            "title": item_title,
            "brand": card_brand,
            "price": current_p,
            "original_price": old_p if (old_p and old_p > current_p) else current_p,
            "image_url": img_url,
            "offer_url": item_url,
            "in_stock": True,
        }
        if best_candidate is None or current_p < best_candidate["price"]:
            best_candidate = cand

    return best_candidate


FORBIDDEN_ERROR_PHRASES_HIRAOKA = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock",
)


def parse_hiraoka(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, el menor precio de venta vigente (PRECIO ONLINE / Especial), precio de lista e imagen oficial de Hiraoka.
    Aísla el contenedor .product-info-main y el JSON-LD principal ignorando carruseles.
    """
    if not html:
        return None

    vis_html = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ).lower()
    if any(phrase in vis_html for phrase in FORBIDDEN_ERROR_PHRASES_HIRAOKA):
        return None

    soup = BeautifulSoup(html, "lxml")

    is_search_url = "/catalogsearch/result" in offer_url or "?q=" in offer_url or "&q=" in offer_url
    if not is_search_url:
        _, clean_offer_url = canonicalize_store_url(offer_url)
        offer_url = clean_offer_url or offer_url
        if not is_official_store_seller("hiraoka", html, offer_url):
            return None
    main_info_box: Optional[Tag] = soup.select_one(".product-info-main")

    if main_info_box and main_info_box.select_one(".stock.unavailable"):
        return None

    if is_search_url and main_info_box and not soup.select(".product-item-info, li.product-item"):
        canon_link = soup.find("link", rel="canonical")
        og_url_meta = soup.find("meta", property="og:url")
        redirected_u = (
            (canon_link.get("href") if canon_link else None)
            or (og_url_meta.get("content") if og_url_meta else None)
        )
        if redirected_u and "/catalogsearch/" not in str(redirected_u):
            _, clean_offer_url = canonicalize_store_url(str(redirected_u))
            offer_url = clean_offer_url or str(redirected_u)
            is_search_url = False

    if is_search_url or (not main_info_box and soup.select(".product-item-info, li.product-item")):
        return _parse_search_results(soup, offer_url, canonical_title)

    # Eliminar carruseles de productos relacionados, upsell, crosssell y garantías extendidas
    for unwanted in soup.select(CAROUSEL_AND_RELATED_SELECTORS):
        unwanted.decompose()
    if main_info_box:
        for opt_box in main_info_box.select(".product-options-wrapper, .fieldset, .warranty-box"):
            opt_txt = opt_box.get_text(" ", strip=True).lower()
            if "asistencia plus" in opt_txt or "garantía extendida" in opt_txt or "garantia extendida" in opt_txt:
                opt_box.decompose()

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

    # Determinar el alcance de precios en el DOM principal
    has_full_page_layout = bool(soup.select_one(".page-wrapper, #maincontent, .columns"))
    if main_info_box is not None:
        price_scope: Optional[Tag] = main_info_box
    elif not has_full_page_layout:
        price_scope = soup
    else:
        price_scope = None

    # Recolectar candidatos de las 4 fuentes de prioridad de Hiraoka (Módulo 2.2)
    active_prices: list[float] = []
    regular_prices: list[float] = []
    candidate_img: Optional[str] = None
    effective_title: str = h1_title
    ld_desc: str = page_desc

    # 1) <meta property="product:price:amount" content="...">
    meta_price = soup.find("meta", property="product:price:amount")
    if meta_price and meta_price.get("content"):
        mp = clean_number(meta_price["content"])
        if mp:
            active_prices.append(mp)

    # 2) .product-info-main [data-price-type="finalPrice"] -> atributo data-price-amount
    if price_scope is not None:
        final_el = price_scope.select_one('[data-price-type="finalPrice"][data-price-amount]')
        if final_el and final_el.get("data-price-amount"):
            fp = clean_number(final_el["data-price-amount"])
            if fp:
                active_prices.append(fp)
        old_el = price_scope.select_one(
            '[data-price-type="oldPrice"][data-price-amount], '
            '[data-price-type="oldPrice"] .price, '
            ".old-price .price"
        )
        if old_el:
            raw_old = old_el.get("data-price-amount") or old_el.get_text()
            op = clean_number(raw_old)
            if op:
                regular_prices.append(op)

    # 3) JSON-LD <script type="application/ld+json"> (@type == "Product") -> offers.price / offers[0].price
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
                if h1_title and ld_name and h1_title.lower()[:12] not in ld_name.lower() and ld_name.lower()[:12] not in h1_title.lower():
                    continue
                if not effective_title and ld_name:
                    effective_title = ld_name

                offers = item.get("offers", [])
                offers_list = offers if isinstance(offers, list) else [offers]
                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            active_prices.append(p)
                        price_spec = off.get("priceSpecification", {})
                        if isinstance(price_spec, dict):
                            p_type = price_spec.get("priceType", "")
                            spec_price = clean_number(price_spec.get("price"))
                            if "SalePrice" in p_type and spec_price:
                                active_prices.append(spec_price)
                            elif "ListPrice" in p_type and spec_price:
                                regular_prices.append(spec_price)

                official_img = item.get("image")
                if isinstance(official_img, list) and official_img:
                    official_img = official_img[0]
                if isinstance(official_img, str) and is_valid_product_image_url(official_img):
                    candidate_img = official_img
                if item.get("description"):
                    ld_desc = str(item.get("description")).strip()
        except Exception as e:
            logger.debug(f"Error parseando JSON-LD en Hiraoka: {e}")

    # 4) Bloque .special-price .price / .hiraoka-online-price / [data-price-type="finalPrice"] .price dentro de price_scope
    if price_scope is not None:
        for sel in (
            ".hiraoka-online-price .price",
            ".hiraoka-online-price",
            ".special-price .price",
            '[data-price-type="finalPrice"] .price',
            ".price-box .price",
        ):
            el = price_scope.select_one(sel)
            if el:
                sp = clean_number(el.get("data-price-amount") or el.get_text())
                if sp:
                    active_prices.append(sp)

    if not effective_title:
        og_title_el = soup.find("meta", property="og:title")
        if og_title_el and og_title_el.get("content"):
            effective_title = str(og_title_el.get("content")).strip()

    if not candidate_img:
        og_img = soup.find("meta", property="og:image")
        if og_img and is_valid_product_image_url(og_img.get("content")):
            candidate_img = og_img.get("content")

    if active_prices:
        best = min(active_prices)
        orig = max(regular_prices) if regular_prices else max(active_prices)
        if not check_is_in_stock("hiraoka", html, status_code=200, has_valid_price=True):
            return None

        if not h1_title and effective_title:
            extracted_meta = extract_product_specs(
                html, title=effective_title, store_id="hiraoka"
            )
        full_title_for_val = (
            f"{extracted_meta['brand']} {effective_title}".strip()
            if extracted_meta.get("brand") and extracted_meta["brand"].lower() not in effective_title.lower()
            else effective_title
        )
        if canonical_title and not validate_product_identity(
            canonical_title,
            full_title_for_val,
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
            "image_url": candidate_img,
            "offer_url": offer_url,
            "brand": extracted_meta["brand"],
            "tech_specs": extracted_meta["tech_specs"],
            "features": extracted_meta["features"],
            "description": ld_desc,
            "in_stock": True,
        }

    return None
