"""
Orquestador del Grafo Dirigido Multitienda (smart_multi_graph.py).
Implementa FinPriceMultiStoreGraph (SearchGraph + SmartScraperMultiGraph) inspirado en ScrapeGraphAI:
Nodo 1: SearchInternetNode  (Descubrimiento en 3 canales para las 8 tiendas)
  │
  ▼
Nodo 2: FetchNode           (Descarga concurrente HTTP/2 + API JSON + expansión de grillas)
  │
  ▼
Nodo 3: ParseNode           (Destilación de HTML/JSON-LD/__NEXT_DATA__/Tablas a ParsedPageNodeData)
  │
  ▼
Nodo 4: SchemaExtractorNode (Resolución de variantes Multi-SKU y extracción a ExtractedOfferSchema)
  │
  ▼
Nodo 5: MergeAnswersNode    (Validación sobre Corpus Completo y filtro estadístico anti-outliers)
"""
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.core.logging import get_logger
from app.collectors.fingerprint_matcher import ProductFingerprint, matches_fingerprint
from app.collectors.query_builder import build_search_queries
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.graph.extractor_node import SchemaExtractorNode
from app.collectors.graph.fetch_node import FetchNode, is_search_endpoint_url
from app.collectors.graph.merge_validator_node import MergeAnswersNode
from app.collectors.graph.parse_node import ParseNode
from app.collectors.graph.search_node import SearchInternetNode
from app.collectors.graph.state import (
    ALL_8_PERU_STORES,
    BaseGraphNode,
    CandidateUrlEntry,
    GraphState,
    ProductTargetSpec,
)

logger = get_logger("collectors.graph.smart_multi_graph")


class FinPriceMultiStoreGraph:
    """
    Pipeline de Grafo Dirigido inspirado en ScrapeGraphAI (SearchGraph + SmartScraperMultiGraph)
    que sincroniza cualquier producto contra las 8 tiendas oficiales del Perú:
    ('falabella', 'ripley', 'tottus', 'efe', 'curacao', 'hiraoka', 'metro', 'wong').
    """

    def __init__(
        self,
        fetch_fn: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[..., Any]] = None,
        llm_extractor_fn: Optional[Callable[..., Any]] = None,
    ):
        self.default_fetch_fn = fetch_fn
        self.default_scrape_fn = scrape_fn
        self.default_llm_extractor_fn = llm_extractor_fn

    def build_nodes(
        self,
        fetch_fn: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[..., Any]] = None,
    ) -> List[BaseGraphNode]:
        """Construye la secuencia de 5 nodos del DAG de extracción multitienda."""
        return [
            SearchInternetNode(),
            FetchNode(
                fetch_fn=fetch_fn or self.default_fetch_fn,
                scrape_fn=scrape_fn or self.default_scrape_fn,
            ),
            ParseNode(),
            SchemaExtractorNode(llm_extractor_fn=self.default_llm_extractor_fn),
            MergeAnswersNode(),
        ]

    async def execute_state(
        self,
        target_product: Any,
        stores_to_check: Optional[Sequence[str]] = None,
        enable_cascade_search: bool = True,
        enable_external_dork: bool = False,
        enable_llm_fallback: bool = False,
        fetch_fn: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[..., Any]] = None,
    ) -> GraphState:
        """
        Ejecuta el grafo dirigido completo (5 nodos) y devuelve el GraphState final
        con la traza de ejecución, documentos parseados y ofertas verificadas.
        """
        target_spec = ProductTargetSpec.from_target(target_product)
        stores = list(stores_to_check) if stores_to_check is not None else list(ALL_8_PERU_STORES)

        state = GraphState(
            target=target_spec,
            stores_to_check=stores,
            enable_cascade_search=enable_cascade_search,
            enable_external_dork=enable_external_dork,
            enable_llm_fallback=enable_llm_fallback,
        )

        nodes = self.build_nodes(fetch_fn=fetch_fn, scrape_fn=scrape_fn)
        for node in nodes:
            state = await node.execute(state)

        return state

    async def run(
        self,
        target_product: Any,
        stores_to_check: Optional[Sequence[str]] = None,
        enable_cascade_search: bool = True,
        enable_external_dork: bool = False,
        enable_llm_fallback: bool = False,
        fetch_fn: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[..., Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta el grafo completo para un producto objetivo y retorna la lista
        de ofertas verificadas y libres de outliers ordenadas por mejor precio.
        """
        final_state = await self.execute_state(
            target_product=target_product,
            stores_to_check=stores_to_check,
            enable_cascade_search=enable_cascade_search,
            enable_external_dork=enable_external_dork,
            enable_llm_fallback=enable_llm_fallback,
            fetch_fn=fetch_fn,
            scrape_fn=scrape_fn,
        )
        return [offer.to_offer_dict() for offer in final_state.verified_offers]

    async def scrape_single_url(
        self,
        store_id: str,
        url: str,
        canonical_title: Optional[str] = None,
        tech_specs: Optional[Dict[str, Any]] = None,
        fingerprint: Optional[ProductFingerprint] = None,
        target_product: Optional[Dict[str, Any]] = None,
        fetch_fn: Optional[Callable[..., Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Ejecuta los nodos FetchNode -> ParseNode -> SchemaExtractorNode -> MergeAnswersNode
        sobre una URL individual (ficha directa o endpoint de búsqueda).
        """
        effective_target = target_product or {
            "title": canonical_title or "",
            "tech_specs": tech_specs or {},
        }
        target_spec = ProductTargetSpec.from_target(effective_target)
        is_search = is_search_endpoint_url(url)

        target_url = url
        if not is_search:
            _, clean_u = canonicalize_store_url(url)
            target_url = clean_u or url

        queries = build_search_queries(target_spec.title, target_spec.tech_specs) if target_spec.title else []
        state = GraphState(
            target=target_spec,
            stores_to_check=[store_id],
            enable_cascade_search=False,
            search_queries=queries,
            candidate_urls_by_store={
                store_id: [
                    CandidateUrlEntry(
                        store_id=store_id,
                        url=target_url,
                        channel="channel_2_store_search" if is_search else "channel_1_seed_cache",
                        is_search_endpoint=is_search,
                        priority=1,
                    )
                ]
            },
        )

        # Ejecutar FetchNode -> ParseNode -> SchemaExtractorNode
        fetch_node = FetchNode(fetch_fn=fetch_fn or self.default_fetch_fn)
        parse_node = ParseNode()
        extractor_node = SchemaExtractorNode(llm_extractor_fn=self.default_llm_extractor_fn)
        merge_node = MergeAnswersNode()

        state = await fetch_node.execute(state)
        if not state.fetched_documents:
            return None

        state = await parse_node.execute(state)
        state = await extractor_node.execute(state)

        if not state.extracted_offers:
            try:
                from app.collectors.orchestrator import CIRCUIT_BREAKERS
                cb = CIRCUIT_BREAKERS.get(store_id)
                if cb:
                    cb.record_failure("No se pudo extraer precio válido")
            except Exception:
                pass
            return None

        if canonical_title or target_spec.title:
            state = await merge_node.execute(state)
            if not state.verified_offers:
                return None
            best_offer = state.verified_offers[0]
        else:
            best_offer = state.extracted_offers[0]

        if fingerprint is not None:
            if not matches_fingerprint(
                fingerprint=fingerprint,
                candidate_title=best_offer.title,
                candidate_specs=best_offer.tech_specs or tech_specs,
                candidate_url=best_offer.offer_url,
            ):
                return None

        return best_offer.to_offer_dict()


# Alias compatible con la nomenclatura de ScrapeGraphAI
SmartScraperMultiGraph = FinPriceMultiStoreGraph

# Instancia global del orquestador de grafo
finprice_multi_store_graph = FinPriceMultiStoreGraph()
