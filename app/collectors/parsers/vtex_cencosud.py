"""
Extractor real VTEX IO para Cencosud Perú: Metro (metro.pe) y Wong (wong.pe).
Soporta:
1. URLs de producto https://www.metro.pe/{slug}-{id}/p y https://www.wong.pe/{slug}-{id}/p
   (extrayendo desde JSON-LD y/o el estado Apollo VTEX IO embebido en el HTML).
2. Respuestas JSON directas de la API pública VTEX:
   /api/catalog_system/pub/products/search/{slug}/p o ?ft={query} o ?fq=alternateIds_RefId:{sku}
Verifica disponibilidad (InStock / AvailableQuantity > 0), limpia la URL canónica y extrae tech_specs.
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.spec_extractor import (
    extract_product_specs,
    generate_product_features,
    normalize_brand,
    normalize_raw_pairs_to_specs,
)
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.validators import validate_product_identity

logger = get_logger("parsers.vtex_cencosud")


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


def parse_vtex_api_item(item_dict: Dict[str, Any], default_url: str = "") -> Optional[Dict[str, Any]]:
    """
    Extrae precio vigente, precio de lista, stock, imagen oficial y especificaciones
    desde un objeto de producto del endpoint JSON de VTEX (/api/catalog_system/pub/products/search).
    """
    if not isinstance(item_dict, dict):
        return None

    title = str(item_dict.get("productName") or item_dict.get("productTitle") or "").strip()
    raw_link = str(item_dict.get("link") or default_url).strip()
    store_id, clean_url = canonicalize_store_url(raw_link)
    raw_brand = str(item_dict.get("brand") or "").strip()

    items = item_dict.get("items") or []
    best_price: Optional[float] = None
    orig_price: Optional[float] = None
    img_url: Optional[str] = None
    is_in_stock = False

    for sku_item in items:
        if not isinstance(sku_item, dict):
            continue
        images = sku_item.get("images") or []
        if not img_url and images and isinstance(images[0], dict):
            img_url = images[0].get("imageUrl")

        sellers = sku_item.get("sellers") or []
        for seller in sellers:
            if not isinstance(seller, dict):
                continue
            offer = seller.get("commertialOffer") or {}
            avail = offer.get("AvailableQuantity", 1)
            is_avail_flag = offer.get("IsAvailable", True)
            if (avail is not None and int(avail) <= 0) or is_avail_flag is False:
                continue

            p = clean_number(offer.get("Price") or offer.get("spotPrice"))
            lp = clean_number(offer.get("ListPrice") or offer.get("PriceWithoutDiscount"))
            if p and p > 0:
                is_in_stock = True
                if best_price is None or p < best_price:
                    best_price = p
                    orig_price = lp if (lp and lp > p) else p

    if not is_in_stock or not best_price:
        return None

    # Extraer especificaciones del objeto VTEX
    raw_pairs: List[Tuple[str, str]] = []
    if raw_brand:
        raw_pairs.append(("Marca", raw_brand))

    all_spec_names = item_dict.get("allSpecifications") or []
    if isinstance(all_spec_names, list):
        for spec_name in all_spec_names:
            val_list = item_dict.get(spec_name)
            if isinstance(val_list, list) and val_list:
                raw_pairs.append((str(spec_name), ", ".join(str(x) for x in val_list if x)))
            elif isinstance(val_list, str) and val_list:
                raw_pairs.append((str(spec_name), val_list))

    tech_specs = normalize_raw_pairs_to_specs(raw_pairs, title=title)
    brand = tech_specs.get("Marca") or normalize_brand(raw_brand, title)
    if brand:
        tech_specs["Marca"] = brand
    features = generate_product_features(soup=None, tech_specs=tech_specs, title=title)

    desc = str(item_dict.get("description") or item_dict.get("metaTagDescription") or "").strip()

    return {
        "title": title,
        "price": best_price,
        "original_price": orig_price or best_price,
        "image_url": img_url,
        "offer_url": clean_url or raw_link,
        "brand": brand,
        "tech_specs": tech_specs,
        "features": features,
        "description": desc,
        "in_stock": True,
    }


def parse_vtex_search_json(
    raw_json: str,
    search_url: str,
    canonical_title: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Parsea la lista de productos devuelta por /api/catalog_system/pub/products/search
    en Metro o Wong.
    """
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    candidates: List[Dict[str, Any]] = []
    for item in data:
        parsed = parse_vtex_api_item(item, default_url=search_url)
        if not parsed:
            continue
        if canonical_title:
            store_id, _ = canonicalize_store_url(parsed["offer_url"])
            if not validate_product_identity(
                canonical_title=canonical_title,
                scraped_title=parsed["title"],
                scraped_url=parsed["offer_url"],
                store_id=store_id,
                tech_specs=parsed.get("tech_specs"),
            ):
                continue
        candidates.append(parsed)
    return candidates


def _parse_vtex_apollo_state(soup: BeautifulSoup, clean_url: str) -> Optional[Dict[str, Any]]:
    """
    Extrae producto, precios, disponibilidad, imágenes y specs desde el estado
    Apollo GraphQL embebido en páginas /p de VTEX IO (Metro y Wong).
    """
    for s in soup.find_all("script"):
        txt = (s.string or "").strip()
        if not txt.startswith('{"Product:'):
            continue
        try:
            state = json.loads(txt)
        except Exception:
            continue

        prod_node: Optional[Dict[str, Any]] = None
        prod_key_prefix = ""
        for k, v in state.items():
            if k.startswith("Product:") and isinstance(v, dict) and v.get("productName"):
                prod_node = v
                prod_key_prefix = k
                break

        if not prod_node:
            continue

        title = str(prod_node.get("productName") or "").strip()
        raw_brand = str(prod_node.get("brand") or "").strip()

        # Buscar precios y stock en commertialOffer o priceRange
        best_p: Optional[float] = None
        orig_p: Optional[float] = None
        in_stock = True

        for k, v in state.items():
            if not isinstance(v, dict):
                continue
            if k.startswith(f"${prod_key_prefix}") and k.endswith(".commertialOffer"):
                avail = v.get("AvailableQuantity")
                if avail is not None and int(avail) <= 0:
                    in_stock = False
                    continue
                p = clean_number(v.get("Price") or v.get("spotPrice"))
                lp = clean_number(v.get("ListPrice") or v.get("PriceWithoutDiscount"))
                if p:
                    in_stock = True
                    best_p = p if (best_p is None or p < best_p) else best_p
                    orig_p = lp if (lp and lp > best_p) else best_p

        if best_p is None:
            selling_node = state.get(f"${prod_key_prefix}.priceRange.sellingPrice") or {}
            list_node = state.get(f"${prod_key_prefix}.priceRange.listPrice") or {}
            best_p = clean_number(selling_node.get("lowPrice") or selling_node.get("highPrice"))
            orig_p = clean_number(list_node.get("highPrice") or list_node.get("lowPrice"))

        if not in_stock or not best_p:
            return None

        # Imagen oficial
        img_url: Optional[str] = None
        for k, v in state.items():
            if k.startswith("Image:") and isinstance(v, dict) and v.get("imageUrl"):
                img_url = str(v["imageUrl"])
                break

        # Especificaciones desde nodos SpecificationGroupProperty
        raw_pairs: List[Tuple[str, str]] = []
        if raw_brand:
            raw_pairs.append(("Marca", raw_brand))
        for k, v in state.items():
            if isinstance(v, dict) and v.get("__typename") == "SpecificationGroupProperty":
                sp_name = str(v.get("name") or "")
                sp_vals = v.get("values")
                if isinstance(sp_vals, dict) and isinstance(sp_vals.get("json"), list):
                    sp_val_str = ", ".join(str(x) for x in sp_vals["json"] if x)
                elif isinstance(sp_vals, list):
                    sp_val_str = ", ".join(str(x) for x in sp_vals if x)
                else:
                    sp_val_str = str(sp_vals or "")
                if sp_name and sp_val_str:
                    raw_pairs.append((sp_name, sp_val_str))

        tech_specs = normalize_raw_pairs_to_specs(raw_pairs, title=title)
        brand = tech_specs.get("Marca") or normalize_brand(raw_brand, title)
        if brand:
            tech_specs["Marca"] = brand
        features = generate_product_features(soup=soup, tech_specs=tech_specs, title=title)

        return {
            "title": title,
            "price": best_p,
            "original_price": orig_p if (orig_p and orig_p > best_p) else best_p,
            "image_url": img_url,
            "offer_url": clean_url,
            "brand": brand,
            "tech_specs": tech_specs,
            "features": features,
        }

    return None


def parse_vtex_cencosud(
    html_or_json: str,
    offer_url: str,
    canonical_title: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Parser principal VTEX para Metro (metro.pe) y Wong (wong.pe).
    Soporta tanto respuestas JSON de /api/catalog_system/pub/products/search
    como HTML de páginas /p (mediante JSON-LD y estado Apollo VTEX IO).
    """
    if not html_or_json:
        return None

    store_id, clean_url = canonicalize_store_url(offer_url)
    stripped = html_or_json.strip()

    # 1. Si la respuesta proviene directamente del endpoint JSON de la API pública VTEX
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                for item in data:
                    parsed = parse_vtex_api_item(item, default_url=clean_url)
                    if not parsed:
                        continue
                    if canonical_title and not validate_product_identity(
                        canonical_title=canonical_title,
                        scraped_title=parsed["title"],
                        scraped_url=parsed["offer_url"],
                        store_id=store_id,
                        tech_specs=parsed.get("tech_specs"),
                    ):
                        continue
                    return parsed
                return None
        except Exception:
            pass

    soup = BeautifulSoup(html_or_json, "lxml")

    # 2. Estrategia JSON-LD en la página /p
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            items = j if isinstance(j, list) else [j]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                ld_title = str(item.get("name") or "").strip()
                offers = item.get("offers")
                if not offers:
                    continue

                offers_list = offers if isinstance(offers, list) else [offers]
                low_p: Optional[float] = None
                high_p: Optional[float] = None
                in_stock = True

                if isinstance(offers, dict):
                    avail_str = str(offers.get("availability") or "")
                    if "OutOfStock" in avail_str:
                        in_stock = False
                    low_p = clean_number(offers.get("lowPrice") or offers.get("price"))
                    high_p = clean_number(offers.get("highPrice") or offers.get("price"))
                    nested = offers.get("offers")
                    if isinstance(nested, list):
                        for noff in nested:
                            if isinstance(noff, dict):
                                if "OutOfStock" in str(noff.get("availability") or ""):
                                    continue
                                np = clean_number(noff.get("price"))
                                if np:
                                    low_p = np if (low_p is None or np < low_p) else low_p
                                    high_p = np if (high_p is None or np > high_p) else high_p
                else:
                    for off in offers_list:
                        if isinstance(off, dict):
                            if "OutOfStock" in str(off.get("availability") or ""):
                                continue
                            p = clean_number(off.get("lowPrice") or off.get("price"))
                            hp = clean_number(off.get("highPrice"))
                            if p:
                                low_p = p if (low_p is None or p < low_p) else low_p
                                high_p = (hp or p) if (high_p is None or (hp or p) > high_p) else high_p

                if in_stock and low_p:
                    if canonical_title and not validate_product_identity(
                        canonical_title, ld_title, clean_url, store_id=store_id
                    ):
                        return None

                    ld_img = item.get("image")
                    if isinstance(ld_img, list) and ld_img:
                        ld_img = ld_img[0]
                    extracted_meta = extract_product_specs(html_or_json, title=ld_title, store_id=store_id)
                    return {
                        "title": ld_title,
                        "price": low_p,
                        "original_price": high_p if (high_p and high_p > low_p) else low_p,
                        "image_url": ld_img if isinstance(ld_img, str) else None,
                        "offer_url": clean_url,
                        "brand": extracted_meta["brand"],
                        "tech_specs": extracted_meta["tech_specs"],
                        "features": extracted_meta["features"],
                    }
        except Exception:
            pass

    # 3. Estrategia Estado Apollo VTEX IO embebido en el HTML de la página /p
    apollo_res = _parse_vtex_apollo_state(soup, clean_url)
    if apollo_res:
        if canonical_title and not validate_product_identity(
            canonical_title, apollo_res["title"], clean_url, store_id=store_id
        ):
            return None
        return apollo_res

    return None
