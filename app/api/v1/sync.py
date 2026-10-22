"""
Endpoint administrativo para sincronización manual de precios: POST /api/v1/collectors/sync
Protegido estrictamente con X-API-Key y Rate Limiting.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.core.database import AsyncSessionLocal
from app.core.security import check_write_rate_limit, verify_admin_api_key
from app.collectors.orchestrator import orchestrator
from app.models.schemas import SyncResponse
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/collectors", tags=["Administración & Sincronización"])


async def run_sync_in_background() -> None:
    """Ejecuta la sincronización en vivo con una sesión asíncrona dedicada."""
    async with AsyncSessionLocal() as session:
        try:
            await orchestrator.sync_all_catalog_products(
                session=session,
                on_cache_invalidate=catalog_service.invalidate_cache,
            )
        except Exception:
            await session.rollback()
            raise


@router.post(
    "/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar sincronización asíncrona de precios en vivo bajo demanda",
    dependencies=[Depends(verify_admin_api_key), Depends(check_write_rate_limit)],
)
async def trigger_collectors_sync(
    background_tasks: BackgroundTasks,
):
    """
    Inicia la recolección concurrente de precios en vivo desde las tiendas en segundo plano.
    Requiere la cabecera 'X-API-Key'. Devuelve HTTP 202 Accepted sin bloquear.
    """
    background_tasks.add_task(run_sync_in_background)

    return SyncResponse(
        status="accepted",
        message="Sincronización multitienda en vivo iniciada en segundo plano con éxito.",
        triggered_at=datetime.now(timezone.utc).isoformat(),
    )
