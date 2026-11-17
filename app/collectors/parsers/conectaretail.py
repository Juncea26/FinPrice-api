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
from app.collectors.url_utils import canonicalize_store_url, is_marketplace_url, is_valid_product_image_url
from app.collectors.validators import check_is_in_stock, is_official_store_seller, validate_product_identity

logger = get_logger("parsers.conectaretail")

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
        ".product-info-main h1, "
        "h1.page-title, "
        "main h1, "
        "h1"
    )
    if h1_span:
        txt = h1_span.get_text(strip=True)
        if txt:
            return txt
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return str(og_title["content"]).split("|", 1)[0].strip()
    if soup.title and soup.title.string:
        raw_t = str(soup.title.string).split("|", 1)[0].strip()
        if raw_t and "resultados de búsqueda" not in raw_t.lower():
            return raw_t
    return ""


def _has_active_add_to_cart(html: str, soup: BeautifulSoup) -> bool:
    if soup.select_one("#product-addtocart-button, button.tocart, button[title*='Agregar al carrito' i]"):
        return True
    low = (html or "").lower()
    return any(
        marker in low
        for marker in ("agregar al carrito", "añadir al carro", "anadir al carro", "product-addtocart-button")
    )


def _parse_search_results(
    soup: BeautifulSoup, search_url: str, canonical_title: Optional[str]
) -> Optional[Dict[str, Any]]:
    """
    Itera sobre TODAS las tarjetas de búsqueda (todos los colores disponibles),
    filtra aquellas que aprueben validate_product_identity(canonical_title, item_title, item_url)
    y selecciona la que tenga el MENOR precio vigente.
    """
    if not canonical_title:
        logger.warning(f"Búsqueda en {search_url} rechazada: se requiere canonical_title para validar tarjetas.")
        return None

    best_candidate: Optional[Dict[str, Any]] = None
    cards = soup.select(".product-item-info, li.product-item")
    for card in cards:
        if card.select_one(".stock.unavailable"):
            continue
        link_el = card.select_one("a.product-item-link")
        if not link_el:
            continue
        raw_title = link_el.get_text(strip=True)
        brand_el = card.select_one(".product-item-brand .brand-name, .brand-name")
        card_brand = brand_el.get_text(strip=True) if brand_el else ""
        item_title = (
            f"{card_brand} {raw_title}".strip()
            if card_brand and card_brand.lower() not in raw_title.lower()
            else raw_title
        )
        raw_href = link_el.get("href") or ""
        item_url = urljoin(search_url, raw_href) if raw_href else search_url
        det_store, clean_card_url = canonicalize_store_url(item_url)
        item_url = clean_card_url or item_url
        eff_card_store = "curacao" if det_store == "curacao" else "efe"
        if is_marketplace_url(eff_card_store, item_url):
            continue
        if not is_official_store_seller(eff_card_store, str(card), item_url):
            continue

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


FORBIDDEN_ERROR_PHRASES_CONECTARETAIL = (
    "¡uy! no hemos encontrado resultados",
    "no hemos encontrado resultados para tu búsqueda",
    "ups! 404",
    "la página que buscas ya no existe",
    "producto que buscas ya no está disponible",
    "no encontramos resultados",
    "producto sin stock",
)


def parse_conectaretail(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, el menor precio de venta vigente, precio original e imagen oficial desde efe.com.pe o lacuracao.pe.
    Aísla estrictamente el contenedor principal (.product-info-main) ignorando carruseles (.block.related, .block.upsell).
    """
    if not html:
        return None

    vis_html = re.sub(
        r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ).lower()
    if any(phrase in vis_html for phrase in FORBIDDEN_ERROR_PHRASES_CONECTARETAIL):
        return None

    is_search_url = "/catalogsearch/result" in offer_url or "?q=" in offer_url or "&q=" in offer_url
    if not is_search_url:
        detected_store, clean_offer_url = canonicalize_store_url(offer_url)
        offer_url = clean_offer_url or offer_url
        eff_store = "curacao" if detected_store == "curacao" else "efe"
        if not is_official_store_seller(eff_store, html, offer_url):
            return None

    soup = BeautifulSoup(html, "lxml")
    main_info_box: Optional[Tag] = soup.select_one(
        ".product-info-main, .product-main-info, .product-view .product-info, .column.main .product-info-main"
    )
    has_cart_btn = _has_active_add_to_cart(html, soup)

    if main_info_box and main_info_box.select_one(".stock.unavailable") and not has_cart_btn:
        return None
    if not main_info_box and soup.select_one(".stock.unavailable") and not has_cart_btn:
        # En plantillas Magento sin .product-info-main, descartar si marca explícitamente .stock.unavailable sin carrito
        main_scope_check = soup.select_one("#maincontent, main, .page-wrapper")
        if main_scope_check and main_scope_check.select_one(".stock.unavailable"):
            return None

    if is_search_url and main_info_box and not soup.select(".product-item-info, li.product-item"):
        # La búsqueda redirigió directamente a la ficha de un único producto
        canon_link = soup.find("link", rel="canonical")
        og_url_meta = soup.find("meta", property="og:url")
        redirected_u = (
            (canon_link.get("href") if canon_link else None)
            or (og_url_meta.get("content") if og_url_meta else None)
        )
        if redirected_u and "/catalogsearch/" not in str(redirected_u):
            detected_store, clean_offer_url = canonicalize_store_url(str(redirected_u))
            offer_url = clean_offer_url or str(redirected_u)
            is_search_url = False
            eff_store = "curacao" if detected_store == "curacao" else "efe"
            if not is_official_store_seller(eff_store, html, offer_url):
                return None

    has_product_metadata = bool(
        soup.find("meta", property="product:price:amount")
        or any(
            s.string and '"Product"' in s.string
            for s in soup.find_all("script", type="application/ld+json")
        )
    )

    if is_search_url or (not main_info_box and not has_product_metadata and soup.select(".product-item-info, li.product-item")):
        return _parse_search_results(soup, offer_url, canonical_title)

    # Eliminar todos los carruseles de productos relacionados, upsell, crosssell y garantías extendidas
    for unwanted in soup.select(CAROUSEL_AND_RELATED_SELECTORS):
        unwanted.decompose()
    if main_info_box:
        for opt_box in main_info_box.select(".product-options-wrapper, .fieldset, .warranty-box"):
            opt_txt = opt_box.get_text(" ", strip=True).lower()
            if "asistencia plus" in opt_txt or "garantía extendida" in opt_txt or "garantia extendida" in opt_txt:
                opt_box.decompose()

    h1_title = _extract_main_h1_title(soup)
    extracted_meta = extract_product_specs(html, title=h1_title, store_id="conectaretail")
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

    # Buscar imagen oficial dando prioridad a meta og:image y rechazando placeholders o logos
    og_img = soup.find("meta", property="og:image")
    og_content = og_img.get("content") if og_img else None
    if isinstance(og_content, str) and "/media/catalog/product/" in og_content and "?" in og_content:
        og_content = og_content.split("?", 1)[0]
    gallery_img = soup.select_one(".fotorama__stage__frame img.fotorama__img, .product.media img")
    gallery_src = (gallery_img.get("src") or gallery_img.get("href")) if gallery_img else None
    if isinstance(gallery_src, str) and "/media/catalog/product/" in gallery_src and "?" in gallery_src:
        gallery_src = gallery_src.split("?", 1)[0]

    page_image = None
    if is_valid_product_image_url(og_content):
        page_image = og_content
    elif is_valid_product_image_url(gallery_src):
        page_image = gallery_src

    # Determinar el contenedor de precios: estrictamente .product-info-main si existe en el DOM.
    # Solo se permite el fallback a soup en fragmentos sintéticos mínimos de tests unitarios sin estructura de página.
    has_full_page_layout = bool(soup.select_one(".page-wrapper, #maincontent, .columns"))
    if main_info_box is not None:
        price_scope: Tag = main_info_box
    elif not has_full_page_layout:
        price_scope = soup
    else:
        price_scope = None  # type: ignore[assignment]

    eff_store_id = "curacao" if "lacuracao.pe" in offer_url.lower() else "efe"

    # Extraer oldPrice del contenedor principal si existe para acompañar cualquier prioridad
    dom_old_p: Optional[float] = None
    if price_scope is not None:
        old_span = price_scope.select_one(
            '[data-price-type="oldPrice"][data-price-amount], '
            ".old-price [data-price-amount]"
        )
        if old_span and old_span.get("data-price-amount"):
            dom_old_p = clean_number(old_span.get("data-price-amount"))
        if not dom_old_p:
            old_text_elem = price_scope.select_one(
                '[data-price-type="oldPrice"] .price, .old-price .price'
            )
            if old_text_elem:
                dom_old_p = clean_number(old_text_elem.get_text())

    # Prioridad 1: <meta property="product:price:amount" content="...">
    meta_price_el = soup.find("meta", property="product:price:amount")
    meta_p = clean_number(meta_price_el.get("content")) if (meta_price_el and meta_price_el.get("content")) else None

    # Prioridad 2: .product-info-main [data-price-type="finalPrice"] -> atributo data-price-amount
    final_p: Optional[float] = None
    if price_scope is not None:
        price_span = price_scope.select_one(
            '[data-price-type="finalPrice"][data-price-amount], '
            ".special-price [data-price-amount], "
            ".price-final_price [data-price-amount], "
            "[data-price-amount]"
        )
        if price_span and price_span.get("data-price-amount"):
            final_p = clean_number(price_span["data-price-amount"])

    chosen_primary_p = meta_p or final_p
    if final_p and meta_p and final_p < meta_p:
        chosen_primary_p = final_p

    if chosen_primary_p:
        if not check_is_in_stock(eff_store_id, html, status_code=200, has_valid_price=True):
            return None
        full_title_for_val = (
            f"{extracted_meta['brand']} {h1_title}".strip()
            if extracted_meta.get("brand") and extracted_meta["brand"].lower() not in h1_title.lower()
            else h1_title
        )
        if canonical_title and not validate_product_identity(
            canonical_title,
            full_title_for_val,
            offer_url,
            store_id="conectaretail",
            tech_specs=extracted_meta["tech_specs"],
            description=page_desc,
        ):
            return None

        return {
            "title": h1_title,
            "price": chosen_primary_p,
            "original_price": dom_old_p if (dom_old_p and dom_old_p > chosen_primary_p) else chosen_primary_p,
            "image_url": page_image,
            "offer_url": offer_url,
            "brand": extracted_meta["brand"],
            "tech_specs": extracted_meta["tech_specs"],
            "features": extracted_meta["features"],
            "description": page_desc,
            "in_stock": True,
        }

    # Prioridad 3: JSON-LD <script type="application/ld+json"> (@type == "Product") -> offers.price / offers[0].price
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            items = []
            if isinstance(j, dict) and isinstance(j.get("@graph"), list):
                items.extend(j["@graph"])
            elif isinstance(j, list):
                items.extend(j)
            else:
                items.append(j)
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                ld_name = str(item.get("name") or "").strip()
                # Si tenemos H1, verificar que el JSON-LD corresponda al mismo producto principal
                effective_title = h1_title or ld_name
                if h1_title and ld_name:
                    h1_words = {w for w in re.findall(r"[a-z0-9]+", h1_title.lower()) if len(w) > 2}
                    ld_words = {w for w in re.findall(r"[a-z0-9]+", ld_name.lower()) if len(w) > 2}
                    if h1_words and ld_words and not (h1_words & ld_words):
                        continue

                offers = item.get("offers")
                offers_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
                prices_found = []
                high_price = dom_old_p
                explicit_out_of_stock = False
                for off in offers_list:
                    if isinstance(off, dict):
                        avail = str(off.get("availability") or "").lower()
                        if any(tok in avail for tok in ("outofstock", "soldout", "discontinued")):
                            explicit_out_of_stock = True
                            continue
                        p = clean_number(off.get("price") or off.get("lowPrice"))
                        if p:
                            prices_found.append(p)
                        hp = clean_number(off.get("highPrice"))
                        if hp:
                            high_price = hp

                if explicit_out_of_stock and not prices_found and not has_cart_btn:
                    return None

                if prices_found:
                    if not check_is_in_stock(eff_store_id, html, status_code=200, has_valid_price=True):
                        return None
                    best_p = min(prices_found)
                    orig_p = high_price or max(prices_found)
                    ld_img = item.get("image")
                    if isinstance(ld_img, list) and ld_img:
                        ld_img = ld_img[0]

                    if not h1_title and effective_title:
                        extracted_meta = extract_product_specs(
                            html, title=effective_title, store_id="conectaretail"
                        )
                    full_title_for_val = (
                        f"{extracted_meta['brand']} {effective_title}".strip()
                        if extracted_meta.get("brand") and extracted_meta["brand"].lower() not in effective_title.lower()
                        else effective_title
                    )
                    if canonical_title and not validate_product_identity(
                        canonical_title, full_title_for_val, offer_url, store_id="conectaretail"
                    ):
                        return None

                    return {
                        "title": effective_title,
                        "price": best_p,
                        "original_price": orig_p if orig_p > best_p else best_p,
                        "image_url": ld_img if isinstance(ld_img, str) else page_image,
                        "offer_url": offer_url,
                        "brand": extracted_meta["brand"],
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                        "in_stock": True,
                    }
        except Exception:
            pass

    # Prioridad 4: Selectores CSS de respaldo estrictamente dentro de .product-info-main (price_scope)
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
                if not check_is_in_stock(eff_store_id, html, status_code=200, has_valid_price=True):
                    return None
                old_p = dom_old_p

                full_title_for_val = (
                    f"{extracted_meta['brand']} {h1_title}".strip()
                    if extracted_meta.get("brand") and extracted_meta["brand"].lower() not in h1_title.lower()
                    else h1_title
                )
                if canonical_title and not validate_product_identity(
                    canonical_title, full_title_for_val, offer_url, store_id="conectaretail"
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
                    "in_stock": True,
                }

    return None
