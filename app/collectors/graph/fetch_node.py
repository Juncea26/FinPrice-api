"""
Nodo 2 del Grafo: FetchNode + GraphIterator (fetch_node.py).
Inspirado en FetchNode y GraphIteratorNode de ScrapeGraphAI.
Ejecuta la descarga concurrente HTTP/2 y de APIs JSON (VTEX / Next.js / Magento 2)
para las 8 tiendas del retail peruano, respetando Circuit Breakers por tienda,
ejecutando la cascada (Canal 1 -> Canal 2 specific -> Canal 2 broad -> Canal 3 dork)
y expandiendo los primeros 5 candidatos de grillas de búsqueda cuando el atributo
técnico está dentro de la ficha del producto.
"""
import asyncio
import json
from typing import Any, Callable, List, Optional

from app.core.logging import get_logger
from app.collectors.http_client import fetch_page as default_fetch_page
from app.collectors.universal_matcher import (
    extract_search_candidate_links,
    match_product_universal,
)
from app.collectors.url_utils import (
    canonicalize_store_url,
    extract_store_urls_from_dork_html,
)
from app.collectors.graph.state import (
    BaseGraphNode,
    CandidateUrlEntry,
    GraphState,
    RawFetchedDocument,
)

logger = get_logger("collectors.graph.fetch_node")

SEARCH_URL_MARKERS = (
    "/catalogsearch/result",
    "/api/catalog_system/",
    "/search?",
    "/search/",
    "/buscar?",
    "?q=",
    "&q=",
    "?ft=",
    "?ntt=",
    "?s=",
)


def is_search_endpoint_url(url: str) -> bool:
    u_low = (url or "").lower()
    return any(m in u_low for m in SEARCH_URL_MARKERS)


class FetchNode(BaseGraphNode):
    """
    Nodo 2 (FetchNode + GraphIterator):
    Itera concurrentemente sobre los canales de cada tienda y descarga el HTML
    o payload JSON correspondiente, expandiendo enlaces candidatos en búsquedas.
    """

    node_name: str = "FetchNode"
    node_type: str = "iterator_node"

    def __init__(
        self,
        fetch_fn: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[..., Any]] = None,
        circuit_breakers: Optional[ dict ] = None,
    ):
        self.fetch_fn = fetch_fn
        self.scrape_fn = scrape_fn
        self.circuit_breakers = circuit_breakers

    def _get_effective_fetch_fn(self) -> Callable[..., Any]:
        if self.fetch_fn is not None:
            return self.fetch_fn
        # Resolver dinámicamente desde orchestrator si está cargado para respetar mocks de tests
        try:
            import app.collectors.orchestrator as orch_mod
            if hasattr(orch_mod, "fetch_page") and orch_mod.fetch_page is not None:
                return orch_mod.fetch_page
        except Exception:
            pass
        return default_fetch_page

    def _get_circuit_breaker(self, store_id: str) -> Any:
        if self.circuit_breakers and store_id in self.circuit_breakers:
            return self.circuit_breakers[store_id]
        try:
            from app.collectors.orchestrator import CIRCUIT_BREAKERS
            return CIRCUIT_BREAKERS.get(store_id)
        except Exception:
            return None

    async def _call_fetch(self, fetch_callable: Callable[..., Any], url: str) -> Optional[str]:
        res = fetch_callable(url)
        if asyncio.iscoroutine(res):
            res = await res
        return res if isinstance(res, str) and res.strip() else None

    async def _call_scrape_fn(
        self,
        store_id: str,
        url: str,
        state: GraphState,
    ) -> Optional[dict]:
        if self.scrape_fn is None:
            return None
        target_dict = state.target.to_target_dict()
        try:
            res = self.scrape_fn(
                store_id=store_id,
                url=url,
                canonical_title=state.target.title,
                tech_specs=state.target.tech_specs,
                target_product=target_dict,
            )
        except TypeError:
            try:
                res = self.scrape_fn(
                    store_id=store_id,
                    url=url,
                    canonical_title=state.target.title,
                    tech_specs=state.target.tech_specs,
                )
            except TypeError:
                res = self.scrape_fn(store_id, url)
        if asyncio.iscoroutine(res):
            res = await res
        return res if isinstance(res, dict) else None

    async def _fetch_store_candidates(
        self,
        store_id: str,
        entries: List[CandidateUrlEntry],
        state: GraphState,
    ) -> List[RawFetchedDocument]:
        docs: List[RawFetchedDocument] = []
        if not entries:
            return docs

        cb = self._get_circuit_breaker(store_id)
        if cb and not cb.can_execute():
            logger.info(f"[FetchNode] Omitiendo '{store_id}' (Circuit Breaker OPEN).")
            return docs

        fetch_callable = self._get_effective_fetch_fn()
        broad_q = state.search_queries[-1] if state.search_queries else state.target.title
        target_dict = state.target.to_target_dict()

        for entry in entries:
            target_url = entry.url
            if not entry.is_search_endpoint:
                _, clean_u = canonicalize_store_url(target_url)
                target_url = clean_u or target_url

            # Modo A: Si se inyectó un scrape_fn de alto nivel (ej. en tests unitarios o adaptadores)
            if self.scrape_fn is not None:
                try:
                    scraped_dict = await self._call_scrape_fn(store_id, target_url, state)
                except Exception as e:
                    if cb:
                        cb.record_failure(e)
                    continue

                if scraped_dict and scraped_dict.get("price") and float(scraped_dict["price"]) > 0:
                    raw_offer_url = str(scraped_dict.get("offer_url") or target_url).strip()
                    if entry.is_search_endpoint and is_search_endpoint_url(raw_offer_url):
                        continue
                    _, clean_offer = canonicalize_store_url(raw_offer_url)
                    scraped_dict["offer_url"] = clean_offer or raw_offer_url
                    if match_product_universal(target_dict, scraped_dict):
                        payload = json.dumps(
                            {"_pre_scraped_offer": True, "offer": scraped_dict},
                            ensure_ascii=False,
                        )
                        docs.append(
                            RawFetchedDocument(
                                store_id=store_id,
                                url=target_url,
                                canonical_url=scraped_dict["offer_url"],
                                channel=entry.channel,
                                content=payload,
                                content_type="json",
                                is_search_page=False,
                            )
                        )
                        # Cortar cascada en cuanto encontramos oferta válida para esta tienda
                        return docs
                continue

            # Modo B: Descarga HTTP/2 real de documento HTML o JSON API
            try:
                raw_content = await self._call_fetch(fetch_callable, target_url)
            except Exception as e:
                if cb:
                    cb.record_failure(e)
                logger.warning(f"[FetchNode] Error descargando {target_url} ({store_id}): {e}")
                continue

            if not raw_content:
                if not entry.is_search_endpoint and cb:
                    cb.record_failure("Respuesta vacía o error HTTP")
                continue

            # Si es Canal 3 (dork externo), extraer URLs reales de producto de la tienda y descargarlas
            if entry.channel == "channel_3_external_dork":
                dork_links = extract_store_urls_from_dork_html(raw_content, store_id=store_id, limit=5)
                for d_link in dork_links:
                    _, clean_d = canonicalize_store_url(d_link)
                    eff_d = clean_d or d_link
                    d_html = await self._call_fetch(fetch_callable, eff_d)
                    if d_html:
                        docs.append(
                            RawFetchedDocument(
                                store_id=store_id,
                                url=eff_d,
                                canonical_url=eff_d,
                                channel="channel_3_external_dork",
                                content=d_html,
                                content_type="json" if d_html.lstrip().startswith(("[", "{")) else "html",
                                is_search_page=False,
                            )
                        )
                if docs:
                    return docs
                continue

            is_search = entry.is_search_endpoint or is_search_endpoint_url(target_url)
            stripped = raw_content.lstrip()
            c_type = "json" if stripped.startswith(("[", "{")) else "html"
            _, clean_u = canonicalize_store_url(target_url)

            docs.append(
                RawFetchedDocument(
                    store_id=store_id,
                    url=target_url,
                    canonical_url=clean_u or target_url,
                    channel=entry.channel,
                    content=raw_content,
                    content_type=c_type,
                    is_search_page=is_search,
                )
            )

            # Si es una grilla de búsqueda HTML, extraer también las fichas de los primeros 5 candidatos
            # cuyo título coincida con broad_model_query para que ParseNode y SchemaExtractorNode
            # puedan inspeccionar su tabla de especificaciones y variantes SKU
            if is_search and c_type == "html":
                cand_links = extract_search_candidate_links(
                    html=raw_content,
                    search_url=target_url,
                    broad_model_query=broad_q,
                    limit=5,
                )
                for cand_link in cand_links:
                    _, clean_cand = canonicalize_store_url(cand_link)
                    eff_cand = clean_cand or cand_link
                    cand_html = await self._call_fetch(fetch_callable, eff_cand)
                    if cand_html:
                        docs.append(
                            RawFetchedDocument(
                                store_id=store_id,
                                url=eff_cand,
                                canonical_url=eff_cand,
                                channel="search_grid_expansion",
                                content=cand_html,
                                content_type="html",
                                is_search_page=False,
                            )
                        )

            # Si ya descargamos exitosamente la URL directa de Canal 1 (y no se pidió forzar búsqueda),
            # o si obtuvimos fichas de producto válidas, avanzamos a ParseNode
            if entry.channel == "channel_1_seed_cache" and docs:
                return docs

        return docs

    async def execute(self, state: GraphState) -> GraphState:
        tasks = [
            self._fetch_store_candidates(
                store_id=s_id,
                entries=state.candidate_urls_by_store.get(s_id, []),
                state=state,
            )
            for s_id in state.stores_to_check
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fetched_docs: List[RawFetchedDocument] = []
        for res in results:
            if isinstance(res, list):
                fetched_docs.extend(res)
            elif isinstance(res, Exception):
                state.errors.append(f"FetchNode error: {res}")

        state.fetched_documents = fetched_docs
        state.execution_trace.append(
            f"FetchNode: fetched_documents={len(fetched_docs)}"
        )
        return state
