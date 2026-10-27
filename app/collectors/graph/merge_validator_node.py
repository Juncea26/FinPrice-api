"""
Nodo 5 del Grafo: MergeAnswersNode (merge_validator_node.py).
Inspirado en MergeAnswersNode de ScrapeGraphAI.
Consolida las ofertas extraídas de las 8 tiendas aplicando:
1. Validación sobre el Corpus Completo del Candidato (match_product_universal):
   full_corpus = f"{offer.title} {offer.offer_url} {json.dumps(offer.tech_specs)} {offer.description}".lower()
   con sus 6 reglas universales (colores ignorados, modelo/chip exacto sin sub-modelos intrusos,
   almacenamiento validado en el corpus completo, pulgadas exactas en TVs y equivalencia comercial
   10.9"==11" en tablets/laptops, conectividad Wi-Fi vs Cellular/5G).
2. Candado 1 de Identidad (validate_product_identity) y limpieza de URL canónica.
3. Deduplicación por tienda (mejor precio en stock por store_id).
4. Filtro Estadístico de Cordura de Precios y Anti-Outliers (0.55 <= price / median <= 1.65).
5. Actualización de la caché persistente de URLs verificadas (register_verified_store_url).
"""
from typing import Dict, List

from app.core.logging import get_logger
from app.collectors.catalog_urls import register_verified_store_url
from app.collectors.universal_matcher import (
    filter_offers_by_price_sanity,
    match_product_universal,
)
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.validators import (
    validate_cross_store_prices,
    validate_product_identity,
)
from app.collectors.graph.fetch_node import is_search_endpoint_url
from app.collectors.graph.state import (
    BaseGraphNode,
    ExtractedOfferSchema,
    GraphState,
    ProductTargetSpec,
)

logger = get_logger("collectors.graph.merge_validator_node")


class MergeAnswersNode(BaseGraphNode):
    """
    Nodo 5 (MergeAnswersNode): Valida el Corpus Completo de cada candidato,
    deduplica por tienda, elimina outliers estadísticos y ordena de menor a mayor precio.
    """

    node_name: str = "MergeAnswersNode"
    node_type: str = "node"

    def validate_single_offer_corpus(
        self,
        offer: ExtractedOfferSchema,
        target: ProductTargetSpec,
        strict_Cross_store_check: bool = True,
    ) -> bool:
        if not offer or offer.price <= 0 or not offer.in_stock:
            return False

        _, clean_url = canonicalize_store_url(offer.offer_url)
        offer.offer_url = clean_url or offer.offer_url

        if not offer.offer_url or is_search_endpoint_url(offer.offer_url):
            return False

        target_dict = target.to_target_dict()
        merged_specs = dict(target.tech_specs or {})
        merged_specs.update(offer.tech_specs or {})

        if not match_product_universal(target_dict, offer):
            return False

        if not validate_product_identity(
            canonical_title=target.title,
            scraped_title=offer.title,
            scraped_url=offer.offer_url,
            store_id=offer.store_id,
            tech_specs=offer.tech_specs or target.tech_specs,
            description=offer.description,
        ):
            return False

        return True

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        best_by_store: Dict[str, ExtractedOfferSchema] = {}

        # 1. Filtrar por Corpus Completo e Identidad y deduplicar por tienda (quedándose con el menor precio válido)
        for offer in state.extracted_offers:
            if not self.validate_single_offer_corpus(offer, target):
                continue

            existing = best_by_store.get(offer.store_id)
            if existing is None or offer.price < existing.price:
                best_by_store[offer.store_id] = offer

        identity_verified: List[ExtractedOfferSchema] = list(best_by_store.values())

        # 2. Filtro estadístico anti-outliers y cordura de precios (0.55 <= price / median <= 1.65)
        sanity_filtered = filter_offers_by_price_sanity(identity_verified)
        cross_store_clean = validate_cross_store_prices(sanity_filtered)

        # 3. Ordenar de menor a mayor precio y registrar URLs verificadas en la caché
        cross_store_clean.sort(key=lambda x: x.price)
        for verified_off in cross_store_clean:
            if target.id:
                register_verified_store_url(
                    product_id=target.id,
                    store_id=verified_off.store_id,
                    offer_url=verified_off.offer_url,
                )

        state.verified_offers = cross_store_clean
        state.execution_trace.append(
            f"MergeAnswersNode: verified_offers={len(cross_store_clean)} "
            f"(from {len(state.extracted_offers)} extracted)"
        )
        return state
