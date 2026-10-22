"""
FinPrice API - Cloud Standalone Real Retail Service
======================================================
Punto de entrada FastAPI con scraping inicial real en lifespan, motor asíncrono,
middlewares de seguridad, logging estructurado JSON y retrocompatibilidad con GET /products.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db, init_db
from app.core.logging import get_logger
from app.core.security import check_read_rate_limit, sanitize_input_text
from app.collectors.orchestrator import orchestrator
from app.models.entities import ProductEntity
from app.models.schemas import ProductResponse
from app.services.catalog_service import catalog_service

logger = get_logger("entrypoint")

_background_task: Optional[asyncio.Task] = None


async def periodic_scraping_loop():
    """Bucle continuo en segundo plano para actualizar precios reales periódicamente."""
    interval = max(60, settings.COLLECTION_INTERVAL_MINUTES * 60)
    logger.info(f"Iniciando programador de recolección en background (intervalo: {settings.COLLECTION_INTERVAL_MINUTES} min)...")
    while True:
        try:
            await asyncio.sleep(interval)
            logger.info("Ejecutando ciclo periódico de scraping real en background...")
            async with AsyncSessionLocal() as session:
                await orchestrator.sync_all_catalog_products(
                    session=session,
                    on_cache_invalidate=catalog_service.invalidate_cache,
                )
        except asyncio.CancelledError:
            logger.info("Programador de recolección cancelado por apagado del servidor.")
            break
        except Exception as e:
            logger.error(f"Error imprevisto en recolección en background: {e}")
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestor del ciclo de vida de la aplicación:
    1. Inicializa las tablas asíncronas en SQLite / PostgreSQL.
    2. Si la base de datos está vacía, dispara la recolección real inicial de precios.
    3. Inicia la tarea de sincronización periódica en background.
    """
    global _background_task
    logger.info("Encendiendo FinPrice API Standalone Real Service...", extra={"env": settings.ENVIRONMENT})

    # 1. Crear tablas asíncronas
    await init_db()

    # 2. Verificar si hay productos en BD o recolectar en vivo
    async with AsyncSessionLocal() as session:
        count_q = await session.execute(select(func.count(ProductEntity.id)))
        count = count_q.scalar() or 0
        if count == 0:
            logger.info("Base de datos limpia detectada. Ejecutando recolección real en vivo inicial...")
            await orchestrator.sync_all_catalog_products(
                session=session,
                on_cache_invalidate=catalog_service.invalidate_cache,
            )
        else:
            logger.info(f"Base de datos operativa con {count} productos reales previamente persistidos.")

    # 3. Iniciar bucle de scraping en segundo plano
    _background_task = asyncio.create_task(periodic_scraping_loop())

    logger.info(f"FinPrice API en línea y lista en puerto {settings.PORT}.")

    yield

    # Apagado limpio
    logger.info("Deteniendo FinPrice API...")
    if _background_task and not _background_task.done():
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
    logger.info("FinPrice API apagada correctamente.")


# ==============================================================================
# INSTANCIA FASTAPI Y MIDDLEWARES
# ==============================================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Servicio Cloud Autónomo 100% Real para recolección de precios retail en el Perú (PEN).",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    """Inyecta cabeceras de seguridad y registra latencia estructurada."""
    start_time = time.time()
    response: Response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Process-Time"] = f"{latency_ms:.2f}ms"

    if request.method == "GET" and "/api/v1/products" in request.url.path:
        response.headers["Cache-Control"] = f"public, max-age={settings.CACHE_TTL_SECONDS}"

    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} ({latency_ms:.1f}ms)",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
        },
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Router modular
app.include_router(api_v1_router)


@app.get("/", tags=["Root"], summary="Estado general del servicio en la nube")
def root():
    return {
        "message": "FinPrice API está activa en la nube",
        "version": settings.VERSION,
        "status": "healthy",
    }


@app.get(
    "/products",
    response_model=List[ProductResponse],
    tags=["Retrocompatibilidad"],
    summary="Endpoint legado de productos (compatibilidad retroactiva)",
    dependencies=[Depends(check_read_rate_limit)],
)
async def legacy_get_products(
    search: Optional[str] = Query(None, max_length=80),
    session: AsyncSession = Depends(get_db),
):
    clean_search = sanitize_input_text(search, max_length=80)
    return await catalog_service.get_legacy_products(session=session, search=clean_search)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENVIRONMENT == "development"),
    )
