"""
Modelos ORM de SQLAlchemy 2.0 para persistencia en base de datos SQLite / PostgreSQL.
Incluye entidades de Productos, Precios por Tienda, Histórico a 30 días y Ofertas Comunitarias.
"""
from datetime import datetime, timezone
from typing import Generator
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
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

from app.core.config import settings

Base = declarative_base()


# ==============================================================================
# TABLAS DEL DOMINIO
# ==============================================================================

class ProductModel(Base):
    __tablename__ = "products"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    brand = Column(String(100), nullable=False, index=True)
    original_price = Column(Float, nullable=False)
    image_url = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    features_json = Column(Text, nullable=False, default="[]")
    tech_specs_json = Column(Text, nullable=False, default="{}")
    is_favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones en cascada
    store_prices = relationship("StorePriceModel", back_populates="product", cascade="all, delete-orphan", lazy="joined")
    price_history = relationship("PriceHistoryModel", back_populates="product", cascade="all, delete-orphan", lazy="joined")
    community_offers = relationship("CommunityOfferModel", back_populates="product", cascade="all, delete-orphan")


class StorePriceModel(Base):
    __tablename__ = "store_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    store_name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    offer_url = Column(String(500), nullable=False)
    last_checked = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("product_id", "store_id", name="uq_product_store"),
    )

    product = relationship("ProductModel", back_populates="store_prices")


class PriceHistoryModel(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    day_offset = Column(Integer, nullable=False)  # -30 a 0
    date_label = Column(String(50), nullable=False)  # ej. "22 Sep", "Hoy"
    price = Column(Float, nullable=False)
    recorded_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("product_id", "day_offset", name="uq_product_day_offset"),
    )

    product = relationship("ProductModel", back_populates="price_history")


class CommunityOfferModel(Base):
    __tablename__ = "community_offers"

    id = Column(String(64), primary_key=True, index=True)
    product_id = Column(String(50), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
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

    product = relationship("ProductModel", back_populates="community_offers")


class SyncLogModel(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    store_id = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED, CIRCUIT_OPEN
    products_updated = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, default=0.0)


# ==============================================================================
# MOTOR Y SESIONES DE BASE DE DATOS
# ==============================================================================

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Crea las tablas en la base de datos si no existen."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Generador de sesión SQLAlchemy con cierre automático para FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
