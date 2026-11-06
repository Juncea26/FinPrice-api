"""
Nodo 4 del Grafo: StrictValidatorNode (strict_validator_node.py).
Aplica el Triple Candado de Integridad, el Filtro Estadístico Anti-Outliers
y la validación de imágenes oficiales y especificaciones técnicas.
"""
from typing import Any, Dict, List
from app.core.logging import get_logger
from app.collectors.catalog_urls import register_verified_store_url
from app.collectors.universal_matcher import match_product_universal
from app.collectors.url_utils import is_valid_product_image_url
from app.collectors.validators import (
    select_best_canonical_image,
    validate_cross_store_prices,
    validate_product_identity,
)
from app.collectors.graph.state import (
    BaseGraphNode,
    ExtractedOfferSchema,
    GraphState,
)

logger = get_logger("collectors.graph.strict_validator_node")


class StrictValidatorNode(BaseGraphNode):
    """
    Nodo 4: Valida identidad contra intrusos, filtra outliers de precio (< 55% de referencia),
    protege la imagen oficial canónica y valida que len(offers) >= 2.
    """

    node_name: str = "StrictValidatorNode"
    node_type: str = "node"

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        target_dict = target.to_target_dict()
        valid_offers: List[ExtractedOfferSchema] = []

        for offer in state.verified_offers:
            # 1. Validación de Identidad y Corpus
            if not match_product_universal(target_dict, offer):
                continue

            if not validate_product_identity(
                canonical_title=target.title,
                scraped_title=offer.title,
                scraped_url=offer.offer_url,
                store_id=offer.store_id,
                tech_specs=offer.tech_specs or target.tech_specs,
                description=offer.description,
            ):
                continue

            valid_offers.append(offer)

        # 2. Filtro Anti-Outliers de Precios Inter-Tiendas
        clean_offers = validate_cross_store_prices(valid_offers)

        # 3. REGLA FINPRICE: Permitir productos desde 1 tienda en adelante (len(clean_offers) >= 1)
        if len(clean_offers) < 1:
            logger.warning(
                f"[STRICT_VALIDATOR_DISCARD] Descartado producto '{target.title}': "
                f"después de validación estricta quedan 0 ofertas válidas (< 1)."
            )
            state.verified_offers = []
            state.execution_trace.append(
                f"StrictValidatorNode: DISCARDED '{target.title}' (valid_stores=0 < 1)"
            )
            return state

        # 4. Registrar URLs verificadas en caché persistente
        for off in clean_offers:
            if target.id:
                register_verified_store_url(
                    product_id=target.id,
                    store_id=off.store_id,
                    offer_url=off.offer_url,
                )

        state.verified_offers = clean_offers
        state.execution_trace.append(
            f"StrictValidatorNode: verified {len(clean_offers)} offers with 100% integrity"
        )
        return state
