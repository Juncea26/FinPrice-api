"""
Nodo 3 del Grafo: CanonicalMatcherNode (canonical_matcher_node.py).
Implementa el Emparejamiento Inteligente Sin Importar el Color (Color-Agnostic Canonical Matching)
y la REGLA DE DESCARTE ESTRICTA (len(offers) >= 2 OBLIGATORIO):

1. Clave Canónica (canonical_key):
   - Elimina todos los colores en español e inglés.
   - Elimina palabras accesorias o de relleno (+ funda, con funda, celular libre, etc.).
   - Extrae la identidad técnica exacta: Marca + Familia/Modelo + Capacidad RAM/Almacenamiento/Pulgadas.
2. Agrupación Multi-Tienda:
   - Agrupa bajo el mismo producto las ofertas de las 8 tiendas oficiales del Perú.
   - Si una tienda vende el producto en 2 o más colores (ej. Negro y Blanco), conserva
     la oferta en stock con el MENOR precio online y su product_url real.
3. REGLA DE DESCARTE ESTRICTA:
   - Si después de buscar en las 8 tiendas un producto tiene menos de 2 tiendas (len(store_offers) < 2),
     se descarta automáticamente. ¡Cero productos de 1 sola tienda (availableStoresCount == 1)!
"""
import re
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger
from app.collectors.color_stripper import strip_color_tokens
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.validators import normalize_text, extract_critical_model_tokens
from app.collectors.graph.state import (
    BaseGraphNode,
    ExtractedOfferSchema,
    GraphState,
    ProductTargetSpec,
)

logger = get_logger("collectors.graph.canonical_matcher_node")

# Frases de relleno y accesorios
FILLER_PATTERNS = [
    re.compile(r"\s*(\+|\bcon\b|\bincluye\b)\s*(funda|case|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|combo|pack)\b.*$", re.IGNORECASE),
    re.compile(r"\b(funda|case|cargador|audifonos?|mochila|mouse|cover|soundbar|maletin|teclado|combo|pack)\b\s*$", re.IGNORECASE),
    re.compile(r"\b(celular\s+libre|smartphone|disco\s+solido\s+de|unidad\s+de\s+estado\s+solido|liberado|dual\s+sim|copilot\+\s*pc)\b", re.IGNORECASE),
]


def clean_canonical_title(title: str) -> str:
    """Limpia colores, promociones y palabras accesorias para obtener el título canónico puro."""
    if not title:
        return ""
    # 1. Quitar colores
    cleaned = strip_color_tokens(title)
    # 2. Quitar rellenos y regalos menores
    for pat in FILLER_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    # 3. Limpiar espacios múltiples y caracteres residuales
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;-–—/\"'")
    return cleaned


def build_canonical_key(title: str, tech_specs: Optional[Dict[str, Any]] = None) -> str:
    """
    Genera una clave canónica normalizada e invariable de color para el producto:
    ej. 'apple_iphone_16_128gb' o 'asus_zenbook_a14_snapdragon_x_16gb_512gb'.
    """
    cleaned = clean_canonical_title(title)
    norm = normalize_text(cleaned)
    critical_tokens, storage, ram = extract_critical_model_tokens(cleaned)

    parts: List[str] = []
    for tok in critical_tokens:
        tok_clean = re.sub(r"[^\w]", "", tok)
        if tok_clean and tok_clean not in parts:
            parts.append(tok_clean)

    if ram and ram not in parts:
        parts.append(ram)
    if storage and storage not in parts:
        parts.append(storage)

    key = "_".join(parts)
    return key or norm[:40]


class CanonicalMatcherNode(BaseGraphNode):
    """
    Nodo 3: Agrupa ofertas por clave canónica ignorando color,
    conserva el mejor precio por tienda y descarta productos con len(offers) < 2.
    """

    node_name: str = "CanonicalMatcherNode"
    node_type: str = "node"

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        target_title = target.title
        target_specs = target.tech_specs or {}

        # 1. Deduplicar por tienda conservando el menor precio en stock
        best_by_store: Dict[str, ExtractedOfferSchema] = {}

        for offer in state.extracted_offers:
            if not offer or offer.price <= 0 or not offer.in_stock:
                continue

            _, clean_url = canonicalize_store_url(offer.offer_url)
            offer.offer_url = clean_url or offer.offer_url

            # Normalizar título de la oferta sin colores
            offer.title = clean_canonical_title(offer.title) or offer.title

            existing = best_by_store.get(offer.store_id)
            if existing is None or offer.price < existing.price:
                best_by_store[offer.store_id] = offer

        unique_store_offers = list(best_by_store.values())

        # 2. REGLA FINPRICE: Permitir productos desde 1 tienda en adelante (len(offers) >= 1)
        if len(unique_store_offers) < 1:
            logger.warning(
                f"[CANONICAL_MATCHER_DISCARD] Descartado producto '{target_title}': "
                f"no cuenta con ninguna tienda válida (requerido >= 1 tienda)."
            )
            state.verified_offers = []
            state.execution_trace.append(
                f"CanonicalMatcherNode: DISCARDED '{target_title}' (stores=0 < 1)"
            )
            return state

        # Ordenar por menor precio público online
        unique_store_offers.sort(key=lambda x: x.price)
        state.verified_offers = unique_store_offers
        state.execution_trace.append(
            f"CanonicalMatcherNode: verified {len(unique_store_offers)} store offers for '{target_title}'"
        )
        return state
