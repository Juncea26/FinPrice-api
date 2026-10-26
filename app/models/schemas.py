"""
Esquemas Pydantic v2 en camelCase estricto alineados con el dominio móvil
y esquemas de retrocompatibilidad para /products.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class StoreSchema(CamelModel):
    id: str = Field(..., description="Identificador único del retailer (efe, falabella, ripley, etc.)")
    name: str = Field(..., description="Nombre comercial oficial de la tienda")
    code: str = Field(..., description="Código en mayúsculas (EFE, FALABELLA, etc.)")
    is_enabled: bool = Field(default=True, description="Indica si la tienda está activa en el sistema")
    circuit_status: Optional[str] = Field(default="CLOSED", description="Estado del Circuit Breaker")


class StorePriceSchema(CamelModel):
    store_id: str = Field(..., description="ID del retailer peruano")
    store_name: str = Field(..., description="Nombre de la tienda")
    price: float = Field(..., gt=0, description="Precio real en Soles (PEN)")
    original_price: Optional[float] = Field(default=None, description="Precio de lista real si existe")
    offer_url: str = Field(..., description="URL real verificada de la oferta")
    is_best_price: bool = Field(default=False, description="True si es la oferta con menor precio actual")

    @field_validator("price", "original_price", mode="before")
    @classmethod
    def round_prices(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return round(float(v), 2)
        return v

    @field_validator("offer_url")
    @classmethod
    def validate_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("La URL debe iniciar con https://")
        return v


class PricePointSchema(CamelModel):
    day_offset: int = Field(..., description="Día relativo (0 = Hoy, -1, -2...)")
    date_label: str = Field(..., description="Etiqueta en español (ej. 'Hoy', '22 Oct')")
    price: float = Field(..., gt=0, description="Precio real observado en Soles (PEN)")

    @field_validator("price", mode="before")
    @classmethod
    def round_point(cls, v: float) -> float:
        return round(float(v), 2)


class ProductSchema(CamelModel):
    id: str = Field(..., description="ID del producto (ej. 'prod_samsung_s25_ultra')")
    title: str = Field(..., description="Nombre oficial del producto")
    category: str = Field(..., description="Categoría (Smartphones, Laptops, Tablets, TVs)")
    brand: str = Field(default="", description="Marca oficial normalizada (Samsung, Apple, Xiaomi, etc.)")
    best_price: float = Field(..., gt=0, description="Menor precio real encontrado en Soles (PEN)")
    original_price: float = Field(..., gt=0, description="Precio de lista o tachado real")
    best_store_name: str = Field(..., description="Tienda que ofrece el mejor precio actual")
    discount_percentage: int = Field(default=0, ge=0, le=100, description="Porcentaje de descuento calculado")
    available_stores_count: int = Field(default=0, ge=0, description="Cantidad de tiendas reales donde sí existe el producto")
    image_url: str = Field(..., description="URL oficial de la imagen del producto")
    description: str = Field(..., description="Descripción detallada del producto")
    features: List[str] = Field(default_factory=list, description="Lista de características destacadas")
    is_favorite: bool = Field(default=False, description="Flag de favorito")
    store_prices: List[StorePriceSchema] = Field(
        default_factory=list,
        description="Ofertas reales ordenadas de menor a mayor precio (solo tiendas donde existe)",
    )
    historical_min_price: Optional[float] = Field(default=None, description="Mínimo precio real observado en BD")
    tech_specs: Dict[str, str] = Field(default_factory=dict, description="Especificaciones técnicas normalizadas")
    is_historical_min: bool = Field(default=False, description="True si bestPrice es menor o igual al mínimo histórico")
    price_history_30_days: List[PricePointSchema] = Field(
        default_factory=list, description="Historial de precios reales acumulado en BD"
    )

    @field_validator("best_price", "original_price", "historical_min_price", mode="before")
    @classmethod
    def round_product_prices(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return round(float(v), 2)
        return v


class CommunityPhysicalOfferSchema(CamelModel):
    id: str = Field(..., description="UUID único de la oferta comunitaria")
    product_id: str = Field(..., description="ID del producto asociado")
    product_name: str = Field(..., description="Nombre del producto")
    physical_store_name: str = Field(..., description="Nombre de la tienda física (ej. 'Falabella Mall Aventura')")
    department: str = Field(..., description="Departamento peruano (ej. Lambayeque, Lima)")
    province: str = Field(..., description="Provincia")
    district: str = Field(..., description="Distrito")
    price_found: float = Field(..., gt=0, description="Precio encontrado en vitrina en PEN")
    photo_uri: str = Field(default="", description="Foto de prueba o comprobante")
    comment: str = Field(default="", description="Comentarios o condiciones de la oferta")
    timestamp_millis: int = Field(..., description="Marca de tiempo en milisegundos")
    formatted_date: str = Field(..., description="Fecha formateada (ej. '22 Oct 2026, 10:30')")
    author_name: str = Field(default="Usuario FinPrice", description="Nombre del autor")


class CommunityOfferCreateSchema(CamelModel):
    product_id: str = Field(..., description="ID del producto existente")
    product_name: Optional[str] = None
    physical_store_name: str = Field(..., min_length=2, max_length=120)
    department: str = Field(..., description="Departamento del Perú")
    province: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    price_found: float = Field(..., gt=0)
    photo_uri: str = ""
    comment: str = ""
    author_name: str = "Usuario FinPrice"


# ==============================================================================
# RETROCOMPATIBILIDAD (GET /products)
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
# RESPUESTAS DEL SISTEMA Y DIAGNÓSTICO
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


class DynamicFiltersSchema(BaseModel):
    """Esquema de facetas dinámicas generadas desde los productos activos en base de datos."""

    categories: List[str] = Field(default_factory=list)
    brands_by_category: Dict[str, List[str]] = Field(default_factory=dict)
    specs_by_category: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)
    brandsByCategory: Optional[Dict[str, List[str]]] = None
    specsByCategory: Optional[Dict[str, Dict[str, List[str]]]] = None
