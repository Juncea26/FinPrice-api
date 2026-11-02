"""
Nodo 2 del Grafo: StoreParserNode (store_parser_node.py).
Parsea los documentos HTML/JSON descargados de las 8 tiendas oficiales del retail peruano
y extrae estrictamente el PRECIO ONLINE público (sin requerir tarjeta exclusiva).
"""
from typing import Any, Callable, Dict, List, Optional
from app.core.logging import get_logger
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.collectors.parsers.tottus import parse_tottus
from app.collectors.parsers.vtex_cencosud import parse_vtex_cencosud
from app.collectors.catalog_urls import STORES_INFO
from app.collectors.graph.state import (
    BaseGraphNode,
    ExtractedOfferSchema,
    GraphState,
    RawFetchedDocument,
)

logger = get_logger("collectors.graph.store_parser_node")


def _get_store_parser(store_id: str) -> Optional[Callable[..., Optional[Dict[str, Any]]]]:
    if store_id == "hiraoka":
        return parse_hiraoka
    elif store_id in {"efe", "curacao"}:
        return parse_conectaretail
    elif store_id == "falabella":
        return parse_falabella
    elif store_id == "tottus":
        return parse_tottus
    elif store_id in {"metro", "wong"}:
        return parse_vtex_cencosud
    elif store_id == "ripley":
        return parse_ripley
    return None


class StoreParserNode(BaseGraphNode):
    """
    Nodo 2: Parsea documentos crudos de las 8 tiendas y extrae las ofertas tipadas
    con su menor precio online público activo.
    """

    node_name: str = "StoreParserNode"
    node_type: str = "node"

    async def execute(self, state: GraphState) -> GraphState:
        target = state.target
        target_title = target.title
        extracted: List[ExtractedOfferSchema] = []

        for doc in state.fetched_documents:
            store_id = doc.store_id
            parser = _get_store_parser(store_id)
            if not parser or not doc.content:
                continue

            try:
                data = parser(
                    doc.content,
                    doc.canonical_url or doc.url,
                    canonical_title=target_title,
                )
                if not data or not data.get("price") or float(data["price"]) <= 0:
                    continue

                store_info = STORES_INFO.get(store_id, {})
                store_name = store_info.get("name") or data.get("store_name") or store_id.title()

                offer = ExtractedOfferSchema(
                    store_id=store_id,
                    store_name=store_name,
                    title=data.get("title") or target_title,
                    price=float(data["price"]),
                    original_price=float(data.get("original_price") or data["price"]),
                    offer_url=data.get("offer_url") or doc.canonical_url or doc.url,
                    image_url=data.get("image_url"),
                    brand=data.get("brand") or target.brand,
                    variant_sku_id=data.get("variant_sku_id"),
                    in_stock=bool(data.get("in_stock", True)),
                    tech_specs=data.get("tech_specs") or target.tech_specs,
                    features=data.get("features") or [],
                    description=data.get("description") or "",
                    extraction_source="store_parser_node",
                )
                extracted.append(offer)
            except Exception as e:
                logger.warning(f"Error parseando documento de {store_id}: {e}")

        state.extracted_offers = extracted
        state.execution_trace.append(
            f"StoreParserNode: extracted {len(extracted)} candidate offers from {len(state.fetched_documents)} documents"
        )
        return state
