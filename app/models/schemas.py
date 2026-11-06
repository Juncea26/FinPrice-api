"""
Esquemas Pydantic v2 en camelCase estricto alineados con el dominio móvil
y esquemas de retrocompatibilidad para /products.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
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
    product_url: Optional[str] = Field(default=None, description="Enlace directo real del producto en la tienda")
    url: Optional[str] = Field(default=None, description="Alias directo de la URL de la oferta")
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

    def model_post_init(self, __context: Any) -> None:
        if not self.product_url:
            self.product_url = self.offer_url
        if not self.url:
            self.url = self.offer_url

    @computed_field(alias="product_url")
    @property
    def product_url_snake(self) -> str:
        return self.product_url or self.offer_url


class PricePointSchema(CamelModel):
    day_offset: int = Field(..., description="Día relativo (0 = Hoy, -1, -2...)")
    date_label: str = Field(..., description="Etiqueta en español (ej. '02 Nov', '03 Nov', '04 Nov', '05 Nov')")
    price: float = Field(..., gt=0, description="Precio real observado en Soles (PEN)")
    recorded_date: Optional[str] = Field(default=None, description="Fecha calendario ISO (ej. '2026-11-05')")

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
    best_store_url: str = Field(default="", description="Enlace directo a la tienda con el mejor precio")
    product_url: str = Field(default="", description="Enlace directo de la oferta ganadora")
    previous_best_price: Optional[float] = Field(default=None, description="Mejor precio del día anterior o previo")
    price_drop_amount: float = Field(default=0.0, ge=0.0, description="Monto de bajada de precio en Soles")
    days_tracked: int = Field(default=1, ge=1, description="Número real de días acumulados en price_history")
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

    @field_validator("best_price", "original_price", "historical_min_price", "previous_best_price", "price_drop_amount", mode="before")
    @classmethod
    def round_product_prices(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return round(float(v), 2)
        return v

    def model_post_init(self, __context: Any) -> None:
        if not self.best_store_url and self.store_prices:
            self.best_store_url = self.store_prices[0].offer_url
        if not self.product_url:
            self.product_url = self.best_store_url

    @computed_field(alias="best_store_url")
    @property
    def best_store_url_snake(self) -> str:
        return self.best_store_url

    @computed_field(alias="product_url")
    @property
    def product_url_snake(self) -> str:
        return self.product_url or self.best_store_url

    @computed_field(alias="previous_best_price")
    @property
    def previous_best_price_snake(self) -> Optional[float]:
        return self.previous_best_price

    @computed_field(alias="price_drop_amount")
    @property
    def price_drop_amount_snake(self) -> float:
        return self.price_drop_amount

    @computed_field(alias="best_store_name")
    @property
    def best_store_name_snake(self) -> str:
        return self.best_store_name

    @computed_field(alias="days_tracked")
    @property
    def days_tracked_snake(self) -> int:
        return self.days_tracked

    @computed_field(alias="offers")
    @property
    def offers_alias(self) -> List[StorePriceSchema]:
        return self.store_prices

    @computed_field(alias="price_history")
    @property
    def price_history_alias(self) -> List[PricePointSchema]:
        return self.price_history_30_days


class PriceDropNotificationSchema(CamelModel):
    product_id: str = Field(..., description="ID del producto")
    product_title: str = Field(..., description="Título oficial del producto")
    old_price: float = Field(..., description="Precio anterior o de referencia")
    new_price: float = Field(..., description="Nuevo mejor precio actual")
    drop_amount: float = Field(..., description="Monto ahorrado por la bajada de precio")
    store_name: str = Field(..., description="Tienda oficial donde bajó de precio")
    product_url: str = Field(..., description="Enlace directo a la oferta en la tienda más barata")
    image_url: str = Field(..., description="Imagen oficial del producto")
    timestamp: str = Field(..., description="Fecha y hora de detección ISO-8601")

    @computed_field(alias="product_id")
    @property
    def product_id_snake(self) -> str:
        return self.product_id

    @computed_field(alias="product_title")
    @property
    def product_title_snake(self) -> str:
        return self.product_title

    @computed_field(alias="old_price")
    @property
    def old_price_snake(self) -> float:
        return self.old_price

    @computed_field(alias="new_price")
    @property
    def new_price_snake(self) -> float:
        return self.new_price

    @computed_field(alias="drop_amount")
    @property
    def drop_amount_snake(self) -> float:
        return self.drop_amount

    @computed_field(alias="store_name")
    @property
    def store_name_snake(self) -> str:
        return self.store_name

    @computed_field(alias="product_url")
    @property
    def product_url_snake(self) -> str:
        return self.product_url

    @computed_field(alias="image_url")
    @property
    def image_url_snake(self) -> str:
        return self.image_url


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
    store_id: Optional[str] = None
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
    next_scheduled_update: Optional[str] = Field(default="00:59 America/Lima")
    stores_status: Dict[str, Any]
    uptime_seconds: float

    @computed_field(alias="next_scheduled_update")
    def next_scheduled_update_exact(self) -> str:
        return self.next_scheduled_update or "00:59 America/Lima"


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


# ==============================================================================
# PUBLICACIONES DE LA COMUNIDAD (GET, POST, PUT)
# ==============================================================================

class CommunityPostSchema(CamelModel):
    id: str = Field(..., description="ID único de la publicación comunitaria")
    product_id: Optional[str] = Field(default=None, description="ID del producto asociado")
    title: str = Field(..., description="Título de la publicación")
    content: Optional[str] = Field(default="", description="Detalle del post")
    product_name: Optional[str] = Field(default="", description="Nombre del producto")
    physical_store_name: Optional[str] = Field(default="", description="Nombre de la tienda física")
    price: Optional[float] = Field(default=None, description="Precio observado en vitrina en PEN")
    department: Optional[str] = Field(default="", description="Departamento peruano")
    province: Optional[str] = Field(default="", description="Provincia")
    district: Optional[str] = Field(default="", description="Distrito")
    photo_uri: Optional[str] = Field(default="", description="Foto o comprobante")
    author_name: str = Field(default="Usuario FinPrice", description="Nombre del autor")
    likes_count: int = Field(default=0, description="Cantidad de likes")
    status: str = Field(default="active", description="Estado de la publicación")
    formatted_date: Optional[str] = Field(default="", description="Fecha legible")
    timestamp_millis: Optional[int] = Field(default=None, description="Marca de tiempo en milisegundos")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CommunityPostCreateSchema(CamelModel):
    title: str = Field(..., min_length=2, max_length=255)
    content: Optional[str] = Field(default="", max_length=2000)
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    physical_store_name: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    department: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    photo_uri: Optional[str] = ""
    author_name: Optional[str] = "Usuario FinPrice"


class CommunityPostUpdateSchema(CamelModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    content: Optional[str] = Field(default=None, max_length=2000)
    product_name: Optional[str] = None
    physical_store_name: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    department: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    photo_uri: Optional[str] = None
    author_name: Optional[str] = None
    status: Optional[str] = None


# ==============================================================================
# LIBRO DE RECLAMACIONES Y CANCELACIONES
# ==============================================================================

class ComplaintCreateSchema(CamelModel):
    full_name: str = Field(..., min_length=3, max_length=150)
    document_type: str = Field(default="DNI", max_length=20)
    document_number: str = Field(..., min_length=5, max_length=30)
    email: str = Field(..., max_length=120)
    phone: str = Field(..., min_length=6, max_length=30)
    address: Optional[str] = Field(default="", max_length=255)
    department: Optional[str] = Field(default="", max_length=100)
    province: Optional[str] = Field(default="", max_length=100)
    district: Optional[str] = Field(default="", max_length=100)
    is_minor: bool = False
    guardian_name: Optional[str] = Field(default="", max_length=150)
    complaint_type: str = Field(default="Reclamo", description="'Reclamo', 'Queja', 'Sugerencia' o 'Cancelación de suscripción'")
    contracted_good: str = Field(default="Servicio", description="'Producto' o 'Servicio'")
    claimed_amount: Optional[float] = None
    description: str = Field(..., min_length=10, description="Detalle del reclamo o sugerencia")
    consumer_request: Optional[str] = Field(default="", description="Pedido concreto del consumidor")


class ComplaintSchema(CamelModel):
    id: int
    claim_number: str
    full_name: str
    document_type: str
    document_number: str
    email: str
    phone: str
    address: Optional[str] = ""
    department: Optional[str] = ""
    province: Optional[str] = ""
    district: Optional[str] = ""
    is_minor: bool = False
    guardian_name: Optional[str] = ""
    complaint_type: str
    contracted_good: str
    claimed_amount: Optional[float] = None
    description: str
    consumer_request: Optional[str] = ""
    status: str
    response_detail: Optional[str] = ""
    created_at: Optional[str] = None


class CancellationSuggestionCreateSchema(CamelModel):
    email: str = Field(..., max_length=120)
    reason: str = Field(..., min_length=3, max_length=255)
    feedback: Optional[str] = Field(default="", max_length=2000)


class CancellationSuggestionSchema(CamelModel):
    id: int
    email: str
    reason: str
    feedback: Optional[str] = ""
    created_at: Optional[str] = None

