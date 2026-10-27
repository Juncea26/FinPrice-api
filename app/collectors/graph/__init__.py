"""
Motor de Extracción Basado en Grafos al estilo ScrapeGraphAI (app/collectors/graph/).
Expone:
- Estado y Esquemas Pydantic v2: GraphState, ProductTargetSpec, ParsedPageNodeData, ExtractedOfferSchema
- Nodo 1 (SearchInternetNode): Descubrimiento en 3 canales para las 8 tiendas del Perú
- Nodo 2 (FetchNode): Descarga concurrente HTTP/2 + API JSON + GraphIterator
- Nodo 3 (ParseNode): Destilación de HTML/JSON-LD/__NEXT_DATA__/Tablas a documento estructurado
- Nodo 4 (SchemaExtractorNode): Resolución de variantes Multi-SKU y extracción tipada (Determinista + LLM/ScrapeGraphAI)
- Nodo 5 (MergeAnswersNode): Validación sobre Corpus Completo y filtro estadístico anti-outliers
- Orquestador: FinPriceMultiStoreGraph / SmartScraperMultiGraph
"""
from app.collectors.graph.state import (
    ALL_8_PERU_STORES,
    BaseGraphNode,
    CandidateUrlEntry,
    ExtractedOfferSchema,
    GraphState,
    ParsedPageNodeData,
    ProductTargetSpec,
    RawFetchedDocument,
)
from app.collectors.graph.search_node import SearchInternetNode
from app.collectors.graph.fetch_node import FetchNode
from app.collectors.graph.parse_node import ParseNode
from app.collectors.graph.extractor_node import SchemaExtractorNode
from app.collectors.graph.merge_validator_node import MergeAnswersNode
from app.collectors.graph.smart_multi_graph import (
    FinPriceMultiStoreGraph,
    SmartScraperMultiGraph,
    finprice_multi_store_graph,
)

__all__ = [
    "ALL_8_PERU_STORES",
    "BaseGraphNode",
    "CandidateUrlEntry",
    "ExtractedOfferSchema",
    "GraphState",
    "ParsedPageNodeData",
    "ProductTargetSpec",
    "RawFetchedDocument",
    "SearchInternetNode",
    "FetchNode",
    "ParseNode",
    "SchemaExtractorNode",
    "MergeAnswersNode",
    "FinPriceMultiStoreGraph",
    "SmartScraperMultiGraph",
    "finprice_multi_store_graph",
]
