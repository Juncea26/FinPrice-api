"""
FinPrice API - Cloud Standalone Entrypoint
======================================================
Punto de entrada FastAPI con gestión de ciclo de vida (lifespan), middlewares de seguridad,
rate limiting, logs estructurados JSON, router modular /api/v1 y retrocompatibilidad con /products.
"""
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import check_read_rate_limit, sanitize_input_text
from app.models.domain import SessionLocal, get_db, init_db
from app.models.schemas import ProductResponse
from app.services.catalog_service import catalog_service
from app.services.scheduler import start_scheduler, stop_scheduler

logger = get_logger("entrypoint")


# ==============================================================================
# 1. GESTIÓN DEL CICLO DE VIDA (LIFESPAN)
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicializa recursos al encender el servidor y los libera al apagar:
    - Crea esquema de base de datos si no existe
    - Inicializa el catálogo con datos semilla si la BD está vacía
    - Inicia el job asíncrono en segundo plano para recolección periódica
    """
    logger.info("Iniciando FinPrice API en la nube...", extra={"environment": settings.ENVIRONMENT})

    # Inicializar Base de Datos
    init_db()

    # Verificar y sembrar catálogo si está vacío
    db = SessionLocal()
    try:
        catalog_service.ensure_seed_data(db)
    finally:
        db.close()

    # Iniciar scheduler en background
    scheduler_task = start_scheduler()

    logger.info("FinPrice API lista para recibir peticiones.", extra={"port": settings.PORT})

    yield

    # Apagado ordenado
    logger.info("Apagando FinPrice API y cancelando tareas en segundo plano...")
    await stop_scheduler()
    logger.info("FinPrice API detenida correctamente.")


# ==============================================================================
# 2. INSTANCIA DE FASTAPI
# ==============================================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Servicio en la nube 100% autónomo para recolectar, normalizar, "
        "almacenar en caché y servir precios de retail peruanos en Soles (PEN)."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ==============================================================================
# 3. MIDDLEWARE DE SEGURIDAD Y LOGS ESTRUCTURADOS
# ==============================================================================

@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    """
    Inyecta cabeceras de seguridad HTTP de nivel producción,
    agrega Cache-Control a lecturas y registra métricas de latencia por petición.
    """
    start_time = time.time()
    response: Response = await call_next(request)
    process_time_ms = (time.time() - start_time) * 1000

    # Cabeceras de seguridad recomendadas por OWASP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"

    # Cache-Control: 60s en lecturas de catálogo bajo /api/v1/products
    if request.method == "GET" and "/api/v1/products" in request.url.path:
        response.headers["Cache-Control"] = f"public, max-age={settings.CACHE_TTL_SECONDS}"

    # Log estructurado
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} ({process_time_ms:.1f}ms)",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(process_time_ms, 2),
            "client_ip": client_ip,
        },
    )

    return response


# ==============================================================================
# 4. CONFIGURACIÓN CORS CONTROLADA
# ==============================================================================

allowed_origins = settings.ALLOWED_ORIGINS
if settings.is_production and allowed_origins == ["*"]:
    logger.warning("CORS: '*' configurado en entorno de producción. Recomendado restringir a dominios específicos.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ==============================================================================
# 5. ROUTERS Y ENDPOINTS
# ==============================================================================

# Incluir versión 1 de la API (/api/v1)
app.include_router(api_v1_router)


@app.get(
    "/",
    tags=["Root"],
    summary="Estado general y bienvenida de FinPrice API",
)
def root():
    """Endpoint raíz que confirma la actividad del microservicio en la nube."""
    return {
        "message": "FinPrice API está activa en la nube",
        "version": settings.VERSION,
        "status": "healthy",
    }


# ==============================================================================
# 6. RETROCOMPATIBILIDAD ESTRICTA (GET /products)
# ==============================================================================

@app.get(
    "/products",
    response_model=List[ProductResponse],
    tags=["Retrocompatibilidad"],
    summary="Endpoint legado de productos (compatibilidad retroactiva)",
    dependencies=[Depends(check_read_rate_limit)],
)
def legacy_get_products(
    search: Optional[str] = Query(None, max_length=80),
    db: Session = Depends(get_db),
):
    """
    Mantiene compatibilidad exacta con el endpoint anterior /products,
    alimentándose del mismo servicio unificado y base de datos.
    """
    clean_search = sanitize_input_text(search, max_length=80)
    return catalog_service.get_legacy_products(db=db, search=clean_search)


# ==============================================================================
# 7. EJECUCIÓN DIRECTA LOCAL
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENVIRONMENT == "development"),
    )
