"""
Nodo 3 del Grafo: ParseNode (parse_node.py).
Inspirado en ParseNode de ScrapeGraphAI.
Destila el HTML crudo o JSON API de cada tienda aislando el DOM principal (sin carruseles
de relacionados/upsell) y extrayendo en un documento estructurado (ParsedPageNodeData):
- Títulos H1 y Meta
- Bloques JSON-LD (@type == "Product")
- Estado Next.js (#__NEXT_DATA__: productData, variants[], attributes.specifications, results[])
- Estado Preloaded de Ripley (window.__PRELOADED_STATE__)
- Payloads JSON / Apollo GraphQL de VTEX IO (Metro y Wong)
- Tablas HTML de especificaciones (#product-attribute-specs-table, .additional-attributes)
- Resumen Markdown destilado (distilled_markdown) para extracción determinista o LLM/ScrapeGraphAI.
"""
import json
import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.collectors.spec_extractor import extract_product_specs
from app.collectors.universal_matcher import extract_search_candidate_links
from app.collectors.graph.state import (
    BaseGraphNode,
    GraphState,
    ParsedPageNodeData,
    RawFetchedDocument,
)

logger = get_logger("collectors.graph.parse_node")

NOISE_AND_CAROUSEL_SELECTORS = (
    ".block.upsell, .block.related, .block.crosssell, "
    ".products-upsell, .products-related, .products-crosssell, "
    "[data-content-type='products'], .widget.block-products-list, "
    ".carousel, .related-products, .product-carousel, "
    "aside, footer, nav"
)


class ParseNode(BaseGraphNode):
    """
    Nodo 3 (ParseNode): Transforma cada RawFetchedDocument en un ParsedPageNodeData
    destilado y libre de ruido de carruseles.
    """

    node_name: str = "ParseNode"
    node_type: str = "node"

    def parse_single_document(
        self,
        doc: RawFetchedDocument,
        broad_model_query: str = "",
    ) -> ParsedPageNodeData:
        # 1. Caso especial: documento pre-scrapeado en JSON o respuesta API JSON de VTEX
        if doc.content_type == "json":
            try:
                parsed_json = json.loads(doc.content)
                if isinstance(parsed_json, dict) and parsed_json.get("_pre_scraped_offer"):
                    offer = parsed_json.get("offer") or {}
                    title = str(offer.get("title") or "")
                    specs = offer.get("tech_specs") if isinstance(offer.get("tech_specs"), dict) else {}
                    desc = str(offer.get("description") or "")
                    md = (
                        f"# {title}\n"
                        f"- Store: {doc.store_id}\n"
                        f"- URL: {doc.canonical_url}\n"
                        f"- Price: {offer.get('price')}\n"
                        f"- Specs: {json.dumps(specs, ensure_ascii=False)}\n"
                        f"- Description: {desc}"
                    )
                    return ParsedPageNodeData(
                        store_id=doc.store_id,
                        url=doc.url,
                        canonical_url=doc.canonical_url,
                        channel=doc.channel,
                        is_search_page=False,
                        h1_title=title,
                        meta_title=title,
                        description=desc,
                        brand=str(offer.get("brand") or ""),
                        image_url=offer.get("image_url"),
                        tech_specs={str(k): str(v) for k, v in specs.items()},
                        features=list(offer.get("features") or []),
                        distilled_markdown=md,
                        raw_html=doc.content,
                    )
                if isinstance(parsed_json, list):
                    first_title = ""
                    if parsed_json and isinstance(parsed_json[0], dict):
                        first_title = str(
                            parsed_json[0].get("productName")
                            or parsed_json[0].get("productTitle")
                            or ""
                        )
                    return ParsedPageNodeData(
                        store_id=doc.store_id,
                        url=doc.url,
                        canonical_url=doc.canonical_url,
                        channel=doc.channel,
                        is_search_page=doc.is_search_page,
                        h1_title=first_title,
                        vtex_api_items=[x for x in parsed_json if isinstance(x, dict)],
                        distilled_markdown=f"# VTEX API Items ({ len(parsed_json) })\n{doc.content[:2000]}",
                        raw_html=doc.content,
                    )
            except Exception:
                pass

        soup = BeautifulSoup(doc.content, "lxml")

        # Si es página de búsqueda, extraer enlaces de candidatos antes de limpiar DOM
        candidate_links: List[str] = []
        if doc.is_search_page:
            candidate_links = extract_search_candidate_links(
                html=doc.content,
                search_url=doc.url,
                broad_model_query=broad_model_query,
                limit=5,
            )

        # 2. Extraer JSON-LD (@type == "Product")
        json_ld_products: List[Dict[str, Any]] = []
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                j = json.loads(s.string)
                items = j if isinstance(j, list) else [j]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        json_ld_products.append(item)
            except Exception:
                pass

        # 3. Extraer #__NEXT_DATA__ (Falabella, Tottus, Ripley)
        next_data_product: Dict[str, Any] = {}
        next_data_variants: List[Dict[str, Any]] = []
        next_data_search_results: List[Dict[str, Any]] = []
        nd_script = soup.find("script", id="__NEXT_DATA__")
        if nd_script and nd_script.string:
            try:
                nd = json.loads(nd_script.string)
                props = nd.get("props", {}).get("pageProps", {})
                results = props.get("results")
                if isinstance(results, list):
                    next_data_search_results = [r for r in results if isinstance(r, dict)]
                prod_node = (
                    props.get("productData")
                    or props.get("detailProps", {}).get("data", {}).get("product")
                    or props.get("product")
                    or {}
                )
                if isinstance(prod_node, dict):
                    next_data_product = prod_node
                    variants = prod_node.get("variants")
                    if isinstance(variants, list):
                        next_data_variants = [v for v in variants if isinstance(v, dict)]
            except Exception:
                pass

        # 4. Extraer window.__PRELOADED_STATE__ (Ripley)
        preloaded_state_product: Dict[str, Any] = {}
        preloaded_match = re.search(
            r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*(?:;|</script>)",
            doc.content,
            flags=re.DOTALL,
        )
        if preloaded_match:
            try:
                st = json.loads(preloaded_match.group(1))
                p_obj = st.get("product", {}).get("product", {}) or st.get("product", {})
                if isinstance(p_obj, dict):
                    preloaded_state_product = p_obj
            except Exception:
                pass

        # 5. Aislar DOM principal eliminando carruseles de recomendados / relacionados
        for unwanted in soup.select(NOISE_AND_CAROUSEL_SELECTORS):
            unwanted.decompose()

        h1_el = soup.select_one(
            'h1.page-title span[data-ui-id="page-title-wrapper"], '
            "h1.page-title span.base, "
            ".product-info-main h1.page-title, "
            "h1.jsx-product-name, "
            "section.product-header h1, "
            "h1"
        )
        h1_title = h1_el.get_text(" ", strip=True) if h1_el else ""
        if not h1_title and next_data_product:
            h1_title = str(
                next_data_product.get("name") or next_data_product.get("displayName") or ""
            ).strip()
        if not h1_title and json_ld_products:
            h1_title = str(json_ld_products[0].get("name") or "").strip()

        title_tag = soup.find("title")
        meta_title = title_tag.get_text(" ", strip=True) if title_tag else h1_title

        # Descripción consolidada (DOM + NextData + JSON-LD + Meta)
        desc_parts: List[str] = []
        if next_data_product:
            for dk in ("description", "longDescription", "shortDescription"):
                val = next_data_product.get(dk)
                if val and isinstance(val, str):
                    desc_parts.append(val.strip())
        for v_item in next_data_variants:
            v_name = v_item.get("name")
            if v_name and isinstance(v_name, str):
                desc_parts.append(v_name.strip())
        desc_el = soup.select_one(
            ".product.attribute.description .value, "
            ".product.attribute.overview .value, "
            ".product.attribute.description"
        )
        if desc_el:
            desc_parts.append(desc_el.get_text(" ", strip=True))
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc_parts.append(str(meta_desc["content"]).strip())
        description = " ".join(dict.fromkeys(p for p in desc_parts if p))

        # Extraer especificaciones técnicas normalizadas, marca y features
        extracted_meta = extract_product_specs(
            doc.content,
            title=h1_title or meta_title,
            store_id=doc.store_id,
        )
        tech_specs = extracted_meta.get("tech_specs") or {}
        brand = extracted_meta.get("brand") or ""
        features = extracted_meta.get("features") or []

        og_img = soup.find("meta", property="og:image")
        image_url = str(og_img.get("content")).strip() if (og_img and og_img.get("content")) else None

        # Construir documento Markdown destilado (estilo ScrapeGraphAI ParseNode)
        variants_summary = [
            {
                "id": v.get("id"),
                "name": v.get("name"),
                "prices": v.get("prices"),
            }
            for v in next_data_variants
        ]
        distilled_md = (
            f"# {h1_title or meta_title}\n"
            f"- Store: {doc.store_id}\n"
            f"- URL: {doc.canonical_url}\n"
            f"- Brand: {brand}\n"
            f"## Technical Specifications\n"
            f"{json.dumps(tech_specs, ensure_ascii=False)}\n"
            f"## Variants\n"
            f"{json.dumps(variants_summary, ensure_ascii=False)}\n"
            f"## Description\n"
            f"{description[:1000]}"
        )

        return ParsedPageNodeData(
            store_id=doc.store_id,
            url=doc.url,
            canonical_url=doc.canonical_url,
            channel=doc.channel,
            is_search_page=doc.is_search_page,
            h1_title=h1_title,
            meta_title=meta_title,
            description=description,
            brand=brand,
            image_url=image_url,
            json_ld_products=json_ld_products,
            next_data_product=next_data_product,
            next_data_variants=next_data_variants,
            next_data_search_results=next_data_search_results,
            preloaded_state_product=preloaded_state_product,
            tech_specs=tech_specs,
            features=features,
            search_candidate_links=candidate_links,
            distilled_markdown=distilled_md,
            raw_html=doc.content,
        )

    async def execute(self, state: GraphState) -> GraphState:
        broad_q = state.search_queries[-1] if state.search_queries else state.target.title
        parsed_list: List[ParsedPageNodeData] = []
        for doc in state.fetched_documents:
            try:
                parsed_node = self.parse_single_document(doc, broad_model_query=broad_q)
                parsed_list.append(parsed_node)
            except Exception as e:
                logger.debug(f"[ParseNode] Error parseando {doc.url}: {e}")
                state.errors.append(f"ParseNode error ({doc.url}): {e}")

        state.parsed_nodes = parsed_list
        state.execution_trace.append(
            f"ParseNode: parsed_nodes={len(parsed_list)}"
        )
        return state
