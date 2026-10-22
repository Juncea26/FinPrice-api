"""
Orquestador concurrente de recolectores para las 8 tiendas retail peruanas.
Maneja semáforos de concurrencia, recolección paralela resiliente y actualización de base de datos.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.data.seed_catalog import OFFICIAL_STORES, STORES_BY_ID
from app.models.domain import PriceHistoryModel, ProductModel, StorePriceModel, SyncLogModel
from app.collectors.base import BaseStoreCollector
from app.collectors.stores.curacao import CuracaoCollector
from app.collectors.stores.efe import EfeCollector
from app.collectors.stores.falabella import FalabellaCollector
from app.collectors.stores.hiraoka import HiraokaCollector
from app.collectors.stores.metro import MetroCollector
from app.collectors.stores.ripley import RipleyCollector
from app.collectors.stores.tottus import TottusCollector
from app.collectors.stores.wong import WongCollector

logger = get_logger("collectors.registry")

try:
    import h2  # noqa: F401
    HAS_HTTP2 = True
except ImportError:
    HAS_HTTP2 = False


class CollectorRegistry:
    """
    Registro y despachador de colectores multitienda con concurrencia controlada.
    """

    def __init__(self):
        self._collectors: Dict[str, BaseStoreCollector] = {
            "efe": EfeCollector(),
            "falabella": FalabellaCollector(),
            "ripley": RipleyCollector(),
            "curacao": CuracaoCollector(),
            "hiraoka": HiraokaCollector(),
            "tottus": TottusCollector(),
            "metro": MetroCollector(),
            "wong": WongCollector(),
        }
        self.last_sync_timestamp: Optional[str] = None
        self._is_syncing: bool = False

    def get_collector(self, store_id: str) -> Optional[BaseStoreCollector]:
        return self._collectors.get(store_id)

    def get_all_stores_status(self) -> List[Dict[str, Any]]:
        """Retorna el estado de las 8 tiendas incluyendo su Circuit Breaker."""
        result = []
        for store in OFFICIAL_STORES:
            s_id = store["id"]
            collector = self._collectors.get(s_id)
            circuit_state = collector.circuit_breaker.state.value if collector else "UNKNOWN"
            failure_count = collector.circuit_breaker.failure_count if collector else 0

            result.append({
                "id": s_id,
                "name": store["name"],
                "code": store["code"],
                "base_url": store["base_url"],
                "is_enabled": store["is_enabled"],
                "circuit_status": circuit_state,
                "consecutive_failures": failure_count,
            })
        return result

    async def sync_all_stores(
        self,
        db: Session,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la sincronización asíncrona de todas las tiendas y productos.
        Garantiza que ningún fallo externo interrumpa la API.
        """
        if self._is_syncing:
            logger.warning("Sincronización omitida: ya existe un proceso de sincronización en curso.")
            return {"status": "in_progress", "message": "Sincronización actualmente en ejecución."}

        self._is_syncing = True
        start_time = time.time()
        logger.info("Iniciando ciclo de recolección de precios multitienda...")

        semaphore = asyncio.Semaphore(settings.COLLECTOR_MAX_CONCURRENCY)
        updated_offers_count = 0
        failed_tasks_count = 0

        timeout_config = httpx.Timeout(
            connect=settings.COLLECTOR_TIMEOUT_CONNECT,
            read=settings.COLLECTOR_TIMEOUT_READ,
            write=10.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(timeout=timeout_config, http2=HAS_HTTP2) as http_client:
            # Obtener todos los productos y sus precios registrados en BD
            products = db.query(ProductModel).all()

            tasks = []
            for product in products:
                for store_price in product.store_prices:
                    collector = self._collectors.get(store_price.store_id)
                    if not collector:
                        continue

                    # Tarea encapsulada con semáforo
                    tasks.append(
                        self._sync_single_store_price(
                            semaphore=semaphore,
                            client=http_client,
                            collector=collector,
                            product_id=product.id,
                            product_title=product.title,
                            store_price=store_price,
                        )
                    )

            # Ejecución concurrente protegida con return_exceptions=True
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Procesar resultados en la base de datos
            for res in results:
                if isinstance(res, Exception):
                    failed_tasks_count += 1
                    logger.warning(f"Excepción en tarea de recolección: {res}")
                elif res and isinstance(res, dict) and res.get("updated"):
                    updated_offers_count += 1

            # Recalcular precios históricos de 'Hoy' para cada producto
            now_label = "Hoy"
            today_utc = datetime.now(timezone.utc)

            for product in products:
                if product.store_prices:
                    current_best = min(sp.price for sp in product.store_prices)
                    # Buscar o crear punto de hoy (day_offset = 0)
                    today_point = (
                        db.query(PriceHistoryModel)
                        .filter(
                            PriceHistoryModel.product_id == product.id,
                            PriceHistoryModel.day_offset == 0,
                        )
                        .first()
                    )
                    if today_point:
                        today_point.price = current_best
                        today_point.recorded_date = today_utc
                    else:
                        new_point = PriceHistoryModel(
                            product_id=product.id,
                            day_offset=0,
                            date_label=now_label,
                            price=current_best,
                            recorded_date=today_utc,
                        )
                        db.add(new_point)

            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error confirmando cambios de sincronización en BD: {e}")

        # Invalidar caché en memoria si se proporcionó callback
        if on_cache_invalidate:
            on_cache_invalidate()

        total_duration = time.time() - start_time
        self.last_sync_timestamp = datetime.now(timezone.utc).isoformat()
        self._is_syncing = False

        # Registrar log en base de datos
        try:
            log_entry = SyncLogModel(
                timestamp=datetime.now(timezone.utc),
                store_id="all",
                status="COMPLETED",
                products_updated=updated_offers_count,
                duration_ms=total_duration * 1000,
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            pass

        logger.info(
            f"Ciclo de recolección finalizado en {total_duration:.2f}s. Ofertas actualizadas: {updated_offers_count}, Errores/Omitidos: {failed_tasks_count}"
        )

        return {
            "status": "success",
            "updated_offers": updated_offers_count,
            "failed_or_skipped": failed_tasks_count,
            "duration_seconds": round(total_duration, 2),
            "timestamp": self.last_sync_timestamp,
        }

    async def _sync_single_store_price(
        self,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
        collector: BaseStoreCollector,
        product_id: str,
        product_title: str,
        store_price: StorePriceModel,
    ) -> Dict[str, Any]:
        """Ejecuta la recolección para un producto y tienda con control de semáforo."""
        async with semaphore:
            scraped = await collector.collect(
                client=client,
                product_id=product_id,
                product_title=product_title,
                offer_url=store_price.offer_url,
                fallback_price=store_price.price,
            )

            if scraped and scraped.get("price"):
                new_price = scraped["price"]
                orig_price = scraped.get("original_price")
                # Solo actualizar si el precio cambió o para refrescar last_checked
                store_price.price = new_price
                if orig_price:
                    store_price.original_price = orig_price
                store_price.last_checked = datetime.now(timezone.utc)
                return {"updated": True, "product_id": product_id, "store_id": collector.store_id}

            return {"updated": False, "product_id": product_id, "store_id": collector.store_id}


collector_registry = CollectorRegistry()
