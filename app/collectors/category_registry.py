"""
Registro declarativo y extensible de categorías de tecnología para las 8 tiendas 1P del Perú
(`falabella`, `ripley`, `tottus`, `efe`, `curacao`, `hiraoka`, `metro`, `wong`).

Proporciona:
1. Catálogo declarativo `CATEGORY_REGISTRY` cubriendo 14 categorías principales de tecnología
   sin hardcodear productos individuales.
2. Constructor de URLs paginadas por estrategia de tienda (`query_page`, `query_p`, `vtex_range`).
3. Clasificador genérico `infer_tech_category(title, url, default_category)` para categorizar
   productos provenientes de listados amplios o búsquedas transversales.
"""
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.collectors.tech_normalizer import _strip_bundles_and_colors, strip_accents_lower

ALL_TECH_STORES: Tuple[str, ...] = (
    "falabella",
    "ripley",
    "tottus",
    "efe",
    "curacao",
    "hiraoka",
    "metro",
    "wong",
)

ALL_TECH_CATEGORIES: Tuple[str, ...] = (
    "celulares",
    "laptops",
    "tablets",
    "televisores",
    "impresoras",
    "consolas",
    "monitores",
    "audifonos",
    "smartwatches",
    "audio",
    "camaras",
    "almacenamiento_redes",
    "accesorios_pc",
    "smart_home",
)

# Nombres canónicos en la tabla `products` (preserva los 5 nombres históricos de Android)
CATEGORY_CATALOG_DISPLAY_NAMES: Dict[str, str] = {
    "celulares": "Smartphones",
    "laptops": "Laptops",
    "tablets": "Tablets",
    "televisores": "TVs",
    "impresoras": "Impresoras",
    "consolas": "Consolas",
    "monitores": "Monitores",
    "audifonos": "Audífonos",
    "smartwatches": "Smartwatches",
    "audio": "Audio",
    "camaras": "Cámaras",
    "almacenamiento_redes": "Almacenamiento y Redes",
    "accesorios_pc": "Accesorios PC",
    "smart_home": "Smart Home",
    "otros_tech": "Otros Tech",
}

_CATEGORY_FILTER_ALIASES: Dict[str, str] = {
    "celulares": "Smartphones",
    "celular": "Smartphones",
    "smartphones": "Smartphones",
    "smartphone": "Smartphones",
    "laptops": "Laptops",
    "laptop": "Laptops",
    "notebooks": "Laptops",
    "notebook": "Laptops",
    "tablets": "Tablets",
    "tablet": "Tablets",
    "ipads": "Tablets",
    "ipad": "Tablets",
    "televisores": "TVs",
    "televisor": "TVs",
    "tvs": "TVs",
    "tv": "TVs",
    "smart tv": "TVs",
    "impresoras": "Impresoras",
    "impresora": "Impresoras",
    "multifuncionales": "Impresoras",
    "consolas": "Consolas",
    "consola": "Consolas",
    "gaming": "Consolas",
    "videojuegos": "Consolas",
    "monitores": "Monitores",
    "monitor": "Monitores",
    "audifonos": "Audífonos",
    "audifono": "Audífonos",
    "auriculares": "Audífonos",
    "headsets": "Audífonos",
    "smartwatches": "Smartwatches",
    "smartwatch": "Smartwatches",
    "wearables": "Smartwatches",
    "relojes": "Smartwatches",
    "audio": "Audio",
    "parlantes": "Audio",
    "soundbars": "Audio",
    "camaras": "Cámaras",
    "camara": "Cámaras",
    "fotografia": "Cámaras",
    "drones": "Cámaras",
    "almacenamiento_redes": "Almacenamiento y Redes",
    "almacenamiento y redes": "Almacenamiento y Redes",
    "almacenamiento": "Almacenamiento y Redes",
    "redes": "Almacenamiento y Redes",
    "accesorios_pc": "Accesorios PC",
    "accesorios pc": "Accesorios PC",
    "accesorios y perifericos": "Accesorios PC",
    "accesorios y perifericos de pc": "Accesorios PC",
    "perifericos": "Accesorios PC",
    "smart_home": "Smart Home",
    "smart home": "Smart Home",
    "smart home y domotica": "Smart Home",
    "domotica": "Smart Home",
    "otros_tech": "Otros Tech",
    "otros tech": "Otros Tech",
}


def resolve_category_display_name(slug_or_name: str) -> str:
    """Convierte un slug de categoría (`celulares`, `consolas`) al nombre canónico en `products`."""
    raw = str(slug_or_name or "").strip()
    if not raw:
        return "Otros Tech"
    low = strip_accents_lower(raw)
    if low in CATEGORY_CATALOG_DISPLAY_NAMES:
        return CATEGORY_CATALOG_DISPLAY_NAMES[low]
    if low in _CATEGORY_FILTER_ALIASES:
        return _CATEGORY_FILTER_ALIASES[low]
    return raw


def matches_category_filter(product_category: str, query_category: str) -> bool:
    """Compara categorías aceptando slugs (`consolas`, `celulares`) y nombres (`Consolas`, `Smartphones`)."""
    p_low = strip_accents_lower(str(product_category or "").strip())
    q_low = strip_accents_lower(str(query_category or "").strip())
    if not p_low or not q_low:
        return False
    if p_low == q_low:
        return True
    p_canon = _CATEGORY_FILTER_ALIASES.get(p_low, p_low)
    q_canon = _CATEGORY_FILTER_ALIASES.get(q_low, q_low)
    return p_canon.lower() == q_canon.lower()


@dataclass(frozen=True)
class StoreCategorySource:
    """Fuente paginada de listados para una combinación (tienda, categoría)."""

    store: str
    category: str
    url: str
    pagination: str  # "query_page" | "query_p" | "vtex_range"
    page_size: int = 48
    is_broad_category: bool = False


@dataclass(frozen=True)
class CategorySpec:
    """Definición declarativa de una categoría tecnológica y sus fuentes por tienda."""

    slug: str
    display_name: str
    is_accessory_category: bool
    min_valid_price_pen: float
    store_sources: Dict[str, Tuple[StoreCategorySource, ...]]


def _src(
    store: str,
    category: str,
    url: str,
    pagination: str,
    page_size: int = 48,
    is_broad_category: bool = False,
) -> Tuple[StoreCategorySource, ...]:
    return (
        StoreCategorySource(
            store=store,
            category=category,
            url=url,
            pagination=pagination,
            page_size=page_size,
            is_broad_category=is_broad_category,
        ),
    )


def _build_default_category_registry() -> Dict[str, CategorySpec]:
    """Construye el registro declarativo para las 14 categorías tech en las 8 tiendas 1P."""
    configs: Tuple[Tuple[str, str, bool, float, Dict[str, Tuple[Any, ...]]], ...] = (
        (
            "celulares",
            "Celulares y Smartphones",
            False,
            180.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat760706/Celulares-y-Telefonos?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/celulares/celulares-y-smartphones?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=celulares",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/celulares.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/celulares.html", False),
                "hiraoka": ("https://hiraoka.com.pe/celulares-y-telefonia/celulares/smartphones", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/telefonia/celulares-y-smartphones",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/telefonia/celulares-y-smartphones",
                    False,
                ),
            },
        ),
        (
            "laptops",
            "Laptops y Notebooks",
            False,
            500.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40712/Laptops?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/computacion/laptops?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=laptops",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/computacion/laptops.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/computacion/laptops.html", False),
                "hiraoka": ("https://hiraoka.com.pe/computo-y-tablets/computadoras/laptops", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/computo/laptops",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/laptops",
                    False,
                ),
            },
        ),
        (
            "tablets",
            "Tablets e iPads",
            False,
            180.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat270476/Tablets?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/computacion/tablets?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=tablets",
                    False,
                ),
                "efe": (
                    "https://www.efe.com.pe/tecnologia/computacion/tablets-y-tabletas-graficas.html",
                    False,
                ),
                "curacao": (
                    "https://www.lacuracao.pe/tecnologia/computacion/tablets-y-tabletas-graficas.html",
                    False,
                ),
                "hiraoka": ("https://hiraoka.com.pe/computo-y-tablets/tablets", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/computo/tablets",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/tablets",
                    False,
                ),
            },
        ),
        (
            "televisores",
            "Televisores y Smart TV",
            False,
            300.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat210477/TV-Televisores?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/tv-y-cine-en-casa/televisores?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=televisores",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/televisores.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/televisores.html", False),
                "hiraoka": ("https://hiraoka.com.pe/televisores/televisores", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/televisores/tv",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/televisores/tv",
                    False,
                ),
            },
        ),
        (
            "impresoras",
            "Impresoras y Multifuncionales",
            False,
            150.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat3180533/Impresoras?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/computacion/impresoras-y-tintas?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=impresoras",
                    False,
                ),
                "efe": (
                    "https://www.efe.com.pe/tecnologia/computacion/impresoras-y-multifuncionales.html",
                    False,
                ),
                "curacao": (
                    "https://www.lacuracao.pe/tecnologia/computacion/impresoras-y-multifuncionales.html",
                    False,
                ),
                "hiraoka": ("https://hiraoka.com.pe/computo-y-tablets/impresoras-y-tintas", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/computo/impresoras-y-tintas",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/impresoras-y-tintas",
                    False,
                ),
            },
        ),
        (
            "consolas",
            "Consolas de Videojuegos",
            False,
            350.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40556/consolas?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/videojuegos/consolas?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=consolas",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/videojuegos/consolas.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/videojuegos/consolas.html", False),
                "hiraoka": ("https://hiraoka.com.pe/gaming/consolas", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/zona-gamer/consolas",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/zona-gamer/consolas",
                    False,
                ),
            },
        ),
        (
            "monitores",
            "Monitores",
            False,
            180.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40695/Monitores?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/computacion/monitores?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=monitores",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/computacion/monitores.html", False),
                "curacao": ("https://www.lacuracao.pe/catalogsearch/result/?q=monitores", False),
                "hiraoka": ("https://hiraoka.com.pe/computo-y-tablets/monitores", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/?ft=monitor",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/?ft=monitor",
                    False,
                ),
            },
        ),
        (
            "audifonos",
            "Audífonos y Headsets",
            True,
            20.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat800582/Audifonos?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/audio/audifonos?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=audifonos",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/audifonos.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/audifonos.html", False),
                "hiraoka": ("https://hiraoka.com.pe/audio-y-musica/audifonos", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/audio/audifonos",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/audio/audifonos",
                    False,
                ),
            },
        ),
        (
            "smartwatches",
            "Smartwatches y Wearables",
            True,
            45.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat1830468/Smartwatch-y-wearables?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/celulares/smartwatch-y-wearables?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=smartwatch",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/celulares/smartwatch.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/celulares/smartwatch.html", False),
                "hiraoka": ("https://hiraoka.com.pe/celulares-y-telefonia/smartwatch", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/?ft=smartwatch",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/?ft=smartwatch",
                    False,
                ),
            },
        ),
        (
            "audio",
            "Audio, Parlantes y Soundbars",
            False,
            50.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40488/Audio?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/audio/equipos-de-sonido?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=parlantes",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/audio.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/audio.html", False),
                "hiraoka": ("https://hiraoka.com.pe/audio-y-musica/audio", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/audio/parlantes",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/audio/parlantes",
                    False,
                ),
            },
        ),
        (
            "camaras",
            "Cámaras y Drones",
            False,
            80.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40812/Fotografia?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/camara-de-fotos/ver-todo?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=camaras",
                    False,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/fotografia-y-video.html", False),
                "curacao": ("https://www.lacuracao.pe/tecnologia/fotografia-y-video.html", False),
                "hiraoka": ("https://hiraoka.com.pe/camaras-y-drones", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/camaras",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/camaras",
                    False,
                ),
            },
        ),
        (
            "almacenamiento_redes",
            "Almacenamiento y Redes",
            True,
            25.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/search?Ntt=router+wifi+tp-link&f.derived.variant.sellerId=FALABELLA",
                    True,
                ),
                # Ripley SSR no soporta filtro de vendedor 1P en query string (`seller_facet` corre en microfrontend cliente);
                # rutas verificadas HTTP 200 con inventario 1P filtrado luego por `_is_ripley_search_item_official`.
                "ripley": (
                    (
                        "https://simple.ripley.com.pe/tecnologia/computacion/disco-duro-y-memorias?s=mdco",
                        False,
                    ),
                    (
                        "https://simple.ripley.com.pe/tecnologia/smart-home/routers-y-modems?s=mdco",
                        False,
                    ),
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=memoria+usb+microsd",
                    True,
                ),
                "efe": (
                    "https://www.efe.com.pe/catalogsearch/result/?q=router+wifi",
                    True,
                ),
                "curacao": (
                    "https://www.lacuracao.pe/catalogsearch/result/?q=router+wifi",
                    True,
                ),
                "hiraoka": (
                    "https://hiraoka.com.pe/computo-y-tablets/accesorios-computo/almacenamiento-externo",
                    False,
                ),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/computo/almacenamiento",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/almacenamiento",
                    False,
                ),
            },
        ),
        (
            "accesorios_pc",
            "Accesorios y Periféricos de PC",
            True,
            15.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat40509/Accesorios-Computacion-y-Perifericos?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                # `/tecnologia/accesorios-computacion` responde 404 en Ripley; mouse y teclados son 200 OK con 1P.
                "ripley": (
                    (
                        "https://simple.ripley.com.pe/tecnologia/computacion/mouse?s=mdco",
                        False,
                    ),
                    (
                        "https://simple.ripley.com.pe/tecnologia/computacion/teclados?s=mdco",
                        False,
                    ),
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=mouse",
                    True,
                ),
                "efe": (
                    "https://www.efe.com.pe/catalogsearch/result/?q=mouse",
                    True,
                ),
                "curacao": (
                    "https://www.lacuracao.pe/catalogsearch/result/?q=mouse",
                    True,
                ),
                "hiraoka": ("https://hiraoka.com.pe/computo-y-tablets/accesorios-computo", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/computo/accesorios-de-computo",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/accesorios-de-computo",
                    False,
                ),
            },
        ),
        (
            "smart_home",
            "Smart Home y Domótica",
            True,
            20.0,
            {
                "falabella": (
                    "https://www.falabella.com.pe/falabella-pe/category/cat11190471/Domotica-y-Smart-Home?f.derived.variant.sellerId=FALABELLA",
                    False,
                ),
                # Nota: el árbol smart-home/ver-todo y monitores en Ripley SSR devuelve actualmente 100% Marketplace
                # (0 ítems en `seller_facet=Ripley`); `_is_ripley_search_item_official` descarta todo tercero.
                "ripley": (
                    "https://simple.ripley.com.pe/tecnologia/smart-home/ver-todo?s=mdco",
                    False,
                ),
                "tottus": (
                    "https://www.tottus.com.pe/tottus-pe/buscar?Ntt=chromecast+google+nest+alexa",
                    True,
                ),
                "efe": ("https://www.efe.com.pe/tecnologia/smart-home-y-domotica.html", False),
                "curacao": (
                    "https://www.lacuracao.pe/tecnologia/smart-home-y-domotica.html",
                    False,
                ),
                "hiraoka": ("https://hiraoka.com.pe/smarthome", False),
                "metro": (
                    "https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/smart-home-y-domotica",
                    False,
                ),
                "wong": (
                    "https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/smart-home-y-domotica",
                    False,
                ),
            },
        ),
    )

    pagination_by_store = {
        "falabella": "query_page",
        "tottus": "query_page",
        "ripley": "query_page",
        "efe": "query_p",
        "curacao": "query_p",
        "hiraoka": "query_p",
        "metro": "vtex_range",
        "wong": "vtex_range",
    }

    registry: Dict[str, CategorySpec] = {}
    for slug, display_name, is_acc, min_price, store_urls in configs:
        sources: Dict[str, Tuple[StoreCategorySource, ...]] = {}
        for store_id in ALL_TECH_STORES:
            raw_entry = store_urls[store_id]
            if (
                isinstance(raw_entry, tuple)
                and len(raw_entry) == 2
                and isinstance(raw_entry[0], str)
                and isinstance(raw_entry[1], bool)
            ):
                entries: Tuple[Tuple[str, bool], ...] = (raw_entry,)
            else:
                entries = tuple(raw_entry)
            sources[store_id] = tuple(
                StoreCategorySource(
                    store=store_id,
                    category=slug,
                    url=u,
                    pagination=pagination_by_store[store_id],
                    page_size=48,
                    is_broad_category=ib,
                )
                for u, ib in entries
            )
        registry[slug] = CategorySpec(
            slug=slug,
            display_name=display_name,
            is_accessory_category=is_acc,
            min_valid_price_pen=min_price,
            store_sources=sources,
        )
    return registry


CATEGORY_REGISTRY: Dict[str, CategorySpec] = _build_default_category_registry()


def get_category_spec(slug: str) -> Optional[CategorySpec]:
    """Devuelve la especificación declarativa para un slug de categoría normalizado."""
    if not slug:
        return None
    return CATEGORY_REGISTRY.get(slug.strip().lower())


def list_registered_categories() -> List[str]:
    """Retorna la lista ordenada de slugs de categorías tecnológicas registradas."""
    return list(ALL_TECH_CATEGORIES)


def get_store_category_sources(
    stores: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
) -> List[StoreCategorySource]:
    """
    Resuelve de forma declarativa todas las fuentes `(store, category)` a barrer
    respetando filtros opcionales de tiendas y categorías.
    """
    target_stores = (
        [s.strip().lower() for s in stores if s and s.strip()]
        if stores is not None
        else list(ALL_TECH_STORES)
    )
    target_categories = (
        [c.strip().lower() for c in categories if c and c.strip()]
        if categories is not None
        else list(ALL_TECH_CATEGORIES)
    )

    resolved: List[StoreCategorySource] = []
    for cat_slug in target_categories:
        spec = get_category_spec(cat_slug)
        if spec is None:
            continue
        for store_id in target_stores:
            resolved.extend(spec.store_sources.get(store_id, ()))
    return resolved


def build_paginated_category_url(source: StoreCategorySource, page: int) -> str:
    """
    Construye la URL exacta de la página `page` (>= 1) según la estrategia de
    paginación real de la tienda (`query_page`, `query_p` o `vtex_range`).
    """
    if page < 1:
        raise ValueError("El número de página debe ser >= 1.")

    parsed = urlsplit(source.url)
    params = parse_qsl(parsed.query, keep_blank_values=True)

    if source.pagination == "query_page":
        updated = [(k, v) for k, v in params if k != "page"]
        updated.append(("page", str(page)))
    elif source.pagination == "query_p":
        has_p = any(k == "p" for k, _ in params)
        if page == 1 and not has_p:
            return source.url
        updated = [(k, v) for k, v in params if k != "p"]
        updated.append(("p", str(page)))
    elif source.pagination == "vtex_range":
        offset_from = (page - 1) * source.page_size
        offset_to = (page * source.page_size) - 1
        updated = [(k, v) for k, v in params if k not in {"_from", "_to"}]
        updated.extend([("_from", str(offset_from)), ("_to", str(offset_to))])
    else:
        raise ValueError(f"Estrategia de paginación no soportada: {source.pagination!r}")

    new_query = urlencode(updated, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, ""))


_EXTRA_GIFT_TAIL_RE = re.compile(
    r"\s*\+\s*(?:smartwatch|reloj|juego|videojuego|mando|control|ea\s+sports)\b.*$",
    flags=re.IGNORECASE,
)

_ACCESSORY_LEAD_PREFIXES: Tuple[str, ...] = (
    "funda ",
    "case ",
    "carcasa ",
    "estuche ",
    "mica ",
    "vidrio templado ",
    "protector ",
    "correa ",
    "malla ",
    "pulsera ",
    "cargador ",
    "cable ",
    "adaptador ",
    "soporte ",
    "rack ",
    "mochila ",
    "maletin ",
    "bolso ",
    "sleeve ",
)

_CONSUMABLE_WORDS_RE = re.compile(
    r"\b(?:botella|botellas|cartucho|cartuchos|toner|cabezal|recarga|repuesto|tambor|tinta\s+para)\b"
)

_CONSOLE_NON_HARDWARE_PREFIX_RE = re.compile(
    r"^(?:juego|videojuego|mando|control|estuche|funda|cargador|soporte|gift\s+card|membresia|tarjeta\s+de\s+regalo)\b"
)


def _contains_any_term(text: str, terms: Sequence[str]) -> bool:
    for term in terms:
        t = term.strip()
        if not t:
            continue
        if len(t) <= 4 or " " not in t:
            if re.search(rf"\b{re.escape(t)}", text):
                # Para abreviaturas cortas como 'ps5'/'ps4'/'nas', exigir borde derecho también
                if t in {"ps5", "ps4", "nas", "xps", "loq", "tuf"}:
                    if re.search(rf"\b{re.escape(t)}\b", text):
                        return True
                else:
                    return True
        else:
            if t in text:
                return True
    return False


def _classify_clean_text(clean_text: str) -> Optional[str]:
    if not clean_text:
        return None

    has_acc_lead = clean_text.startswith(_ACCESSORY_LEAD_PREFIXES)
    has_consumable = bool(_CONSUMABLE_WORDS_RE.search(clean_text))

    # 1. Audífonos
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "audifono",
            "audifonos",
            "auricular",
            "auriculares",
            "airpods",
            "earbuds",
            "galaxy buds",
            "redmi buds",
            "freebuds",
            "headset",
            "headphone",
            "wh-1000xm",
            "wf-1000xm",
        ),
    ):
        return "audifonos"

    # 2. Smartwatches y Wearables
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "smartwatch",
            "smartwatches",
            "reloj inteligente",
            "apple watch",
            "galaxy watch",
            "galaxy fit",
            "huawei watch",
            "redmi watch",
            "xiaomi watch",
            "honor watch",
            "amazfit",
            "smart band",
            "smartband",
            "mi band",
            "fitbit",
            "garmin",
        ),
    ):
        return "smartwatches"

    # 3. Almacenamiento y Redes
    if _contains_any_term(
        clean_text,
        (
            "router",
            "modem",
            "repetidor",
            "access point",
            "wifi mesh",
            "deco ",
            "switch de red",
            "adaptador usb wifi",
            "disco duro externo",
            "ssd externo",
            "disco solido externo",
            "memoria usb",
            "pendrive",
            "flash drive",
            "microsd",
            "tarjeta de memoria",
            "nas",
        ),
    ):
        return "almacenamiento_redes"

    # 4. Accesorios y Periféricos PC
    if _contains_any_term(
        clean_text,
        (
            "mouse",
            "raton",
            "teclado",
            "keyboard",
            "webcam",
            "camara web",
            "cooler para laptop",
            "base para laptop",
            "soporte para laptop",
            "soporte para monitor",
            "pad mouse",
            "mousepad",
            "mouse pad",
            "hub usb",
            "docking",
            "capturadora",
            "microfono usb",
            "microfono gamer",
            "tableta grafica",
            "wacom",
            "mando ",
            "control inalambrico",
            "dualsense",
            "joy-con",
            "joycon",
            "joystick",
        ),
    ):
        return "accesorios_pc"

    # 5. Consolas (excluyendo juegos, mandos y estuches cuando el título base empieza por ellos)
    if not _CONSOLE_NON_HARDWARE_PREFIX_RE.match(clean_text) and _contains_any_term(
        clean_text,
        (
            "consola",
            "playstation 5",
            "ps5",
            "playstation 4",
            "ps4",
            "nintendo switch",
            "xbox series",
            "steam deck",
            "rog ally",
            "legion go",
        ),
    ):
        return "consolas"

    # 6. Monitores
    if not has_acc_lead and _contains_any_term(
        clean_text,
        ("monitor", "monitores", "ultragear", "odyssey g", "zenscreen"),
    ):
        return "monitores"

    # 7. Impresoras (excluye consumibles/tintas sueltas sin palabra de equipo)
    has_printer_noun = _contains_any_term(
        clean_text, ("impresora", "multifuncional", "escaner")
    )
    if not has_consumable or has_printer_noun:
        if _contains_any_term(
            clean_text,
            (
                "impresora",
                "multifuncional",
                "ecotank",
                "smart tank",
                "pixma",
                "laserjet",
                "deskjet",
                "escaner",
            ),
        ):
            return "impresoras"

    # 8. Cámaras y Drones
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "camara digital",
            "camara mirrorless",
            "camara reflex",
            "dslr",
            "camara instantanea",
            "instax",
            "camara deportiva",
            "camara de accion",
            "gopro",
            "insta360",
            "videocamara",
            "camara de video",
            "handycam",
            "dron",
            "drone",
            "dji ",
            "eos r",
            "zv-e",
            "alpha a6",
            "alpha a7",
        ),
    ):
        return "camaras"

    # 9. Smart Home y Domótica
    if _contains_any_term(
        clean_text,
        (
            "echo dot",
            "echo pop",
            "echo show",
            "alexa",
            "nest mini",
            "nest hub",
            "chromecast",
            "google tv streamer",
            "fire tv",
            "roku",
            "apple tv 4k",
            "tv box",
            "mi box",
            "foco inteligente",
            "enchufe inteligente",
            "interruptor inteligente",
            "cerradura inteligente",
            "sensor inteligente",
            "aspiradora robot",
            "camara de seguridad",
            "camara wifi",
            "tapo c",
            "domotica",
            "smart home",
        ),
    ):
        return "smart_home"

    # 10. Audio (no confundir con laptops/TVs que mencionan parlantes integrados)
    is_main_screen_device = _contains_any_term(
        clean_text,
        ("laptop", "notebook", "televisor", "smart tv", "celular", "smartphone", "tablet", "ipad"),
    )
    if not has_acc_lead and not is_main_screen_device and _contains_any_term(
        clean_text,
        (
            "parlante",
            "altavoz",
            "bocina",
            "soundbar",
            "barra de sonido",
            "home theater",
            "minicomponente",
            "equipo de sonido",
            "torre de sonido",
            "one body",
            "one box",
            "partybox",
            "xboom",
            "boombox",
            "subwoofer",
            "radio portatil",
        ),
    ):
        return "audio"

    # 11. Tablets (evaluada antes que celulares para no clasificar Galaxy Tab como celular)
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "tablet",
            "tableta",
            "ipad",
            "galaxy tab",
            "redmi pad",
            "xiaomi pad",
            "matepad",
            "idea tab",
            "lenovo tab",
            "honor pad",
        ),
    ):
        return "tablets"

    # 12. Laptops
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "laptop",
            "notebook",
            "macbook",
            "ideapad",
            "thinkpad",
            "legion",
            "loq",
            "vivobook",
            "zenbook",
            "rog strix",
            "rog zephyrus",
            "asus tuf",
            "hp victus",
            "hp omen",
            "pavilion",
            "acer nitro",
            "aspire",
            "predator",
            "inspiron",
            "latitude",
            "xps",
            "imac",
            "all in one",
        ),
    ):
        return "laptops"

    # 13. Televisores
    if not has_acc_lead and (
        _contains_any_term(
            clean_text,
            (
                "televisor",
                "smart tv",
                "oled tv",
                "qled",
                "neo qled",
                "qned",
                "nanocell",
                "crystal uhd",
                "mini led",
                "miniled",
            ),
        )
        or bool(re.search(r"\b(?:oled|qned|qn)(?:32|42|43|48|50|55|65|75|77|83|85)\b", clean_text))
    ):
        return "televisores"

    # 14. Celulares
    if not has_acc_lead and _contains_any_term(
        clean_text,
        (
            "celular",
            "smartphone",
            "iphone",
            "galaxy s",
            "galaxy a",
            "galaxy z",
            "galaxy m",
            "redmi note",
            "redmi 1",
            "redmi a",
            "poco x",
            "poco f",
            "poco m",
            "poco c",
            "moto g",
            "motorola edge",
            "razr",
            "honor magic",
            "honor x",
            "honor 200",
            "honor 400",
            "huawei pura",
            "xiaomi 14",
            "xiaomi 15",
            "realme",
            "oppo reno",
            "oppo a",
        ),
    ):
        return "celulares"

    return None


def infer_tech_category(
    title: str,
    url: str = "",
    default_category: str = "otros_tech",
) -> str:
    """
    Clasifica de forma genérica un producto tecnológico a partir de su título y URL.
    Útil para listados amplios (ej. `/tecnologia`, `/computo` o búsquedas transversales).
    """
    norm_raw = strip_accents_lower(title or "")
    raw_title = _strip_bundles_and_colors(norm_raw)
    raw_title = _EXTRA_GIFT_TAIL_RE.sub("", raw_title).strip()
    norm_title = re.sub(r"\s+", " ", raw_title).strip()

    matched = _classify_clean_text(norm_title)
    if matched:
        return matched

    if url:
        parsed_path = urlsplit(url).path or url
        norm_url = re.sub(r"[/\-_\.]+", " ", strip_accents_lower(parsed_path))
        norm_url = re.sub(r"\s+", " ", norm_url).strip()
        matched_url = _classify_clean_text(norm_url)
        if matched_url:
            return matched_url

    return default_category
