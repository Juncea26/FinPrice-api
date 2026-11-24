"""
Extractor real para Tottus Perú (tottus.com.pe).
Soporta URLs https://www.tottus.com.pe/tottus-pe/articulo/{productId}/{slug}/{skuId}
y /tottus-pe/product/..., compartiendo la arquitectura Next.js (#__NEXT_DATA__ + JSON-LD) del grupo Falabella.
"""
from typing import Any, Dict, Optional, Set
from bs4 import BeautifulSoup
import json

from app.collectors.parsers.falabella import parse_falabella
from app.collectors.spec_extractor import normalize_brand
from app.collectors.url_utils import canonicalize_store_url


def parse_tottus(
    html: str,
    offer_url: str,
    canonical_title: Optional[str] = None,
    seen_candidate_urls: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extrae desde #__NEXT_DATA__ y JSON-LD de Tottus el precio CMR/Internet,
    precio regular, imagen oficial, marca real y tabla de especificaciones técnicas.
    """
    if not html:
        return None

    _, clean_url = canonicalize_store_url(offer_url)
    res = parse_falabella(
        html,
        clean_url or offer_url,
        canonical_title=canonical_title,
        seen_candidate_urls=seen_candidate_urls,
    )
    if not res:
        return None

    # En Tottus el bloque JSON-LD Product suele traer el objeto brand.name exacto (ej. 'JVC')
    soup = BeautifulSoup(html, "lxml")
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            j = json.loads(s.string)
            if isinstance(j, dict) and j.get("@type") == "Product":
                b_obj = j.get("brand")
                b_name = b_obj.get("name") if isinstance(b_obj, dict) else b_obj
                if b_name and isinstance(b_name, str):
                    norm_b = normalize_brand(b_name, res.get("title", ""))
                    if norm_b:
                        res["brand"] = norm_b
                        if isinstance(res.get("tech_specs"), dict):
                            res["tech_specs"]["Marca"] = norm_b
                        break
        except Exception:
            pass

    _, final_clean_url = canonicalize_store_url(str(res.get("offer_url") or clean_url or offer_url))
    res["offer_url"] = final_clean_url or res.get("offer_url") or clean_url or offer_url
    return res
