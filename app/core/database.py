"""
Motor y sesiones de base de datos con SQLAlchemy 2.0.
Optimizado para Neon PostgreSQL Serverless Pooler con fallback a SQLite local.
Garantiza pool_pre_ping, pool_recycle, bajo consumo de RAM (< 15 MB) y compatibilidad total.
"""
import os
import sys
from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("core.database")

Base = declarative_base()


def normalize_database_url(url: str, is_async: bool = True) -> str:
    """
    Normaliza la URL de conexión a base de datos:
    - Remueve parámetros de channel_binding para evitar incompatibilidades con libpq/asyncpg.
    - Asegura prefijo correcto según motor asíncrono (asyncpg) o síncrono (psycopg2).
    - Adapta sslmode=require a ssl=require para asyncpg.
    """
    if not url:
        return url

    # Eliminar channel_binding=require que causa errores en contenedores Linux Slim
    url = url.replace("&channel_binding=require", "").replace("?channel_binding=require", "")
    if "?" not in url and "&" in url:
        url = url.replace("&", "?", 1)

    if is_async:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

        # asyncpg utiliza ssl=require en lugar de sslmode=require
        if "sslmode=" in url:
            url = url.replace("sslmode=", "ssl=")
    else:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

        if "ssl=require" in url and "sslmode=" not in url:
            url = url.replace("ssl=require", "sslmode=require")

    return url


# URLs normalizadas
ASYNC_DATABASE_URL = normalize_database_url(settings.DATABASE_URL, is_async=True)
SYNC_DATABASE_URL = normalize_database_url(settings.DATABASE_URL, is_async=False)

is_sqlite = "sqlite" in ASYNC_DATABASE_URL
is_test = bool("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") or settings.ENVIRONMENT == "test")

# Configuración del motor asíncrono
async_engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}

if is_sqlite:
    async_engine_kwargs["connect_args"] = {"check_same_thread": False}
elif is_test:
    async_engine_kwargs["poolclass"] = NullPool
else:
    # Optimizado para Neon Serverless Pooler y consumo mínimo de RAM (< 15 MB)
    async_engine_kwargs["pool_recycle"] = 300
    async_engine_kwargs["pool_size"] = 5
    async_engine_kwargs["max_overflow"] = 5

engine = create_async_engine(ASYNC_DATABASE_URL, **async_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Motor síncrono para migraciones o tareas batch que utilicen psycopg2
sync_engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}
if is_sqlite:
    sync_engine_kwargs["connect_args"] = {"check_same_thread": False}
elif is_test:
    sync_engine_kwargs["poolclass"] = NullPool
else:
    sync_engine_kwargs["pool_recycle"] = 300
    sync_engine_kwargs["pool_size"] = 5
    sync_engine_kwargs["max_overflow"] = 5

sync_engine = create_engine(SYNC_DATABASE_URL, **sync_engine_kwargs)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)


async def init_db() -> None:
    """Crea y verifica todas las tablas del sistema en la base de datos sin borrar datos existentes."""
    # Importar modelos para que estén presentes en Base.metadata
    import app.models.entities  # noqa: F401

    logger.info("Inicializando/verificando tablas en base de datos...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Esquema de base de datos verificado y listo.")


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
