"""
Esquemas Pydantic v2 alineados con el contrato del dominio móvil (camelCase)
y esquemas de retrocompatibilidad para /products.
"""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


# ==============================================================================
# BASE SCHEMA CON CONFIGURACIÓN CAMELCASE
# ==============================================================================

class CamelModel(BaseModel):
    """
    Modelo base con alias camelCase automático y compatibilidad bidireccional.
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ==============================================================================
# TIENDAS Y PRECIOS
# ==============================================================================

class StoreSchema(CamelModel):
    id: str = Field(..., description="Identificador único (efe, falabella, ripley, curacao, hiraoka, tottus, metro, wong)")
    name: str = Field(..., description="Nombre comercial oficial de la tienda retail")
    code: str = Field(..., description="Código en mayúsculas (EFE, FALABELLA, etc.)")
    is_enabled: bool = Field(default=True, description="Indica si la tienda está activa en el sistema")
    circuit_status: Optional[str] = Field(default="CLOSED", description="Estado del Circuit Breaker (CLOSED, OPEN, HALF_OPEN)")


class StorePriceSchema(CamelModel):
    store_id: str = Field(..., description="Identificador de la tienda retail")
    store_name: str = Field(..., description="Nombre de la tienda")
    price: float = Field(..., gt=0, description="Precio actual en Soles (PEN)")
    original_price: Optional[float] = Field(default=None, description="Precio de lista o tachado si aplica")
    offer_url: str = Field(..., description="URL https validada de la oferta")
    is_best_price: bool = Field(default=False, description="True si es el precio más bajo entre todas las tiendas")

    @field_validator("price", "original_price", mode="before")
    @classmethod
    def round_prices(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return round(float(v), 2)
        return v

    @field_validator("offer_url")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("La URL de la oferta debe comenzar con https://")
        return v


class PricePointSchema(CamelModel):
    day_offset: int = Field(..., ge=-30, le=0, description="Días relativos desde hoy (-30 a 0)")
    date_label: str = Field(..., description="Etiqueta legible en español (ej. '22 Sep', 'Hoy')")
    price: float = Field(..., gt=0, description="Precio histórico en PEN")

    @field_validator("price", mode="before")
    @classmethod
    def round_price(cls, v: float) -> float:
        return round(float(v), 2)


# ==============================================================================
# PRODUCTOS Y CATÁLOGO
# ==============================================================================

class ProductSchema(CamelModel):
    id: str = Field(..., description="Identificador único del producto (ej. 'prod_1')")
    title: str = Field(..., description="Título y modelo del producto")
    category: str = Field(..., description="Categoría (Smartphones, Laptops, Tablets, TVs)")
    best_price: float = Field(..., gt=0, description="Menor precio disponible actual en PEN")
    original_price: float = Field(..., gt=0, description="Precio original o de lista en PEN")
    best_store_name: str = Field(..., description="Nombre de la tienda con la mejor oferta")
    discount_percentage: int = Field(default=0, ge=0, le=100, description="Porcentaje de descuento redondeado")
    available_stores_count: int = Field(default=0, ge=0, description="Cantidad de tiendas que ofrecen el producto")
    image_url: str = Field(..., description="URL de imagen del producto (https)")
    description: str = Field(..., description="Descripción detallada del producto")
    features: List[str] = Field(default_factory=list, description="Lista de características destacadas")
    is_favorite: bool = Field(default=False, description="Flag de favorito")
    store_prices: List[StorePriceSchema] = Field(default_factory=list, description="Ofertas por tienda ordenadas de menor a mayor precio")
    historical_min_price: Optional[float] = Field(default=None, description="Mínimo precio histórico registrado")
    tech_specs: Dict[str, str] = Field(default_factory=dict, description="Especificaciones técnicas normalizadas")
    is_historical_min: bool = Field(default=False, description="True si bestPrice es menor o igual al mínimo histórico")
    price_history_30_days: List[PricePointSchema] = Field(default_factory=list, description="Serie temporal de precios de los últimos 30 días")

    @field_validator("best_price", "original_price", "historical_min_price", mode="before")
    @classmethod
    def round_product_prices(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return round(float(v), 2)
        return v


# ==============================================================================
# OFERTAS FÍSICAS COMUNITARIAS
# ==============================================================================

class CommunityPhysicalOfferSchema(CamelModel):
    id: str = Field(..., description="UUID único de la oferta comunitaria")
    product_id: str = Field(..., description="ID del producto asociado")
    product_name: str = Field(..., description="Nombre del producto asociado")
    physical_store_name: str = Field(..., description="Nombre de la tienda física (ej. 'Falabella Mall Aventura Chiclayo')")
    department: str = Field(..., description="Departamento peruano (ej. Lambayeque, Lima, Arequipa)")
    province: str = Field(..., description="Provincia")
    district: str = Field(..., description="Distrito")
    price_found: float = Field(..., gt=0, description="Precio encontrado en tienda física en PEN")
    photo_uri: str = Field(default="", description="URI o URL de foto de prueba")
    comment: str = Field(default="", description="Comentarios o condiciones de la oferta física")
    timestamp_millis: int = Field(..., description="Marca de tiempo en milisegundos")
    formatted_date: str = Field(..., description="Fecha formateada (ej. '22 Oct 2026, 14:30')")
    author_name: str = Field(default="Usuario FinPrice", description="Nombre del autor del reporte")


class CommunityOfferCreateSchema(CamelModel):
    product_id: str = Field(..., description="ID del producto existente")
    product_name: Optional[str] = None
    physical_store_name: str = Field(..., min_length=2, max_length=120, description="Nombre de la tienda física")
    department: str = Field(..., description="Departamento del Perú válido")
    province: str = Field(..., min_length=2, max_length=100, description="Provincia")
    district: str = Field(..., min_length=2, max_length=100, description="Distrito")
    price_found: float = Field(..., gt=0, description="Precio en Soles (PEN)")
    photo_uri: str = ""
    comment: str = ""
    author_name: str = "Usuario FinPrice"


# ==============================================================================
# RETROCOMPATIBILIDAD LEGADA (GET /products)
# ==============================================================================

class StoreOffer(BaseModel):
    store_name: str
    price: float
    currency: str = "PEN"
    product_url: str


class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    lowest_price: float
    best_store: str
    offers: List[StoreOffer]


# ==============================================================================
# DIAGNÓSTICO Y RESPUESTAS DEL SISTEMA
# ==============================================================================

class HealthResponse(CamelModel):
    status: str
    version: str
    database: str
    total_products: int
    total_stores: int
    active_stores: int
    last_sync_timestamp: Optional[str]
    stores_status: Dict[str, Any]
    uptime_seconds: float


class SyncResponse(CamelModel):
    status: str
    message: str
    triggered_at: str
