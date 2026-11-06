"""
Entidades ORM de SQLAlchemy 2.0 para FinPrice API.
Mapeadas a Neon PostgreSQL y SQLite con integridad referencial completa.
Tablas:
- products: Catálogo de productos reales con precios, marcas, categorías e imágenes oficiales.
- store_offers: Ofertas verificadas por tienda y por producto.
- price_history: Serie histórica de precios (últimos 30 días).
- community_offers: Ofertas físicas comunitarias reportadas por usuarios en tiendas locales.
- community_posts: Publicaciones de la comunidad con soporte para crear, listar y editar.
- complaints: Libro de Reclamaciones virtual y registro de quejas/reclamos formal.
- cancellation_suggestions: Sugerencias y motivos de cancelación de suscripción.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProductEntity(Base):
    __tablename__ = "products"

    id = Column(String(80), primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(80), nullable=False, index=True)
    brand = Column(String(80), nullable=False, index=True)
    best_price = Column(Float, nullable=False, default=0.0)
    original_price = Column(Float, nullable=False, default=0.0)
    best_store_name = Column(String(100), nullable=False, default="En verificación")
    best_store_url = Column(String(600), nullable=False, default="")
    previous_best_price = Column(Float, nullable=True)
    price_drop_amount = Column(Float, nullable=False, default=0.0)
    days_tracked = Column(Integer, nullable=False, default=1)
    discount_percentage = Column(Integer, nullable=False, default=0)
    available_stores_count = Column(Integer, nullable=False, default=0)
    image_url = Column(String(500), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    features_json = Column(Text, nullable=False, default="[]")
    tech_specs_json = Column(Text, nullable=False, default="{}")
    is_favorite = Column(Boolean, default=False)
    historical_min_price = Column(Float, nullable=True)
    is_historical_min = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    # Relaciones
    store_offers = relationship(
        "StoreOfferEntity",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    price_history = relationship(
        "PriceHistoryEntity",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    community_offers = relationship(
        "CommunityOfferEntity",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    community_posts = relationship(
        "CommunityPostEntity",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StoreOfferEntity(Base):
    __tablename__ = "store_offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(
        String(80), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id = Column(String(50), nullable=False, index=True)
    store_name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    offer_url = Column(String(600), nullable=False)
    is_best_price = Column(Boolean, default=False)
    last_scraped_at = Column(DateTime, default=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("product_id", "store_id", name="uq_real_product_store"),
    )

    product = relationship("ProductEntity", back_populates="store_offers")


class PriceHistoryEntity(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(
        String(80), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_offset = Column(Integer, nullable=False)  # 0 = Hoy, -1, -2...
    date_label = Column(String(50), nullable=False)  # "02 Nov", "03 Nov", etc.
    recorded_date = Column(String(20), nullable=True, index=True)  # "2026-11-05"
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("product_id", "day_offset", name="uq_real_product_day"),
    )

    product = relationship("ProductEntity", back_populates="price_history")


class CommunityOfferEntity(Base):
    __tablename__ = "community_offers"

    id = Column(String(80), primary_key=True, index=True)
    product_id = Column(
        String(80), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_name = Column(String(255), nullable=False)
    physical_store_name = Column(String(120), nullable=False)
    department = Column(String(100), nullable=False, index=True)
    province = Column(String(100), nullable=False, index=True)
    district = Column(String(100), nullable=False, index=True)
    price_found = Column(Float, nullable=False)
    photo_uri = Column(String(500), default="")
    comment = Column(Text, default="")
    timestamp_millis = Column(BigInteger, nullable=False)
    formatted_date = Column(String(100), nullable=False)
    author_name = Column(String(100), default="Usuario FinPrice")
    created_at = Column(DateTime, default=utc_now_naive)

    product = relationship("ProductEntity", back_populates="community_offers")


class CommunityPostEntity(Base):
    __tablename__ = "community_posts"

    id = Column(String(80), primary_key=True, index=True)
    product_id = Column(
        String(80), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=True, default="")
    product_name = Column(String(255), nullable=True)
    physical_store_name = Column(String(120), nullable=True)
    price = Column(Float, nullable=True)
    department = Column(String(100), nullable=True, index=True)
    province = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True, index=True)
    photo_uri = Column(String(500), default="")
    author_name = Column(String(100), default="Usuario FinPrice")
    likes_count = Column(Integer, default=0)
    status = Column(String(50), default="active")
    timestamp_millis = Column(BigInteger, nullable=True)
    formatted_date = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    product = relationship("ProductEntity", back_populates="community_posts")


class ComplaintEntity(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_number = Column(String(60), unique=True, index=True, nullable=False)  # Ej. REC-2026-0001
    full_name = Column(String(150), nullable=False)
    document_type = Column(String(20), nullable=False, default="DNI")  # DNI, CE, Pasaporte, RUC
    document_number = Column(String(30), nullable=False, index=True)
    email = Column(String(120), nullable=False, index=True)
    phone = Column(String(30), nullable=False)
    address = Column(String(255), nullable=True, default="")
    department = Column(String(100), nullable=True, default="")
    province = Column(String(100), nullable=True, default="")
    district = Column(String(100), nullable=True, default="")
    is_minor = Column(Boolean, default=False)
    guardian_name = Column(String(150), nullable=True, default="")
    complaint_type = Column(String(50), nullable=False, default="Reclamo")  # Reclamo, Queja, Sugerencia, Cancelación de suscripción
    contracted_good = Column(String(50), default="Servicio")  # Producto o Servicio
    claimed_amount = Column(Float, nullable=True)
    description = Column(Text, nullable=False)
    consumer_request = Column(Text, nullable=True, default="")
    status = Column(String(50), default="Pendiente")  # Pendiente, En trámite, Atendido, Resuelto
    response_detail = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )


class CancellationSuggestionEntity(Base):
    __tablename__ = "cancellation_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(120), nullable=False, index=True)
    reason = Column(String(255), nullable=False)
    feedback = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, default=utc_now_naive)
