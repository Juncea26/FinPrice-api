"""
Job asíncrono en segundo plano para recolectar precios periódicamente (cada COLLECTION_INTERVAL_MINUTES).
"""
import asyncio
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.domain import SessionLocal
from app.collectors.registry import collector_registry
from app.services.catalog_service import catalog_service

logger = get_logger("services.scheduler")

_scheduler_task: Optional[asyncio.Task] = None


async def run_periodic_price_collection() -> None:
    """
    Bucle asíncrono continuo que ejecuta la recolección periódica.
    Diseñado para correr durante todo el ciclo de vida (lifespan) de la aplicación.
    """
    interval_seconds = max(60, settings.COLLECTION_INTERVAL_MINUTES * 60)
    logger.info(
        f"Scheduler en segundo plano activado. Intervalo: {settings.COLLECTION_INTERVAL_MINUTES} min ({interval_seconds}s)."
    )

    while True:
        try:
            # Esperar el intervalo configurado
            await asyncio.sleep(interval_seconds)
            logger.info("Iniciando recolección periódica programada de precios retail...")

            # Abrir sesión dedicada para el job en segundo plano
            db = SessionLocal()
            try:
                await collector_registry.sync_all_stores(
                    db=db,
                    on_cache_invalidate=catalog_service.invalidate_cache,
                )
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("Scheduler de precios cancelado por apagado del servidor.")
            break
        except Exception as e:
            logger.error(
                f"Error imprevisto en ciclo del scheduler de precios (se mantendrá en ejecución): {e}"
            )
            # Pequeña pausa antes de reintentar si ocurrió error
            await asyncio.sleep(10)


def start_scheduler() -> Optional[asyncio.Task]:
    """Inicia la tarea del scheduler asíncrono si no está activa."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(run_periodic_price_collection())
        logger.info("Tarea de background scheduler iniciada exitosamente.")
    return _scheduler_task


async def stop_scheduler() -> None:
    """Detiene y cancela limpiamente la tarea del scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        logger.info("Deteniendo tarea de background scheduler...")
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
