"""
Motor y sesiones asíncronas de base de datos con SQLAlchemy 2.0 y aiosqlite.
Soporta persistencia real en SQLite (finprice_real.db) o PostgreSQL sin hilos bloqueantes.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("core.database")

Base = declarative_base()

# Configurar motor asíncrono
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Crea todas las tablas reales en la base de datos de forma asíncrona."""
    logger.info("Inicializando esquema de base de datos asíncrona...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Esquema de base de datos listo y verificado.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Generador asíncrono de sesión de base de datos para inyección en FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
