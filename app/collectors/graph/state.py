"""
Estado del Grafo Dirigido y Esquemas Tipados Pydantic v2 inspirados en ScrapeGraphAI (state.py).
Define:
- BaseGraphNode: Abstracción base de nodo de grafo (input -> execute(state) -> state).
- ProductTargetSpec: Especificación técnica y semántica del producto objetivo.
- CandidateUrlEntry: URL candidata descubierta por SearchInternetNode en cualquiera de los 3 canales.
- RawFetchedDocument: Documento crudo (HTML o JSON API) descargado por FetchNode.
- ParsedPageNodeData: Documento estructurado destilado por ParseNode (DOM principal + JSON-LD + __NEXT_DATA__ + Tablas).
- ExtractedOfferSchema: Oferta tipada extraída por SchemaExtractorNode con resolución de variantes Multi-SKU.
- GraphState: Estado compartido entre todos los nodos de FinPriceMultiStoreGraph (SmartScraperMultiGraph).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

from app.collectors.fingerprint_matcher import (
    ProductFingerprint,
    build_fingerprint_from_catalog_item,
)
from app.collectors.universal_matcher import _extract_target_profile

ALL_8_PERU_STORES: Tuple[str, ...] = (
    "falabella",
    "ripley",
    "tottus",
    "efe",
    "curacao",
    "hiraoka",
    "metro",
    "wong",
)


class ProductTargetSpec(BaseModel):
    """
    Esquema Pydantic v2 que modela la especificación completa del producto objetivo
    para la búsqueda en cascada, resolución de variantes SKU y validación sobre el Corpus Completo.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(default="", description="ID canónico del producto (ej. 'prod_ipad_11')")
    title: str = Field(..., description="Título canónico del producto")
    category: str = Field(default="", description="Categoría del producto (Smartphones, Laptops, Tablets, TVs)")
    brand: str = Field(default="", description="Marca normalizada en minúsculas (ej. 'apple', 'lg', 'samsung')")
    model_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens obligatorios de línea, modelo y procesador/chip (ej. ['ipad', 'a16'], ['oled', 'c6'])",
    )
    storage_gb: Optional[int] = Field(
        default=None,
        description="Capacidad de almacenamiento requerida en GB (ej. 128, 256, 512, 1024)",
    )
    ram_gb: Optional[int] = Field(
        default=None,
        description="Memoria RAM requerida en GB cuando sea diferenciadora del SKU (ej. 8, 12, 16)",
    )
    screen_inches: Optional[float] = Field(
        default=None,
        description="Tamaño de pantalla requerido en pulgadas (ej. 11.0, 13.6, 55.0)",
    )
    network: Optional[str] = Field(
        default=None,
        description="Conectividad móvil requerida (ej. '5g')",
    )
    is_tv: bool = Field(default=False, description="Indica si el producto objetivo es un televisor")
    is_tablet_or_ipad: bool = Field(default=False, description="Indica si el producto objetivo es una tablet/iPad")
    requires_wifi_only_tablet: bool = Field(
        default=False,
        description="True cuando la tablet objetivo es versión solo Wi-Fi (bloquea versiones Cellular/5G/LTE)",
    )
    requires_5g: bool = Field(
        default=False,
        description="True cuando el dispositivo objetivo exige conectividad 5G",
    )
    forbidden_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens de otros modelos o generaciones que deben rechazarse inmediatamente",
    )
    tech_specs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diccionario de especificaciones técnicas base del producto",
    )
    seed_store_urls: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapa de URLs semilla por tienda {'falabella': 'https://...', ...}",
    )
    fingerprint: Optional[ProductFingerprint] = Field(
        default=None,
        description="Huella técnica determinista opcional asociada al producto",
    )

    @classmethod
    def from_target(cls, target_product: Any) -> "ProductTargetSpec":
        """Construye un ProductTargetSpec a partir de un dict de catálogo, entidad ORM, ProductTargetSpec o título."""
        if isinstance(target_product, cls):
            return target_product

        profile = _extract_target_profile(target_product)

        prod_id = ""
        category = ""
        tech_specs: Dict[str, Any] = {}
        seed_urls: Dict[str, str] = {}
        fp_obj: Optional[ProductFingerprint] = None

        if isinstance(target_product, dict):
            prod_id = str(target_product.get("id") or "")
            category = str(target_product.get("category") or "")
            tech_specs = dict(target_product.get("tech_specs") or target_product.get("techSpecs") or {})
            seed_urls = dict(target_product.get("store_urls") or {})
            if target_product.get("fingerprint") or target_product.get("title"):
                try:
                    fp_obj = build_fingerprint_from_catalog_item(target_product)
                except Exception:
                    fp_obj = None
        elif not isinstance(target_product, str):
            prod_id = str(getattr(target_product, "id", "") or "")
            category = str(getattr(target_product, "category", "") or "")
            raw_specs = getattr(target_product, "tech_specs_json", None) or getattr(target_product, "tech_specs", None)
            if isinstance(raw_specs, str):
                try:
                    tech_specs = json.loads(raw_specs)
                except Exception:
                    tech_specs = {}
            elif isinstance(raw_specs, dict):
                tech_specs = dict(raw_specs)

        return cls(
            id=prod_id,
            title=profile["title"],
            category=category,
            brand=profile["brand"],
            model_tokens=profile["model_tokens"],
            storage_gb=profile["storage_gb"],
            ram_gb=profile["ram_gb"],
            screen_inches=profile["screen_inches"],
            network="5g" if profile["requires_5g"] else None,
            is_tv=profile["is_tv"],
            is_tablet_or_ipad=profile["is_tablet_or_ipad"],
            requires_wifi_only_tablet=profile["requires_wifi_only_tablet"],
            requires_5g=profile["requires_5g"],
            forbidden_tokens=profile["forbidden_tokens"],
            tech_specs=tech_specs,
            seed_store_urls=seed_urls,
            fingerprint=fp_obj,
        )

    def to_target_dict(self) -> Dict[str, Any]:
        """Retorna representación dict compatible con match_product_universal."""
        d: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "brand": self.brand,
            "tech_specs": self.tech_specs,
            "store_urls": self.seed_store_urls,
        }
        if self.fingerprint is not None:
            d["fingerprint"] = self.fingerprint.model_dump()
        return d


class CandidateUrlEntry(BaseModel):
    """Representa una URL candidata descubierta por SearchInternetNode (Nodo 1)."""

    store_id: str
    url: str
    channel: str = Field(
        default="channel_1_seed_cache",
        description="Canal de descubrimiento: channel_1_seed_cache | channel_2_store_search | channel_3_external_dork | search_grid_expansion",
    )
    query_used: Optional[str] = None
    is_search_endpoint: bool = False
    priority: int = 1


class RawFetchedDocument(BaseModel):
    """Documento crudo (HTML o JSON API) descargado por FetchNode (Nodo 2)."""

    store_id: str
    url: str
    canonical_url: str
    channel: str = "channel_1_seed_cache"
    content: str
    content_type: str = "html"  # "html" | "json"
    is_search_page: bool = False


class ParsedPageNodeData(BaseModel):
    """
    Esquema Pydantic v2 del documento estructurado destilado por ParseNode (Nodo 3).
    Reúne el DOM principal aislado (sin carruseles), JSON-LD, #__NEXT_DATA__,
    window.__PRELOADED_STATE__, objetos VTEX y tablas de especificaciones técnicas.
    """

    model_config = ConfigDict(extra="allow")

    store_id: str
    url: str
    canonical_url: str
    channel: str = "channel_1_seed_cache"
    is_search_page: bool = False
    h1_title: str = ""
    meta_title: str = ""
    description: str = ""
    brand: str = ""
    image_url: Optional[str] = None
    json_ld_products: List[Dict[str, Any]] = Field(default_factory=list)
    next_data_product: Dict[str, Any] = Field(default_factory=dict)
    next_data_variants: List[Dict[str, Any]] = Field(default_factory=list)
    next_data_search_results: List[Dict[str, Any]] = Field(default_factory=list)
    preloaded_state_product: Dict[str, Any] = Field(default_factory=dict)
    vtex_api_items: List[Dict[str, Any]] = Field(default_factory=list)
    tech_specs: Dict[str, str] = Field(default_factory=dict)
    features: List[str] = Field(default_factory=list)
    search_candidate_links: List[str] = Field(default_factory=list)
    distilled_markdown: str = ""
    raw_html: str = ""

    def build_full_corpus(self) -> str:
        """Construye el Corpus Completo del nodo parseado."""
        title_part = self.h1_title or self.meta_title
        specs_part = json.dumps(self.tech_specs, ensure_ascii=False)
        return f"{title_part} {self.canonical_url} {specs_part} {self.description}".lower()


class ExtractedOfferSchema(BaseModel):
    """
    Esquema Pydantic v2 de oferta extraída por SchemaExtractorNode (Nodo 4),
    con soporte de variantes SKU resueltas y compatibilidad dual (atributo y dict).
    """

    model_config = ConfigDict(extra="allow")

    store_id: str
    store_name: str
    title: str
    price: float
    original_price: Optional[float] = None
    offer_url: str
    image_url: Optional[str] = None
    brand: Optional[str] = None
    variant_sku_id: Optional[str] = None
    in_stock: bool = True
    tech_specs: Dict[str, Any] = Field(default_factory=dict)
    features: List[str] = Field(default_factory=list)
    description: str = ""
    extraction_source: str = "deterministic_graph"

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def build_full_corpus(self) -> str:
        """
        Construye el Corpus Completo del Candidato para validación en MergeAnswersNode:
        full_corpus = f"{candidate.title} {candidate.offer_url} {json.dumps(candidate.tech_specs)} {candidate.description}".lower()
        """
        return (
            f"{self.title} {self.offer_url} "
            f"{json.dumps(self.tech_specs, ensure_ascii=False)} {self.description}"
        ).lower()

    def to_offer_dict(self) -> Dict[str, Any]:
        """Convierte el esquema tipado al diccionario estándar de oferta de FinPrice-api."""
        return {
            "store_id": self.store_id,
            "store_name": self.store_name,
            "title": self.title,
            "price": round(float(self.price), 2),
            "original_price": round(float(self.original_price), 2) if self.original_price else round(float(self.price), 2),
            "offer_url": self.offer_url,
            "image_url": self.image_url,
            "brand": self.brand,
            "variant_sku_id": self.variant_sku_id,
            "in_stock": self.in_stock,
            "tech_specs": self.tech_specs or {},
            "features": self.features or [],
            "description": self.description or "",
        }


class GraphState(BaseModel):
    """
    Estado global compartido del pipeline de grafo dirigido FinPriceMultiStoreGraph
    (SearchInternetNode -> FetchNode -> ParseNode -> SchemaExtractorNode -> MergeAnswersNode).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    target: ProductTargetSpec
    stores_to_check: List[str] = Field(default_factory=lambda: list(ALL_8_PERU_STORES))
    enable_cascade_search: bool = True
    enable_external_dork: bool = False
    enable_llm_fallback: bool = False
    search_queries: List[str] = Field(default_factory=list)
    candidate_urls_by_store: Dict[str, List[CandidateUrlEntry]] = Field(default_factory=dict)
    fetched_documents: List[RawFetchedDocument] = Field(default_factory=list)
    parsed_nodes: List[ParsedPageNodeData] = Field(default_factory=list)
    extracted_offers: List[ExtractedOfferSchema] = Field(default_factory=list)
    verified_offers: List[ExtractedOfferSchema] = Field(default_factory=list)
    execution_trace: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class BaseGraphNode(ABC):
    """Clase base para todos los nodos del grafo inspirado en ScrapeGraphAI."""

    node_name: str = "BaseGraphNode"
    node_type: str = "node"

    @abstractmethod
    async def execute(self, state: GraphState) -> GraphState:
        """Ejecuta la transformación del nodo sobre el estado compartido del grafo."""
        raise NotImplementedError
