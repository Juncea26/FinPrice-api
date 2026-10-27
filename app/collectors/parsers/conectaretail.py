"""
Extractor real para Conecta Retail (Tiendas Efe y La Curacao).
Soporta tiendas basadas en Magento 2 con aislamiento estricto del contenedor principal (.product-info-main),
extracción de título H1/JSON-LD y validación de identidad en búsquedas.
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

logger = get_logger("parsers.conectaretail")

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
    Itera sobre las tarjetas de búsqueda y selecciona únicamente aquella cuyo título
    apruebe validate_product_identity(canonical_title, item_title, item_url).
    Jamás toma el primer resultado a ciegas.
    """
    if not canonical_title:
        logger.warning(f"Búsqueda en {search_url} rechazada: se requiere canonical_title para validar tarjetas.")
        return None

    cards = soup.select(".product-item-info, li.product-item")
    for card in cards:
        link_el = card.select_one("a.product-item-link")
        if not link_el:
            continue
        item_title = link_el.get_text(strip=True)
        raw_href = link_el.get("href") or ""
        item_url = urljoin(search_url, raw_href) if raw_href else search_url

        if not validate_product_identity(canonical_title, item_title, item_url, store_id="conectaretail"):
            continue

        # Extraer precio estrictamente dentro de la tarjeta validada
        price_el = card.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            ".special-price [data-price-amount], "
            "[data-price-amount], "
            '[data-price-type="finalPrice"] .price, '
            ".special-price .price, "
            ".price-box .price"
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
        img_url = None
        if img_el:
            img_url = img_el.get("src") or img_el.get("data-src")

        return {
            "title": item_title,
            "price": current_p,
            "original_price": old_p if (old_p and old_p > current_p) else current_p,
            "image_url": img_url,
            "offer_url": item_url,
        }

    return None


def parse_conectaretail(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, precio final, precio original e imagen oficial desde efe.com.pe o lacuracao.pe.
    Aísla estrictamente el contenedor principal (.product-info-main) ignorando carruseles (.block.related, .block.upsell).
    """
    if not html:
        return None

    is_search_url = "/catalogsearch/result" in offer_url or "?q=" in offer_url or "&q=" in offer_url
    if not is_search_url:
        _, clean_offer_url = canonicalize_store_url(offer_url)
        offer_url = clean_offer_url or offer_url

    soup = BeautifulSoup(html, "lxml")
    main_info_box: Optional[Tag] = soup.select_one(".product-info-main")

    if is_search_url or (not main_info_box and soup.select(".product-item-info, li.product-item")):
        return _parse_search_results(soup, offer_url, canonical_title)

    # Eliminar todos los carruseles de productos relacionados, upsell y crosssell antes de extraer
    for unwanted in soup.select(CAROUSEL_AND_RELATED_SELECTORS):
        unwanted.decompose()

    h1_title = _extract_main_h1_title(soup)
    extracted_meta = extract_product_specs(html, title=h1_title, store_id="conectaretail")

    # Buscar imagen oficial en el bloque de galería principal o meta og:image de la ficha
    gallery_img = soup.select_one(
        ".product.media img.gallery-placeholder__image, "
        ".fotorama__stage__frame img.fotorama__img"
    )
    og_img = soup.find("meta", property="og:image")
    page_image = (
        (gallery_img.get("src") or gallery_img.get("href")) if gallery_img else None
    ) or (og_img.get("content") if og_img else None)

    # Determinar el contenedor de precios: estrictamente .product-info-main si existe en el DOM.
    # Solo se permite el fallback a soup en fragmentos sintéticos mínimos de tests unitarios sin estructura de página.
    has_full_page_layout = bool(soup.select_one(".page-wrapper, #maincontent, .columns"))
    if main_info_box is not None:
        price_scope: Tag = main_info_box
    elif not has_full_page_layout:
        price_scope = soup
    else:
        price_scope = None  # type: ignore[assignment]

    # 1. Estrategia Magento 2 dentro de .product-info-main
    if price_scope is not None:
        price_span = price_scope.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            ".special-price [data-price-amount], "
            ".price-final_price [data-price-amount], "
            "[data-price-amount]"
        )
        if price_span and price_span.get("data-price-amount"):
            current_p = clean_number(price_span["data-price-amount"])
            if current_p:
                old_span = price_scope.select_one(
                    '[data-price-type="oldPrice"][data-price-amount], '
                    ".old-price [data-price-amount]"
                )
                old_p = clean_number(old_span.get("data-price-amount")) if old_span else None

                if canonical_title and not validate_product_identity(
                    canonical_title, h1_title, offer_url, store_id="conectaretail"
                ):
                    return None

                return {
                    "title": h1_title,
                    "price": current_p,
                    "original_price": old_p if (old_p and old_p > current_p) else current_p,
                    "image_url": page_image,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"],
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                }

    # 2. Estrategia JSON-LD del Producto Principal
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
                # Si tenemos H1, verificar que el JSON-LD corresponda al mismo producto principal
                effective_title = h1_title or ld_name
                if h1_title and ld_name and h1_title.lower()[:12] not in ld_name.lower() and ld_name.lower()[:12] not in h1_title.lower():
                    continue

                offers = item.get("offers")
                offers_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
                prices_found = []
                high_price = None
                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            prices_found.append(p)
                        hp = clean_number(off.get("highPrice"))
                        if hp:
                            high_price = hp

                if prices_found:
                    best_p = min(prices_found)
                    orig_p = high_price or max(prices_found)
                    ld_img = item.get("image")
                    if isinstance(ld_img, list) and ld_img:
                        ld_img = ld_img[0]

                    if canonical_title and not validate_product_identity(
                        canonical_title, effective_title, offer_url, store_id="conectaretail"
                    ):
                        return None

                    if not h1_title and effective_title:
                        extracted_meta = extract_product_specs(
                            html, title=effective_title, store_id="conectaretail"
                        )
                    return {
                        "title": effective_title,
                        "price": best_p,
                        "original_price": orig_p if orig_p > best_p else best_p,
                        "image_url": ld_img if isinstance(ld_img, str) else page_image,
                        "offer_url": offer_url,
                        "brand": extracted_meta["brand"],
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                    }
        except Exception:
            pass

    # 3. Selectores CSS de respaldo estrictamente dentro de .product-info-main (price_scope)
    if price_scope is not None:
        price_text_elem = price_scope.select_one(
            '[data-price-type="finalPrice"] .price, '
            ".special-price .price, "
            ".price-wrapper .price, "
            ".final-price .price"
        )
        if price_text_elem:
            p = clean_number(price_text_elem.get_text())
            if p:
                old_text_elem = price_scope.select_one(
                    '[data-price-type="oldPrice"] .price, .old-price .price'
                )
                old_p = clean_number(old_text_elem.get_text()) if old_text_elem else None

                if canonical_title and not validate_product_identity(
                    canonical_title, h1_title, offer_url, store_id="conectaretail"
                ):
                    return None

                return {
                    "title": h1_title,
                    "price": p,
                    "original_price": old_p if (old_p and old_p > p) else p,
                    "image_url": page_image,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"],
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                }

    return None
