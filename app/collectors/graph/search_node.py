"""
Nodo 1 del Grafo: SearchInternetNode (search_node.py).
Inspirado en SearchInternetNode de ScrapeGraphAI.
Descubre URLs candidatas en 3 canales para cada una de las 8 tiendas oficiales del Perú
(falabella, ripley, tottus, efe, curacao, hiraoka, metro, wong):
- Canal 1 (channel_1_seed_cache): Semilla de URLs reales verificadas + caché persistente en DB.
- Canal 2 (channel_2_store_search): Consultas en cascada (specific_query -> broad_model_query)
  contra los buscadores y APIs públicas de cada tienda.
- Canal 3 (channel_3_external_dork): Búsqueda externa con dork site:{host} cuando se habilita.
"""
from typing import Dict, List

from app.core.logging import get_logger
from app.collectors.catalog_urls import get_verified_store_urls_for_product
from app.collectors.query_builder import build_search_queries
from app.collectors.url_utils import (
    build_external_dork_search_url,
    build_store_search_url,
    canonicalize_store_url,
)
from app.collectors.graph.state import (
    BaseGraphNode,
    CandidateUrlEntry,
    GraphState,
)

logger = get_logger("collectors.graph.search_node")


class SearchInternetNode(BaseGraphNode):
    """
    Nodo 1 (SearchInternetNode): Genera las consultas en cascada libres de colores
    y descubre las rutas candidatas en los 3 canales para las 8 tiendas del retail peruano.
    """

    node_name: str = "SearchInternetNode"
    node_type: str = "node"

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        queries = build_search_queries(target.title, target.tech_specs)
        state.search_queries = queries

        # Recuperar URLs verificadas de semilla + caché persistente
        seed_and_cached: Dict[str, str] = get_verified_store_urls_for_product(
            product_id=target.id,
            extra_seed_urls=target.seed_store_urls,
        )

        candidates_map: Dict[str, List[CandidateUrlEntry]] = {}

        for store_id in state.stores_to_check:
            store_entries: List[CandidateUrlEntry] = []
            seen_urls = set()

            # ------------------------------------------------------------------
            # CANAL 1: Semilla verificada + Caché persistente en Base de Datos
            # ------------------------------------------------------------------
            direct_u = seed_and_cached.get(store_id) or target.seed_store_urls.get(store_id)
            if direct_u:
                _, clean_u = canonicalize_store_url(direct_u)
                effective_u = clean_u or direct_u
                if effective_u not in seen_urls:
                    seen_urls.add(effective_u)
                    store_entries.append(
                        CandidateUrlEntry(
                            store_id=store_id,
                            url=effective_u,
                            channel="channel_1_seed_cache",
                            query_used=None,
                            is_search_endpoint=False,
                            priority=1,
                        )
                    )

            # ------------------------------------------------------------------
            # CANAL 2: Buscador / API Oficial de la Tienda en Cascada
            # (1° specific_query -> 2° broad_model_query)
            # ------------------------------------------------------------------
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

            # ------------------------------------------------------------------
            # CANAL 3: Búsqueda Externa (Dork site:{canonical_host} {query})
            # ------------------------------------------------------------------
            if state.enable_external_dork and queries:
                dork_url = build_external_dork_search_url(store_id, queries[0])
                if dork_url and dork_url not in seen_urls:
                    seen_urls.add(dork_url)
                    store_entries.append(
                        CandidateUrlEntry(
                            store_id=store_id,
                            url=dork_url,
                            channel="channel_3_external_dork",
                            query_used=queries[0],
                            is_search_endpoint=True,
                            priority=10,
                        )
                    )

            candidates_map[store_id] = store_entries

        state.candidate_urls_by_store = candidates_map
        state.execution_trace.append(
            f"SearchInternetNode: queries={queries}, stores={len(state.stores_to_check)}"
        )
        return state
