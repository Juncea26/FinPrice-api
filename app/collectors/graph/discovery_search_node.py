"""
Nodo 1 del Grafo: DiscoverySearchNode (discovery_search_node.py).
Descubre URLs y grillas de candidatos en las 8 tiendas oficiales del retail peruano:
1. Tiendas Efe (efe)
2. Falabella (falabella)
3. Ripley (ripley)
4. La Curacao (curacao)
5. Hiraoka (hiraoka)
6. Tottus (tottus)
7. Metro (metro)
8. Wong (wong)
"""
from typing import Dict, List, Optional
from app.core.logging import get_logger
from app.collectors.catalog_urls import get_verified_store_urls_for_product
from app.collectors.query_builder import build_search_queries
from app.collectors.url_utils import build_store_search_url, canonicalize_store_url
from app.collectors.graph.state import (
    BaseGraphNode,
    CandidateUrlEntry,
    GraphState,
)

logger = get_logger("collectors.graph.discovery_search_node")


class DiscoverySearchNode(BaseGraphNode):
    """
    Nodo 1: Genera consultas en cascada libres de colores y descubre las rutas
    en las 8 tiendas oficiales del Perú (Canal 1 Semilla/Caché, Canal 2 Buscador/API Oficial).
    """

    node_name: str = "DiscoverySearchNode"
    node_type: str = "node"

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        queries = build_search_queries(target.title, target.tech_specs)
        state.search_queries = queries

        seed_and_cached: Dict[str, str] = get_verified_store_urls_for_product(
            product_id=target.id,
            extra_seed_urls=target.seed_store_urls,
        )

        candidates_map: Dict[str, List[CandidateUrlEntry]] = {}

        for store_id in state.stores_to_check:
            store_entries: List[CandidateUrlEntry] = []
            seen_urls = set()

            # CANAL 1: URL directa verificada de semilla o base de datos
            direct_u = seed_and_cached.get(store_id) or target.seed_store_urls.get(store_id)
            if direct_u:
                _, clean_u = canonicalize_store_url(direct_u)
                eff_u = clean_u or direct_u
                if eff_u not in seen_urls:
                    seen_urls.add(eff_u)
                    store_entries.append(
                        CandidateUrlEntry(
                            store_id=store_id,
                            url=eff_u,
                            channel="channel_1_seed_cache",
                            query_used=None,
                            is_search_endpoint=False,
                            priority=1,
                        )
                    )

            # CANAL 2: Buscador / API Oficial de la Tienda
            if state.enable_cascade_search:
                for idx, q in enumerate(queries):
                    s_url = build_store_search_url(store_id, q)
                    if s_url and s_url not in seen_urls:
                        seen_urls.add(s_url)
                        store_entries.append(
                            CandidateUrlEntry(
                                store_id=store_id,
                                url=s_url,
                                channel="channel_2_store_search",
                                query_used=q,
                                is_search_endpoint=True,
                                priority=2 + idx,
                            )
                        )

            candidates_map[store_id] = store_entries

        state.candidate_urls_by_store = candidates_map
        total_cand = sum(len(e) for e in candidates_map.values())
        state.execution_trace.append(
            f"DiscoverySearchNode: discovered {total_cand} candidate routes across {len(state.stores_to_check)} stores"
        )
        return state
