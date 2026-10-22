"""
Endpoint administrativo para sincronización manual de precios: POST /api/v1/collectors/sync
Protegido estrictamente con X-API-Key y Rate Limiting.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.security import check_write_rate_limit, verify_admin_api_key
from app.models.domain import SessionLocal, get_db
from app.models.schemas import SyncResponse
from app.collectors.registry import collector_registry
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/collectors", tags=["Administración & Sincronización"])


async def run_sync_in_background() -> None:
    """Función de soporte para BackgroundTasks con sesión de base de datos dedicada."""
    db = SessionLocal()
    try:
        await collector_registry.sync_all_stores(
            db=db,
            on_cache_invalidate=catalog_service.invalidate_cache,
        )
    finally:
        db.close()


@router.post(
    "/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar sincronización asíncrona de precios bajo demanda",
    dependencies=[Depends(verify_admin_api_key), Depends(check_write_rate_limit)],
)
async def trigger_collectors_sync(
    background_tasks: BackgroundTasks,
):
    """
    Inicia la recolección concurrente de precios en las 8 tiendas en segundo plano.
    Requiere la cabecera 'X-API-Key'. Devuelve HTTP 202 Accepted de inmediato sin bloquear.
    """
    background_tasks.add_task(run_sync_in_background)

    return SyncResponse(
        status="accepted",
        message="Sincronización multitienda iniciada en segundo plano con éxito.",
        triggered_at=datetime.now(timezone.utc).isoformat(),
    )
