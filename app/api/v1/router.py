"""
Router principal /api/v1 agregando módulos de productos, tiendas, comunidad, reclamos y sync.
Incluye diagnóstico de salud en tiempo real en GET /api/v1/health.
"""
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.community import router as community_router
from app.api.v1.complaints import router as complaints_router
from app.api.v1.filters import router as filters_router
from app.api.v1.image_proxy import router as image_proxy_router
from app.api.v1.products import categories_router, router as products_router
from app.api.v1.stores import router as stores_router
from app.api.v1.sync import router as sync_router
from app.core.config import settings
from app.core.database import (
    MAX_OVERFLOW,
    MAX_TOTAL_POOL_CONNECTIONS,
    POOL_SIZE,
    get_read_db,
    get_write_db,
)
from app.core.security import (
    IP_BLACKLIST,
    MAX_REQUESTS_PER_MINUTE_PER_IP,
    create_api_access_token,
    sanitize_input_text,
)
from app.collectors.orchestrator import SCHEDULE_WINDOWS_LABELS, orchestrator
from app.models.entities import ProductEntity
from app.models.schemas import HealthResponse, PriceDropNotificationSchema
from app.services.catalog_service import catalog_service

api_v1_router = APIRouter(prefix="/api/v1")

# Subrouters
api_v1_router.include_router(products_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(filters_router)
api_v1_router.include_router(stores_router)
api_v1_router.include_router(community_router)
api_v1_router.include_router(complaints_router)
api_v1_router.include_router(sync_router)
api_v1_router.include_router(image_proxy_router)

APP_START_TIME = time.time()


@api_v1_router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Diagnóstico"],
    summary="Diagnóstico integral de FinPrice API en la nube",
)
async def get_health_status(session: AsyncSession = Depends(get_read_db)):
    """
    Retorna el estado operativo integral:
    - Estado de la conexión a Neon PostgreSQL (SELECT 1)
    - Total de productos reales registrados
    - Total de tiendas y tiendas con Circuit Breaker operativo
    - Timestamp de la última recolección en vivo
    - Uptime del servidor
    """
    db_target = (
        "connected (Neon PostgreSQL)"
        if ("neon.tech" in settings.DATABASE_URL or "postgres" in settings.DATABASE_URL)
        else "connected"
    )
    db_status = db_target
    total_products = 0

    try:
        await session.execute(text("SELECT 1"))
        count_q = await session.execute(select(func.count(ProductEntity.id)))
        total_products = count_q.scalar() or 0
    except Exception as e:
        db_status = f"error: {str(e)}"

    stores_status_list = orchestrator.get_stores_status()
    total_stores = len(stores_status_list)
    active_stores = sum(
        1 for s in stores_status_list if s["is_enabled"] and s["circuit_status"] != "OPEN"
    )

    stores_status_dict: Dict[str, Any] = {
        s["id"]: {
            "name": s["name"],
            "circuit_status": s["circuit_status"],
            "consecutive_failures": s["consecutive_failures"],
            "is_enabled": s["is_enabled"],
        }
        for s in stores_status_list
    }

    uptime = time.time() - APP_START_TIME

    return HealthResponse(
        status="healthy" if db_status.startswith("connected") else "degraded",
        version=settings.VERSION,
        database=db_status,
        total_products=total_products,
        total_stores=total_stores,
        active_stores=active_stores,
        last_sync_timestamp=orchestrator.last_sync_timestamp,
        next_scheduled_update="00:59, 06:59, 12:59, 18:59 America/Lima",
        stores_status=stores_status_dict,
        uptime_seconds=round(uptime, 2),
    )


@api_v1_router.post(
    "/auth/token",
    tags=["Seguridad & Autenticación"],
    summary="Emite un Token firmado HMAC-SHA256 para la App Móvil Android",
)
async def issue_client_token(
    client_id: str = Query("finprice-android-app", max_length=80),
):
    """
    Genera un token firmado HMAC-SHA256 válido para autenticar peticiones en la capa API
    mediante `Authorization: Bearer <token>` o `X-FinPrice-Token: <token>`.
    """
    clean_client = sanitize_input_text(client_id, max_length=80) or "finprice-android-app"
    return create_api_access_token(client_id=clean_client, expires_in_seconds=86400 * 7)


@api_v1_router.get(
    "/security/architecture",
    tags=["Seguridad & Autenticación"],
    summary="Resumen en vivo de las 5 capas de seguridad y pool de conexiones",
)
async def get_security_architecture():
    """
    Documenta y expone en vivo la configuración activa de ciberseguridad y rendimiento:
    1. Rate Limiting por IP (50 peticiones/minuto por IP, ventana deslizante 60s).
    2. WAF + IP Blacklist + Anti-SQLi/XSS en memoria antes de tocar PostgreSQL.
    3. Autenticación por Token HMAC-SHA256 en la capa API.
    4. Separación de Base de Datos (Writer para Scraper vs Read-Only para App) + Pool 10 conexiones.
    5. Programador de 4 actualizaciones diarias (00:59, 06:59, 12:59, 18:59 America/Lima).
    """
    return {
        "rate_limiting": {
            "enabled": True,
            "max_requests_per_minute_per_ip": MAX_REQUESTS_PER_MINUTE_PER_IP,
            "window_seconds": 60,
            "exceeded_status_code": 429,
            "retry_after_seconds": 60,
        },
        "waf_and_blacklist": {
            "enabled": True,
            "blacklisted_ips_count": len(IP_BLACKLIST),
            "sample_blacklisted_ips": sorted(list(IP_BLACKLIST))[:10],
            "auto_ban_on_sqli_or_xss": True,
            "auto_ban_after_consecutive_rate_limit_violations": 5,
            "blocked_status_code": 403,
        },
        "token_authentication": {
            "enabled": True,
            "algorithm": "HMAC-SHA256",
            "token_endpoint": "/api/v1/auth/token",
            "accepted_headers": ["Authorization: Bearer <token>", "X-FinPrice-Token"],
        },
        "database_separation_and_pool": {
            "writer_session": "WriterSessionLocal (get_write_db) - SELECT, INSERT, UPDATE, DELETE (Scraper & Admin)",
            "reader_session": "ReaderSessionLocal (get_read_db) - Solo SELECT (default_transaction_read_only = on / finprice_reader)",
            "pool_size": POOL_SIZE,
            "max_overflow": MAX_OVERFLOW,
            "max_total_connections": MAX_TOTAL_POOL_CONNECTIONS,
        },
        "scheduled_updates": {
            "timezone": "America/Lima (UTC-5)",
            "daily_windows": SCHEDULE_WINDOWS_LABELS,
            "intraday_min_price_tracking": True,
        },
    }


@api_v1_router.post(
    "/cron/daily-update",
    tags=["Cron & Sincronización"],
    summary="Ejecuta la actualización programada de precios e historial (00:59, 06:59, 12:59, 18:59 America/Lima)",
)
@api_v1_router.get(
    "/cron/daily-update",
    tags=["Cron & Sincronización"],
    summary="Ejecuta la actualización programada de precios e historial (00:59, 06:59, 12:59, 18:59 America/Lima)",
)
async def trigger_daily_cron_update(session: AsyncSession = Depends(get_write_db)):
    """
    Endpoint invocado en las 4 ventanas diarias (00:59, 06:59, 12:59 y 18:59 America/Lima)
    para ejecutar run_scheduled_price_update() y devolver cuántos productos se actualizaron,
    cuántos bajaron de precio y cuántos días de historial tienen.
    """
    result = await orchestrator.run_scheduled_price_update(
        session=session,
        on_cache_invalidate=catalog_service.invalidate_cache,
    )
    if result.get("status") == "in_progress":
        prods_q = await session.execute(select(ProductEntity))
        all_prods = prods_q.scalars().all()
        return {
            "status": "in_progress",
            "updated_products": len(all_prods),
            "price_drops_count": sum(
                1 for p in all_prods if (getattr(p, "price_drop_amount", 0.0) or 0.0) > 0 or p.best_price < p.original_price
            ),
            "days_tracked": max((getattr(p, "days_tracked", 1) or 1 for p in all_prods), default=1),
        }
    return result


@api_v1_router.get(
    "/notifications/price-drops",
    response_model=List[PriceDropNotificationSchema],
    tags=["Notificaciones"],
    summary="Lista de productos que han bajado de precio para notificaciones de favoritos",
)
async def get_price_drops_notifications(
    product_ids: Optional[str] = Query(
        None,
        max_length=500,
        description="Lista opcional de product_id separados por coma (ej. favoritos del usuario)",
    ),
    session: AsyncSession = Depends(get_read_db),
):
    """
    Devuelve la lista de productos que han bajado de precio respecto a su precio anterior o regular,
    indicando product_id, product_title, old_price, new_price, drop_amount, store_name, product_url,
    image_url y timestamp.
    """
    return await catalog_service.get_price_drop_notifications(
        session=session,
        product_ids=product_ids,
    )
