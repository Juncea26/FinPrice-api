"""
Nodo 4 del Grafo: SchemaExtractorNode (extractor_node.py).
Inspirado en GenerateAnswerNode / SchemaExtractorNode de ScrapeGraphAI.
Ejecuta:
1. Resolución de Variantes Multi-SKU (ej. Falabella SKU 21014911 128GB vs SKU 21014999 256GB,
   Tottus SKU 150930381, VTEX SKUs en Metro/Wong).
2. Extracción determinista tipada hacia ExtractedOfferSchema combinando los parsers por tienda
   con el documento estructurado destilado por ParseNode (tech_specs, description, features).
3. Fallback opcional con ScrapeGraphAI (SmartScraperGraph) / LLM estructurado sobre
   `parsed_node.distilled_markdown` cuando `enable_llm_fallback=True`.
"""
import json
from typing import Any, Callable, Dict, List, Optional

from app.core.logging import get_logger
from app.collectors.catalog_urls import STORES_INFO
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.collectors.parsers.tottus import parse_tottus
from app.collectors.parsers.vtex_cencosud import parse_vtex_cencosud
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.graph.state import (
    BaseGraphNode,
    ExtractedOfferSchema,
    GraphState,
    ParsedPageNodeData,
    ProductTargetSpec,
)

logger = get_logger("collectors.graph.extractor_node")


def get_store_parser(store_id: str) -> Optional[Callable[..., Optional[Dict[str, Any]]]]:
    if store_id == "falabella":
        return parse_falabella
    if store_id == "tottus":
        return parse_tottus
    if store_id in {"efe", "curacao"}:
        return parse_conectaretail
    if store_id == "ripley":
        return parse_ripley
    if store_id == "hiraoka":
        return parse_hiraoka
    if store_id in {"metro", "wong"}:
        return parse_vtex_cencosud
    return None


class SchemaExtractorNode(BaseGraphNode):
    """
    Nodo 4 (SchemaExtractorNode): Extrae ofertas tipadas (ExtractedOfferSchema)
    desde cada ParsedPageNodeData resolviendo variantes Multi-SKU.
    """

    node_name: str = "SchemaExtractorNode"
    node_type: str = "node"

    def __init__(
        self,
        llm_extractor_fn: Optional[Callable[[ParsedPageNodeData, ProductTargetSpec], Optional[Dict[str, Any]]]] = None,
    ):
        self.llm_extractor_fn = llm_extractor_fn

    def _extract_with_scrapegraphai_or_llm(
        self,
        node_data: ParsedPageNodeData,
        target: ProductTargetSpec,
    ) -> Optional[Dict[str, Any]]:
        """
        Integración opcional con ScrapeGraphAI (SmartScraperGraph) o función LLM inyectada
        sobre el Markdown destilado de la página cuando la extracción determinista no encuentra precio.
        """
        if self.llm_extractor_fn is not None:
            try:
                return self.llm_extractor_fn(node_data, target)
            except Exception as e:
                logger.debug(f"[SchemaExtractorNode] Error en llm_extractor_fn: {e}")
                return None

        try:
            from scrapegraphai.graphs import SmartScraperGraph  # type: ignore
            import os

            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                return None

            graph_config = {
                "llm": {
                    "api_key": api_key,
                    "model": "openai/gpt-4o-mini",
                },
                "verbose": False,
                "headless": True,
            }
            prompt = (
                f"Extract the exact product offer for '{target.title}' "
                f"(storage={target.storage_gb}GB, screen={target.screen_inches} inches) "
                "including title, price (float in PEN), original_price, image_url, and tech_specs."
            )
            smart_Graph = SmartScraperGraph(
                prompt=prompt,
                source=node_data.distilled_markdown,
                schema=ExtractedOfferSchema,
                config=graph_config,
            )
            res = smart_Graph.run()
            if isinstance(res, dict) and res.get("price"):
                res["extraction_source"] = "scrapegraphai_llm"
                return res
        except Exception:
            pass
        return None

    def extract_from_parsed_node(
        self,
        node_data: ParsedPageNodeData,
        target: ProductTargetSpec,
        enable_llm_fallback: bool = False,
    ) -> Optional[ExtractedOfferSchema]:
        store_id = node_data.store_id
        store_meta = STORES_INFO.get(store_id, {})
        default_store_name = store_meta.get("name", store_id.title())

        # 1. Si proviene de una oferta pre-extraída (ej. scrape_fn inyectado)
        if node_data.raw_html.lstrip().startswith("{"):
            try:
                raw_j = json.loads(node_data.raw_html)
                if isinstance(raw_j, dict) and raw_j.get("_pre_scraped_offer"):
                    off = raw_j["offer"]
                    _, clean_u = canonicalize_store_url(off.get("offer_url") or node_data.canonical_url)
                    return ExtractedOfferSchema(
                        store_id=store_id,
                        store_name=str(off.get("store_name") or default_store_name),
                        title=str(off.get("title") or target.title),
                        price=round(float(off["price"]), 2),
                        original_price=round(float(off.get("original_price") or off["price"]), 2),
                        offer_url=clean_u or node_data.canonical_url,
                        image_url=off.get("image_url"),
                        brand=off.get("brand") or node_data.brand,
                        variant_sku_id=off.get("variant_sku_id"),
                        in_stock=bool(off.get("in_stock", True)),
                        tech_specs=off.get("tech_specs") or node_data.tech_specs or {},
                        features=list(off.get("features") or node_data.features or []),
                        description=str(off.get("description") or node_data.description or ""),
                        extraction_source="deterministic_graph",
                    )
            except Exception:
                pass

        # 2. Extracción determinista con resolución de variantes Multi-SKU
        parser = get_store_parser(store_id)
        data: Optional[Dict[str, Any]] = None
        if parser is not None:
            if node_data.is_search_page or store_id in {"falabella", "tottus"}:
                data = parser(
                    node_data.raw_html,
                    node_data.url,
                    canonical_title=target.title,
                )
            else:
                data = parser(node_data.raw_html, node_data.url)

        # 3. Fallback opcional con ScrapeGraphAI / LLM si está habilitado
        if (not data or not data.get("price") or float(data["price"]) <= 0) and enable_llm_fallback:
            data = self._extract_with_scrapegraphai_or_llm(node_data, target)

        if not data or not data.get("price") or float(data["price"]) <= 0:
            return None

        raw_offer_url = str(data.get("offer_url") or node_data.canonical_url or node_data.url).strip()
        _, clean_offer_url = canonicalize_store_url(raw_offer_url)
        final_offer_url = clean_offer_url or raw_offer_url

        # Fusionar las especificaciones técnicas y descripción destiladas por ParseNode
        merged_specs: Dict[str, Any] = dict(node_data.tech_specs or {})
        if isinstance(data.get("tech_specs"), dict):
            merged_specs.update(data["tech_specs"])

        merged_desc = str(data.get("description") or node_data.description or "").strip()
        merged_features = list(data.get("features") or node_data.features or [])
        merged_brand = str(data.get("brand") or node_data.brand or "").strip() or None

        price_val = round(float(data["price"]), 2)
        orig_raw = data.get("original_price")
        orig_val = round(float(orig_raw), 2) if (orig_raw and float(orig_raw) > price_val) else price_val

        return ExtractedOfferSchema(
            store_id=store_id,
            store_name=str(data.get("store_name") or default_store_name),
            title=str(data.get("title") or node_data.h1_title or "").strip(),
            price=price_val,
            original_price=orig_val,
            offer_url=final_offer_url,
            image_url=data.get("image_url") or node_data.image_url,
            brand=merged_brand,
            variant_sku_id=data.get("variant_sku_id"),
            in_stock=bool(data.get("in_stock", True)),
            tech_specs=merged_specs,
            features=merged_features,
            description=merged_desc,
            extraction_source=str(data.get("extraction_source") or "deterministic_graph"),
        )

    async def execute(self, state: GraphState) -> GraphState:
        extracted: List[ExtractedOfferSchema] = []
        try:
            from app.collectors.orchestrator import CIRCUIT_BREAKERS
        except Exception:
            CIRCUIT_BREAKERS = {}

        for parsed_node in state.parsed_nodes:
            try:
                offer = self.extract_from_parsed_node(
                    node_data=parsed_node,
                    target=state.target,
                    enable_llm_fallback=state.enable_llm_fallback,
                )
                if offer is not None and offer.price > 0:
                    cb = CIRCUIT_BREAKERS.get(offer.store_id)
                    if cb:
                        cb.record_success()
                    extracted.append(offer)
            except Exception as e:
                logger.debug(f"[SchemaExtractorNode] Error en {parsed_node.url}: {e}")
                state.errors.append(f"SchemaExtractorNode error ({parsed_node.url}): {e}")

        state.extracted_offers = extracted
        state.execution_trace.append(
            f"SchemaExtractorNode: extracted_offers={len(extracted)}"
        )
        return state
