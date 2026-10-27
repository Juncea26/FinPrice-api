"""
Canonicalizador de URLs y soporte de las 8 estructuras oficiales de tiendas retail del Perú:
1. Falabella (falabella): https://www.falabella.com.pe/falabella-pe/product/{product_id}/{slug}/{sku_id}
2. Tottus (tottus): https://www.tottus.com.pe/tottus-pe/articulo/{product_id}/{slug}/{sku_id}
3. Ripley (ripley): https://simple.ripley.com.pe/{slug}-{part_number}p
4. Metro (metro): https://www.metro.pe/{slug}-{sku_id}/p
5. Wong (wong): https://www.wong.pe/{slug}-{sku_id}/p
6. Tiendas Efe (efe): https://www.efe.com.pe/{slug}.html
7. La Curacao (curacao): https://www.lacuracao.pe/{slug}.html
8. Hiraoka (hiraoka): https://hiraoka.com.pe/{slug}
"""
import re
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlparse, urlunparse

# Parámetros basura de publicidad, atribución y tracking que deben eliminarse siempre
AD_AND_TRACKING_PARAMS = {
    "kid",
    "gclsrc",
    "gad_source",
    "gad_campaignid",
    "gbraid",
    "wbraid",
    "gclid",
    "fbclid",
    "gsimpressionid",
    "s",
    "pos",
    "catpos",
    "p",
    "ps",
    "orig",
    "searchterm",
    "color_80",
    "ef_id",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ttclid",
    "twclid",
    "yclid",
    "_ga",
    "_gl",
}

# Parámetros legítimos de búsqueda que sí deben conservarse en URLs de buscador
ALLOWED_SEARCH_PARAMS = {"q", "ft", "fq", "ntt", "query"}

# Dominios canónicos por tienda
CANONICAL_HOSTS: Dict[str, str] = {
    "falabella": "www.falabella.com.pe",
    "tottus": "www.tottus.com.pe",
    "ripley": "simple.ripley.com.pe",
    "metro": "www.metro.pe",
    "wong": "www.wong.pe",
    "efe": "www.efe.com.pe",
    "curacao": "www.lacuracao.pe",
    "hiraoka": "hiraoka.com.pe",
}

# Expresiones regulares de validación de ruta de ficha de producto para las 8 tiendas
STORE_PRODUCT_PATH_PATTERNS: Dict[str, re.Pattern] = {
    "falabella": re.compile(r"^/falabella-pe/product/[^/]+/[^/]+(?:/[^/]+)?/?$", re.IGNORECASE),
    "tottus": re.compile(r"^/tottus-pe/(?:articulo|product)/[^/]+/[^/]+(?:/[^/]+)?/?$", re.IGNORECASE),
    "ripley": re.compile(r"^/[a-z0-9\-]+-(?:\d+p|pmp\d+|20\d{9,12})/?$", re.IGNORECASE),
    "metro": re.compile(r"^/[a-z0-9\-]+/p/?$", re.IGNORECASE),
    "wong": re.compile(r"^/[a-z0-9\-]+/p/?$", re.IGNORECASE),
    "efe": re.compile(r"^/[a-z0-9\-_]+\.html$", re.IGNORECASE),
    "curacao": re.compile(r"^/(?:[a-z0-9\-_]+\.html|catalog/product/view/.+)$", re.IGNORECASE),
    "hiraoka": re.compile(r"^/[a-z0-9\-_]+$", re.IGNORECASE),
}


def identify_store_from_host(host: str) -> str:
    """Identifica el store_id a partir del hostname."""
    h = (host or "").lower().strip()
    if "falabella.com.pe" in h:
        return "falabella"
    if "tottus.com.pe" in h:
        return "tottus"
    if "ripley.com.pe" in h:
        return "ripley"
    if "metro.pe" in h:
        return "metro"
    if "wong.pe" in h:
        return "wong"
    if "efe.com.pe" in h:
        return "efe"
    if "lacuracao.pe" in h:
        return "curacao"
    if "hiraoka.com.pe" in h:
        return "hiraoka"
    return "unknown"


def canonicalize_store_url(url: str) -> Tuple[str, str]:
    """
    Identifica la tienda (store_id) y limpia automáticamente todos los parámetros
    basura de publicidad (kid, gclsrc, gad_source, gad_campaignid, gbraid, gsImpressionId,
    s, pos, catPos, p, ps, orig, searchTerm, color_80, utm_*), conservando intacta
    la ruta real de cada tienda según su patrón oficial.
    """
    if not url or not str(url).strip():
        return ("unknown", "")

    raw = str(url).strip()
    parsed = urlparse(raw)
    store_id = identify_store_from_host(parsed.netloc)

    canonical_host = CANONICAL_HOSTS.get(store_id, parsed.netloc.lower())
    scheme = "https"

    # Normalizar ruta sin barra final innecesaria (excepto en rutas que terminan en /p si no la tienen)
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if len(path) > 1 and path.endswith("/") and not path.endswith("/view/"):
        path = path.rstrip("/")

    # Determinar si es una URL de búsqueda o de API
    is_search_or_api = any(
        seg in path.lower()
        for seg in ("/catalogsearch/", "/search", "/buscar", "/api/catalog_system/")
    )

    clean_query = ""
    if parsed.query:
        filtered_params = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=False):
            k_low = k.lower().strip()
            if k_low in AD_AND_TRACKING_PARAMS or k_low.startswith("utm_"):
                continue
            if is_search_or_api and k_low in ALLOWED_SEARCH_PARAMS:
                filtered_params.append((k, v))
        if filtered_params:
            clean_query = urlencode(filtered_params, quote_via=quote)

    canonical_url = urlunparse((scheme, canonical_host, path, "", clean_query, ""))
    return (store_id, canonical_url)


def is_valid_store_product_url(store_id: str, url: str) -> bool:
    """Verifica si una URL cumple con el patrón estructural de ficha de producto de esa tienda."""
    detected_store, clean_u = canonicalize_store_url(url)
    if detected_store != store_id or not clean_u:
        return False
    parsed = urlparse(clean_u)
    pattern = STORE_PRODUCT_PATH_PATTERNS.get(store_id)
    if not pattern:
        return False
    return bool(pattern.match(parsed.path))


def extract_vtex_slug_from_url(url: str) -> Optional[str]:
    """Extrae el slug de producto desde una URL VTEX (https://www.metro.pe/{slug}/p)."""
    _, clean_u = canonicalize_store_url(url)
    parsed = urlparse(clean_u)
    m = re.match(r"^/([a-z0-9\-]+)/p$", parsed.path, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def build_vtex_api_url_for_product(url: str) -> Optional[str]:
    """
    Construye el endpoint JSON de la API pública VTEX para una URL de ficha /p de Metro o Wong.
    Ej: https://www.metro.pe/api/catalog_system/pub/products/search/{slug}/p
    """
    store_id, clean_u = canonicalize_store_url(url)
    if store_id not in {"metro", "wong"}:
        return None
    slug = extract_vtex_slug_from_url(clean_u)
    if not slug:
        return None
    host = CANONICAL_HOSTS[store_id]
    return f"https://{host}/api/catalog_system/pub/products/search/{slug}/p"


def build_store_search_url(store_id: str, compact_query: str) -> Optional[str]:
    """Construye la URL de búsqueda oficial de la tienda a partir de una compact_search_query."""
    q_clean = re.sub(r"\s+", " ", (compact_query or "")).strip()
    if not q_clean or store_id not in CANONICAL_HOSTS:
        return None

    host = CANONICAL_HOSTS[store_id]
    if store_id in {"metro", "wong"}:
        return f"https://{host}/api/catalog_system/pub/products/search/?ft={quote(q_clean)}"
    if store_id in {"efe", "curacao", "hiraoka"}:
        return f"https://{host}/catalogsearch/result/?q={quote_plus(q_clean)}"
    if store_id == "falabella":
        return f"https://{host}/falabella-pe/search?Ntt={quote(q_clean)}"
    if store_id == "tottus":
        return f"https://{host}/tottus-pe/buscar?Ntt={quote(q_clean)}"
    if store_id == "ripley":
        return f"https://{host}/search/{quote(q_clean)}"
    return None
