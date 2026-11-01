"""
FinPrice API - Cloud Standalone Real Retail Service
======================================================
Punto de entrada FastAPI de alto rendimiento optimizado para Render (< 512 MB RAM):
1. Arranque instantáneo (< 2 segundos) no bloqueante con verificación de tablas en Neon PostgreSQL.
2. Si Neon está vacío, inyección de semilla oficial en < 50ms y scraping en segundo plano tras abrir puerto.
3. Endpoints ultraligeros GET y HEAD /ping para keep-alive de UptimeRobot sin tocar Neon.
4. Middlewares de seguridad, CORS y diagnóstico integral en /api/v1/health.
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
from app.core.seed_data import seed_database_fast, sync_and_upsert_catalog
from app.collectors.orchestrator import orchestrator
from app.models.entities import ProductEntity
from app.models.schemas import ProductResponse
from app.services.catalog_service import catalog_service

logger = get_logger("entrypoint")

_background_task: Optional[asyncio.Task] = None


async def periodic_scraping_loop():
    """Bucle continuo en segundo plano para actualizar precios periódicamente sin saturar la RAM."""
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
            logger.error(f"Error imprevisto en recolección periódica en background: {e}")
            await asyncio.sleep(15)


async def initial_background_scraping_job():
    """
    Tarea en segundo plano tras arranque inicial cuando la base de datos estaba vacía.
    Espera 5 segundos para que Uvicorn abra el puerto HTTP ($PORT) y Render valide el healthcheck,
    luego ejecuta la sincronización sin bloquear el inicio.
    """
    try:
        await asyncio.sleep(5)
        logger.info("Iniciando recolección inicial en background tras confirmación de puerto HTTP abierto...")
        async with AsyncSessionLocal() as session:
            await orchestrator.sync_all_catalog_products(
                session=session,
                on_cache_invalidate=catalog_service.invalidate_cache,
            )
        # Continuar con el ciclo periódico
        await periodic_scraping_loop()
    except asyncio.CancelledError:
        logger.info("Tarea de sincronización inicial en background cancelada.")
    except Exception as e:
        logger.error(f"Error en sincronización inicial en background: {e}")
        await periodic_scraping_loop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida de FastAPI optimizado para Render y Neon Serverless:
    1. Crea / verifica el esquema de tablas en Neon PostgreSQL (Base.metadata.create_all).
    2. Cuenta rápidamente los productos en Neon (SELECT COUNT(*)):
       - count > 0: arranque instantáneo (< 1 seg) sirviendo datos persistidos de Neon.
       - count == 0: inserta semilla de respaldo en < 50ms y programa scraping diferido en background.
    3. JAMÁS bloquea el arranque con tareas de red pesadas.
    """
    global _background_task
    logger.info("Encendiendo FinPrice API Standalone...", extra={"env": settings.ENVIRONMENT})

    # 1. Crear y verificar tablas en Neon PostgreSQL
    await init_db()

    # 2. Sincronización UPSERT instantánea (< 200 ms) en Neon PostgreSQL
    async with AsyncSessionLocal() as session:
        synced_count = await sync_and_upsert_catalog(session=session)
        catalog_service.invalidate_cache()

    logger.info(f"Catálogo oficial de FinPrice sincronizado ({synced_count} productos en Neon). Arranque instantáneo listo.")
    _background_task = asyncio.create_task(periodic_scraping_loop())

    logger.info(f"FinPrice API en línea y disponible en puerto {settings.PORT}.")
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


# ==============================================================================
# ENDPOINT ULTRA-LIGERO KEEP-ALIVE ANTI-SUSPENSIÓN (GET y HEAD /ping)
# ==============================================================================

@app.get(
    "/ping",
    tags=["Keep-Alive"],
    summary="Endpoint ultraligero anti-suspensión para UptimeRobot (< 1 ms)",
)
@app.head(
    "/ping",
    tags=["Keep-Alive"],
    include_in_schema=False,
)
def ping():
    """
    Responde en menos de 1 ms con 200 OK sin tocar base de datos ni disparar scraping.
    Mantiene vivo el contenedor de Render sin gastar cuota de cómputo en Neon Serverless.
    """
    return {"status": "alive", "service": "FinPrice-api"}


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

    # No saturar logs con pings de UptimeRobot
    if request.url.path != "/ping":
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Router modular /api/v1
app.include_router(api_v1_router)


@app.get("/", tags=["Root"], summary="Estado general del servicio en la nube")
def root():
    return {
        "message": "FinPrice API está activa en la nube",
        "version": settings.VERSION,
        "status": "healthy",
        "database": "Neon PostgreSQL (US East 2 - Ohio)",
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
