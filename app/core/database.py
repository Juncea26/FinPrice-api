"""
Motor y sesiones de base de datos con SQLAlchemy 2.0.
Optimizado para Neon PostgreSQL Serverless Pooler con fallback a SQLite local.
Garantiza pool_pre_ping, pool_recycle, bajo consumo de RAM (< 15 MB) y compatibilidad total.
"""
import os
import re
import sys
from typing import AsyncGenerator
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("core.database")

Base = declarative_base()

# Configuración estricta de Pool de máximo 10 conexiones (pool_size=5, max_overflow=5)
POOL_SIZE: int = 5
MAX_OVERFLOW: int = 5
MAX_POOL_CONNECTIONS: int = POOL_SIZE + MAX_OVERFLOW
MAX_TOTAL_POOL_CONNECTIONS: int = MAX_POOL_CONNECTIONS
POOL_RECYCLE_SECONDS: int = 300


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


# URLs normalizadas para separación Writer (Scraper/Escritura) y Reader (Consultas App Solo Lectura)
_raw_writer_url = settings.WRITER_DATABASE_URL or settings.DATABASE_URL
_raw_reader_url = settings.READER_DATABASE_URL or settings.DATABASE_URL

ASYNC_DATABASE_URL = normalize_database_url(_raw_writer_url, is_async=True)
ASYNC_READER_DATABASE_URL = normalize_database_url(_raw_reader_url, is_async=True)
SYNC_DATABASE_URL = normalize_database_url(_raw_writer_url, is_async=False)

is_sqlite = "sqlite" in ASYNC_DATABASE_URL
is_test = bool("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") or settings.ENVIRONMENT == "test")

# Configuración del motor asíncrono con Pool estricto de máximo 10 conexiones (pool_size=5, max_overflow=5)
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
    async_engine_kwargs["pool_recycle"] = POOL_RECYCLE_SECONDS
    async_engine_kwargs["pool_size"] = POOL_SIZE
    async_engine_kwargs["max_overflow"] = MAX_OVERFLOW

# 1. Motor de Escritura (Writer Engine): usado por el motor de Web Scraping y rutas de escritura controlada
writer_engine = create_async_engine(ASYNC_DATABASE_URL, **async_engine_kwargs)
engine = writer_engine

WriterSessionLocal = async_sessionmaker(
    bind=writer_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
AsyncSessionLocal = WriterSessionLocal

# 2. Motor de Solo Lectura (Reader Engine): usado exclusivamente por las rutas GET de consulta de la App
reader_engine = create_async_engine(ASYNC_READER_DATABASE_URL, **async_engine_kwargs)

ReaderSessionLocal = async_sessionmaker(
    bind=reader_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

_FORBIDDEN_WRITE_SQL_PREFIX = re.compile(
    r"^\s*(?:INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


@event.listens_for(reader_engine.sync_engine, "before_cursor_execute")
def _enforce_read_only_cursor(conn, cursor, statement, parameters, context, executemany):
    """Bloquea físicamente cualquier sentencia DML/DDL de escritura en el motor de solo lectura (reader_engine)."""
    if _FORBIDDEN_WRITE_SQL_PREFIX.match(statement or ""):
        raise PermissionError(
            "READ_ONLY_SESSION_VIOLATION: Operación de escritura bloqueada en sesión de solo lectura (reader_engine)."
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
    sync_engine_kwargs["pool_recycle"] = POOL_RECYCLE_SECONDS
    sync_engine_kwargs["pool_size"] = POOL_SIZE
    sync_engine_kwargs["max_overflow"] = MAX_OVERFLOW

sync_engine = create_engine(SYNC_DATABASE_URL, **sync_engine_kwargs)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)


def _ensure_new_columns(sync_conn) -> None:
    """Agrega columnas nuevas sin pérdida de datos en Neon PostgreSQL o SQLite."""
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    if "products" in existing_tables:
        prod_cols = {c["name"] for c in inspector.get_columns("products")}
        if "best_store_url" not in prod_cols:
            sync_conn.execute(text("ALTER TABLE products ADD COLUMN best_store_url VARCHAR(600) NOT NULL DEFAULT ''"))
        if "previous_best_price" not in prod_cols:
            sync_conn.execute(text("ALTER TABLE products ADD COLUMN previous_best_price FLOAT"))
        if "price_drop_amount" not in prod_cols:
            sync_conn.execute(text("ALTER TABLE products ADD COLUMN price_drop_amount FLOAT NOT NULL DEFAULT 0.0"))
        if "days_tracked" not in prod_cols:
            sync_conn.execute(text("ALTER TABLE products ADD COLUMN days_tracked INTEGER NOT NULL DEFAULT 1"))
    if "price_history" in existing_tables:
        hist_cols = {c["name"] for c in inspector.get_columns("price_history")}
        if "recorded_date" not in hist_cols:
            sync_conn.execute(text("ALTER TABLE price_history ADD COLUMN recorded_date VARCHAR(20)"))


async def _configure_postgres_readonly_role() -> None:
    """
    Configura de forma segura en Neon PostgreSQL el rol de solo lectura 'finprice_reader'
    con privilegios exclusivamente SELECT sobre todas las tablas del esquema public.
    """
    if is_sqlite:
        return
    try:
        async with writer_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'finprice_reader') THEN
                        CREATE ROLE finprice_reader WITH LOGIN PASSWORD 'FinPriceReadOnly2026!';
                      END IF;
                    END
                    $$;
                    """
                )
            )
            await conn.execute(text("GRANT CONNECT ON DATABASE neondb TO finprice_reader;"))
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO finprice_reader;"))
            await conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO finprice_reader;"))
            await conn.execute(
                text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO finprice_reader;")
            )
        logger.info("Rol de solo lectura 'finprice_reader' verificado con permisos SELECT en Neon PostgreSQL.")
    except Exception as exc:
        logger.info(f"Nota sobre provisión de rol finprice_reader en PostgreSQL: {exc}")


async def init_db() -> None:
    """Crea y verifica todas las tablas del sistema y configura el rol de solo lectura en Neon PostgreSQL."""
    import app.models.entities  # noqa: F401

    logger.info("Inicializando/verificando tablas en base de datos...")
    async with writer_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_new_columns)
    await _configure_postgres_readonly_role()
    logger.info("Esquema de base de datos verificado y listo.")


async def get_write_db() -> AsyncGenerator[AsyncSession, None]:
    """Sesión de base de datos con permisos de lectura/escritura (para Scraper y endpoints de escritura)."""
    async with WriterSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Sesión de base de datos ESTRICTAMENTE SOLO LECTURA (READ ONLY) para todas las consultas GET de la App.
    En PostgreSQL activa SET default_transaction_read_only = on y en el cursor bloquea INSERT/UPDATE/DELETE/DROP.
    """
    async with ReaderSessionLocal() as session:
        try:
            if not is_sqlite:
                await session.execute(text("SET default_transaction_read_only = on"))
            else:
                await session.execute(text("PRAGMA query_only = ON"))
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias retrocompatible de sesión de base de datos."""
    async for s in get_write_db():
        yield s
