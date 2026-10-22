"""
Router principal de la API versión 1 (/api/v1), agregando módulos y diagnóstico /health.
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.admin_sync import router as admin_sync_router
from app.api.v1.community import router as community_router
from app.api.v1.products import router as products_router
from app.api.v1.stores import router as stores_router
from app.core.config import settings
from app.models.domain import ProductModel, get_db
from app.models.schemas import HealthResponse
from app.collectors.registry import collector_registry

api_v1_router = APIRouter(prefix="/api/v1")

# Incluir sub-routers
api_v1_router.include_router(products_router)
api_v1_router.include_router(stores_router)
api_v1_router.include_router(community_router)
api_v1_router.include_router(admin_sync_router)

# Registro de tiempo de inicio para métricas de uptime
APP_START_TIME = time.time()


@api_v1_router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Diagnóstico"],
    summary="Diagnóstico detallado del servicio en la nube",
)
def get_detailed_health(db: Session = Depends(get_db)):
    """
    Retorna el estado operativo integral de FinPrice API:
    - Conexión y conteos de base de datos
    - Total de tiendas y tiendas activas
    - Timestamp de última recolección exitosa
    - Estado de Circuit Breaker por tienda retail
    - Tiempo de actividad (uptime) en segundos
    """
    # Probar conexión a BD
    db_status = "connected"
    total_products = 0
    try:
        db.execute(text("SELECT 1"))
        total_products = db.query(ProductModel).count()
    except Exception as e:
        db_status = f"error: {str(e)}"

    stores_status_list = collector_registry.get_all_stores_status()
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
        last_sync_timestamp=collector_registry.last_sync_timestamp,
        stores_status=stores_status_dict,
        uptime_seconds=round(uptime, 2),
    )
