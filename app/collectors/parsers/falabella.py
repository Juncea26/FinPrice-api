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
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.url_utils import canonicalize_store_url
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

    _, clean_offer_url = canonicalize_store_url(offer_url)
    offer_url = clean_offer_url or offer_url

    soup = BeautifulSoup(html, "lxml")
    h1_el = soup.select_one("h1.jsx-product-name, .product-name h1, h1")
    h1_title = h1_el.get_text(strip=True) if h1_el else ""

    # 1. Estrategia __NEXT_DATA__
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            props = data.get("props", {}).get("pageProps", {})

            # Si es una página de resultados de búsqueda en __NEXT_DATA__, evaluar todos los colores/resultados válidos y elegir el más barato
            search_results = props.get("results")
            if isinstance(search_results, list) and search_results and not props.get("productData"):
                if not canonical_title:
                    return None
                best_search_candidate: Optional[Dict[str, Any]] = None
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
                        cand_dict = {
                            "title": item_title,
                            "price": best_p,
                            "original_price": list_p if list_p > best_p else best_p,
                            "image_url": img_u,
                            "offer_url": item_url,
                        }
                        if best_search_candidate is None or best_p < best_search_candidate["price"]:
                            best_search_candidate = cand_dict
                return best_search_candidate

            prod = props.get("productData", {}) or props.get("product", {})
            prod_title = str(prod.get("name") or prod.get("displayName") or h1_title).strip()
            prod_desc = " ".join(
                filter(
                    None,
                    [
                        str(prod.get("description") or "").strip(),
                        str(prod.get("longDescription") or "").strip(),
                    ],
                )
            )
            variants = prod.get("variants", [])
            extracted_prices = []
            orig_price = None
            official_img = None
            variant_name = ""
            variant_id = ""

            if variants and isinstance(variants, list):
                # Multi-SKU & Multi-Color Variant Resolution:
                # Evaluar TODAS las variantes (todos los colores) que cumplan la capacidad buscada
                # y seleccionar la que tenga el PRECIO MÁS BARATO.
                url_parts = [p for p in offer_url.split("/") if p]
                url_tail_sku = url_parts[-1] if len(url_parts) >= 6 else ""

                req_storage_tok = None
                if canonical_title:
                    m_st = re.search(r"\b(\d{2,4}\s*(?:GB|TB))\b", canonical_title, flags=re.IGNORECASE)
                    if m_st:
                        req_storage_tok = re.sub(r"\s+", "", m_st.group(1)).lower()

                all_storage_tokens = {"64gb", "128gb", "256gb", "512gb", "1024gb", "1tb", "2tb"}

                def _variant_min_price(v_obj: Dict[str, Any]) -> Optional[float]:
                    v_prices = []
                    for p_it in v_obj.get("prices", []) or []:
                        if not isinstance(p_it, dict):
                            continue
                        p_v = p_it.get("price", [])
                        r_v = p_v[0] if isinstance(p_v, list) and p_v else p_v
                        n_v = clean_number(r_v)
                        if n_v:
                            v_prices.append(n_v)
                    return min(v_prices) if v_prices else None

                priced_variants = [
                    v_c for v_c in variants if isinstance(v_c, dict) and _variant_min_price(v_c) is not None
                ]

                matching_capacity_variants = []
                if req_storage_tok and priced_variants:
                    # 1. Variantes que declaran explícitamente la capacidad buscada (ej. 128gb)
                    explicit_cap = [
                        v_c
                        for v_c in priced_variants
                        if req_storage_tok in json.dumps(v_c, ensure_ascii=False).lower().replace(" ", "")
                    ]
                    if explicit_cap:
                        matching_capacity_variants = explicit_cap
                    else:
                        # 2. Variantes que no declaran una capacidad conflictiva distinta
                        other_caps = all_storage_tokens - {req_storage_tok}
                        matching_capacity_variants = [
                            v_c
                            for v_c in priced_variants
                            if not any(
                                oc in json.dumps(v_c, ensure_ascii=False).lower().replace(" ", "")
                                for oc in other_caps
                            )
                        ]
                else:
                    matching_capacity_variants = priced_variants

                selected_v = None
                if matching_capacity_variants:
                    # Ordenar por menor precio vigente; en caso de empate de precio, priorizar el SKU de la URL
                    matching_capacity_variants.sort(
                        key=lambda v_c: (
                            _variant_min_price(v_c) or float("inf"),
                            0 if str(v_c.get("id") or "") == url_tail_sku else 1,
                        )
                    )
                    selected_v = matching_capacity_variants[0]
                elif priced_variants:
                    selected_v = priced_variants[0]
                else:
                    selected_v = variants[0]

                v = selected_v
                variant_id = str(v.get("id") or "").strip()
                variant_name = str(v.get("name") or "").strip()
                if not prod_title and variant_name:
                    prod_title = variant_name

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

                medias = v.get("medias", []) or prod.get("medias", [])
                if medias and isinstance(medias[0], dict) and medias[0].get("url"):
                    official_img = medias[0]["url"]

                # Si la variante tiene SKU ID explícito y la URL tiene formato /product/{id}/{slug}/{sku}, actualizar al SKU de la variante
                if variant_id:
                    m_url = re.match(
                        r"^(https://www\.(?:falabella|tottus)\.com\.pe/(?:falabella-pe|tottus-pe)/(?:product|articulo)/[^/]+/[^/]+)(?:/[^/?#]+)?$",
                        offer_url,
                    )
                    if m_url:
                        offer_url = f"{m_url.group(1)}/{variant_id}"

            if extracted_prices:
                full_desc = " ".join(filter(None, [prod_desc, variant_name])).strip()
                extracted_meta = extract_product_specs(
                    html,
                    title=f"{prod_title} {variant_name}".strip(),
                    store_id="tottus" if "tottus.com.pe" in offer_url else "falabella",
                )
                if canonical_title and not validate_product_identity(
                    canonical_title,
                    prod_title,
                    offer_url,
                    store_id="tottus" if "tottus.com.pe" in offer_url else "falabella",
                    tech_specs=extracted_meta["tech_specs"],
                    description=full_desc,
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
                    "description": full_desc,
                    "variant_sku_id": variant_id,
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
