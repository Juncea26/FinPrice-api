"""
Entidades ORM reales de SQLAlchemy 2.0.
Reflejan el estado persistido en SQLite (finprice_real.db) o PostgreSQL.
Cero simulación: almacena únicamente productos, ofertas e historiales reales.
"""
from datetime import datetime, timezone
from sqlalchemy import (
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


class ProductEntity(Base):
    __tablename__ = "products"

    id = Column(String(80), primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(80), nullable=False, index=True)
    brand = Column(String(80), nullable=False, index=True)
    best_price = Column(Float, nullable=False, default=0.0)
    original_price = Column(Float, nullable=False, default=0.0)
    best_store_name = Column(String(100), nullable=False, default="En verificación")
    discount_percentage = Column(Integer, nullable=False, default=0)
    available_stores_count = Column(Integer, nullable=False, default=0)
    image_url = Column(String(500), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    features_json = Column(Text, nullable=False, default="[]")
    tech_specs_json = Column(Text, nullable=False, default="{}")
    is_favorite = Column(Boolean, default=False)
    historical_min_price = Column(Float, nullable=True)
    is_historical_min = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relaciones reales
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
    last_scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    day_offset = Column(Integer, nullable=False)  # 0 = Hoy, -1, -2... acumulados de recolecciones reales
    date_label = Column(String(50), nullable=False)  # "Hoy", "22 Oct"
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    timestamp_millis = Column(Integer, nullable=False)
    formatted_date = Column(String(100), nullable=False)
    author_name = Column(String(100), default="Usuario FinPrice")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("ProductEntity", back_populates="community_offers")
