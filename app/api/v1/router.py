"""
Router principal /api/v1 agregando módulos de productos, tiendas, comunidad y sync.
Incluye diagnóstico de salud en tiempo real en GET /api/v1/health.
"""
import time
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.community import router as community_router
from app.api.v1.filters import router as filters_router
from app.api.v1.products import router as products_router
from app.api.v1.stores import router as stores_router
from app.api.v1.sync import router as sync_router
from app.core.config import settings
from app.core.database import get_db
from app.collectors.orchestrator import orchestrator
from app.models.entities import ProductEntity
from app.models.schemas import HealthResponse

api_v1_router = APIRouter(prefix="/api/v1")

# Subrouters
api_v1_router.include_router(products_router)
api_v1_router.include_router(filters_router)
api_v1_router.include_router(stores_router)
api_v1_router.include_router(community_router)
api_v1_router.include_router(sync_router)

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
    - Estado de la conexión asíncrona a la base de datos
    - Total de productos reales registrados
    - Total de tiendas y tiendas con Circuit Breaker operativo
    - Timestamp de la última recolección en vivo
    - Uptime del servidor
    """
    db_status = "connected"
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
        status="healthy" if db_status == "connected" else "degraded",
        version=settings.VERSION,
        database=db_status,
        total_products=total_products,
        total_stores=total_stores,
        active_stores=active_stores,
        last_sync_timestamp=orchestrator.last_sync_timestamp,
        stores_status=stores_status_dict,
        uptime_seconds=round(uptime, 2),
    )
