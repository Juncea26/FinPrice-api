"""
Extractor real para Ripley Perú (simple.ripley.com.pe).
Extrae título real y precios desde __NEXT_DATA__ (detailProps.data.product.parentpricestock) y JSON-LD,
aislando el nodo del producto principal e ignorando carruseles de recomendados.
"""
import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.validators import validate_product_identity

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


def parse_ripley(
    html: str, offer_url: str, canonical_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extrae título real, precio con Tarjeta Ripley o internet, precio lista e imagen oficial de Ripley.
    """
    if not html:
        return None

    _, clean_offer_url = canonicalize_store_url(offer_url)
    offer_url = clean_offer_url or offer_url

    soup = BeautifulSoup(html, "lxml")

    # Eliminar carruseles de recomendados / relacionados en el DOM
    for carousel in soup.select(".carousel, .related-products, .product-carousel, aside, footer"):
        carousel.decompose()

    h1_el = soup.select_one("section.product-header h1, .product-info h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

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
            prod_title = str(prod.get("name") or h1_title).strip()
            price_stock = prod.get("parentpricestock", {})
            price_dict = price_stock.get("price", {}) if isinstance(price_stock, dict) else {}

            extracted_prices = []
            orig_price = None

            # 1. Precio con tarjeta Ripley
            ripley_p = clean_number(price_dict.get("ripley", {}).get("valueNumber"))
            if ripley_p:
                extracted_prices.append(ripley_p)

            # 2. Precio de venta / oferta internet
            sale_p = clean_number(price_dict.get("sale", {}).get("valueNumber"))
            if sale_p:
                extracted_prices.append(sale_p)

            # 3. Precio de lista / normal
            master_p = clean_number(price_dict.get("master", {}).get("valueNumber"))
            if master_p:
                orig_price = master_p

            official_img = None
            images = prod.get("images", [])
            if images and isinstance(images, list):
                official_img = images[0]
            elif prod.get("primaryImage"):
                official_img = prod.get("primaryImage")

            if extracted_prices:
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

                best_p = min(extracted_prices)
                list_p = orig_price or max(extracted_prices)
                return {
                    "title": prod_title,
                    "price": best_p,
                    "original_price": list_p if list_p > best_p else best_p,
                    "image_url": official_img,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"],
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                    "description": prod_desc,
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
            prod_title = str(prod.get("name") or h1_title).strip()
            prod_desc = str(prod.get("description") or prod.get("shortDescription") or "").strip()
            prices_node = prod.get("prices", {}) or prod.get("parentpricestock", {}).get("price", {})
            extracted_p = []
            orig_p = None
            if isinstance(prices_node, dict):
                for k_p in ("cardPrice", "offerPrice", "ripley", "sale"):
                    v_p = prices_node.get(k_p)
                    num_p = clean_number(v_p.get("valueNumber") if isinstance(v_p, dict) else v_p)
                    if num_p:
                        extracted_p.append(num_p)
                for k_orig in ("listPrice", "master", "normalPrice"):
                    v_o = prices_node.get(k_orig)
                    num_o = clean_number(v_o.get("valueNumber") if isinstance(v_o, dict) else v_o)
                    if num_o:
                        orig_p = num_o
            if extracted_p:
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
                best_p = min(extracted_p)
                list_p = orig_p or max(extracted_p)
                imgs = prod.get("images") or []
                img_u = imgs[0] if isinstance(imgs, list) and imgs else prod.get("fullImage")
                return {
                    "title": prod_title,
                    "price": best_p,
                    "original_price": list_p if list_p > best_p else best_p,
                    "image_url": img_u,
                    "offer_url": offer_url,
                    "brand": extracted_meta["brand"],
                    "tech_specs": extracted_meta["tech_specs"],
                    "features": extracted_meta["features"],
                    "description": prod_desc,
                }
        except Exception as e:
            logger.debug(f"Error parseando __PRELOADED_STATE__ en Ripley: {e}")

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
                prices = []
                for off in offers_list:
                    if isinstance(off, dict):
                        p = clean_number(off.get("price"))
                        if p:
                            prices.append(p)
                if prices:
                    if canonical_title and not validate_product_identity(
                        canonical_title, ld_title, offer_url, store_id="ripley"
                    ):
                        return None

                    og_img = soup.find("meta", property="og:image")
                    return {
                        "title": ld_title,
                        "price": min(prices),
                        "original_price": max(prices),
                        "image_url": og_img.get("content") if og_img else None,
                        "offer_url": offer_url,
                    }
        except Exception:
            pass

    # 3. Selectores CSS aislados al contenedor de producto
    main_scope = soup.select_one(".product-info, .product-header, #product-page") or soup
    price_elem = main_scope.select_one(
        ".catalog-prices__card-price, .catalog-prices__offer-price, .product-price"
    )
    if price_elem:
        p = clean_number(price_elem.get_text())
        if p:
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
            }

    return None
