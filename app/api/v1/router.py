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
from app.api.v1.products import router as products_router
from app.api.v1.stores import router as stores_router
from app.api.v1.sync import router as sync_router
from app.core.config import settings
from app.core.database import get_db
from app.collectors.orchestrator import orchestrator
from app.models.entities import ProductEntity
from app.models.schemas import HealthResponse, PriceDropNotificationSchema
from app.services.catalog_service import catalog_service

api_v1_router = APIRouter(prefix="/api/v1")

# Subrouters
api_v1_router.include_router(products_router)
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
async def get_health_status(session: AsyncSession = Depends(get_db)):
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
        next_scheduled_update="00:59 America/Lima",
        stores_status=stores_status_dict,
        uptime_seconds=round(uptime, 2),
    )


@api_v1_router.post(
    "/cron/daily-update",
    tags=["Cron & Sincronización"],
    summary="Ejecuta la actualización diaria de precios e historial (00:59 AM America/Lima)",
)
@api_v1_router.get(
    "/cron/daily-update",
    tags=["Cron & Sincronización"],
    summary="Ejecuta la actualización diaria de precios e historial (00:59 AM America/Lima)",
)
async def trigger_daily_cron_update(session: AsyncSession = Depends(get_db)):
    """
    Endpoint invocado por GitHub Actions (.github/workflows/daily_cron_0059.yml) a las 00:59 AM (UTC-5)
    para despertar el contenedor de Render, ejecutar run_daily_price_update() y devolver cuántos
    productos se actualizaron, cuántos bajaron de precio y cuántos días de historial tienen.
    """
    result = await orchestrator.run_daily_price_update(
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
    session: AsyncSession = Depends(get_db),
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
