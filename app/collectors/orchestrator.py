"""
Orquestador concurrente de recolección real de precios multitienda.
Scrapea en vivo desde falabella.com.pe, efe.com.pe, lacuracao.pe, hiraoka.com.pe y ripley.com.pe,
normaliza precios en PEN, extrae imágenes oficiales y persiste en la base de datos asíncrona.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.catalog_urls import CATALOG_PRODUCTS, STORES_INFO
from app.collectors.http_client import fetch_page
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.models.entities import (
    PriceHistoryEntity,
    ProductEntity,
    StoreOfferEntity,
)

logger = get_logger("collectors.orchestrator")


# ==============================================================================
# PATRÓN CIRCUIT BREAKER POR TIENDA
# ==============================================================================

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class StoreCircuitBreaker:
    def __init__(self, store_id: str):
        self.store_id = store_id
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        now = time.time()
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time >= settings.CIRCUIT_BREAKER_RECOVERY_SECONDS):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self, err: Any):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit Breaker para '{self.store_id}' activado (OPEN). Error: {err}")


# Mapa de Circuit Breakers por tienda
CIRCUIT_BREAKERS: Dict[str, StoreCircuitBreaker] = {
    s_id: StoreCircuitBreaker(s_id) for s_id in STORES_INFO
}


def get_parser_for_store(store_id: str) -> Optional[Callable[[str, str], Optional[Dict[str, Any]]]]:
    if store_id == "falabella":
        return parse_falabella
    elif store_id in {"efe", "curacao"}:
        return parse_conectaretail
    elif store_id == "ripley":
        return parse_ripley
    elif store_id == "hiraoka":
        return parse_hiraoka
    return None


class CollectorOrchestrator:
    def __init__(self):
        self.last_sync_timestamp: Optional[str] = None
        self._is_syncing: bool = False

    def get_stores_status(self) -> List[Dict[str, Any]]:
        """Retorna el estado de todas las tiendas oficiales y su Circuit Breaker."""
        result = []
        for s_id, info in STORES_INFO.items():
            cb = CIRCUIT_BREAKERS.get(s_id)
            result.append({
                "id": s_id,
                "name": info["name"],
                "code": info["code"],
                "base_url": info["base_url"],
                "is_enabled": True,
                "circuit_status": cb.state.value if cb else "CLOSED",
                "consecutive_failures": cb.failure_count if cb else 0,
            })
        return result

    async def scrape_store_url(self, store_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Descarga y parsea una URL real de tienda respetando el Circuit Breaker."""
        cb = CIRCUIT_BREAKERS.get(store_id)
        if cb and not cb.can_execute():
            logger.info(f"Omitiendo llamada a '{store_id}' (Circuit Breaker OPEN).")
            return None

        parser = get_parser_for_store(store_id)
        if not parser:
            return None

        try:
            html = await fetch_page(url)
            if not html:
                if cb:
                    cb.record_failure("Respuesta vacía o error HTTP")
                return None

            data = parser(html, url)
            if data and data.get("price") and data["price"] > 0:
                if cb:
                    cb.record_success()
                return data
            else:
                if cb:
                    cb.record_failure("No se pudo extraer precio")
                return None
        except Exception as e:
            if cb:
                cb.record_failure(e)
            logger.warning(f"Error procesando {url} ({store_id}): {e}")
            return None

    async def sync_all_catalog_products(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la recolección en vivo de precios reales, imágenes y descuentos.
        Persiste los datos reales en SQLite y actualiza el historial de precios.
        """
        if self._is_syncing:
            return {"status": "in_progress", "message": "Sincronización en ejecución."}

        self._is_syncing = True
        start_time = time.time()
        logger.info("Iniciando recolección REAL en vivo desde tiendas retail peruanas...")

        total_offers_updated = 0

        for item in CATALOG_PRODUCTS:
            prod_id = item["id"]
            store_urls: Dict[str, str] = item.get("store_urls", {})
            verified_offers: List[Dict[str, Any]] = []

            # Scrapear concurrentemente las tiendas reales de este producto
            scrape_tasks = [
                self.scrape_store_url(store_id, url)
                for store_id, url in store_urls.items()
            ]
            results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

            for store_id, res in zip(store_urls.keys(), results):
                if isinstance(res, dict) and res.get("price"):
                    verified_offers.append({
                        "store_id": store_id,
                        "store_name": STORES_INFO[store_id]["name"],
                        "price": res["price"],
                        "original_price": res.get("original_price"),
                        "offer_url": res["offer_url"],
                        "image_url": res.get("image_url"),
                    })

            # Si no hubo respuesta en vivo (ej. falla de red temporal), buscar si ya existían ofertas previas en BD
            if not verified_offers:
                existing_q = await session.execute(
                    select(ProductEntity).where(ProductEntity.id == prod_id)
                )
                existing_prod = existing_q.scalar_one_or_none()
                if existing_prod and existing_prod.store_offers:
                    logger.info(f"Conservando instantánea previa para '{prod_id}' ante error temporal de scraping.")
                    continue

            # Si se obtuvieron ofertas reales, actualizar base de datos
            if verified_offers:
                verified_offers.sort(key=lambda x: x["price"])
                best_offer = verified_offers[0]
                best_price = best_offer["price"]
                best_store = best_offer["store_name"]
                orig_price = best_offer.get("original_price") or best_price
                if orig_price < best_price:
                    orig_price = best_price

                discount = (
                    round(((orig_price - best_price) / orig_price) * 100)
                    if orig_price > best_price
                    else 0
                )
                available_count = len(verified_offers)

                # Seleccionar la mejor imagen oficial extraída
                real_image = next((o["image_url"] for o in verified_offers if o.get("image_url")), "")

                # Consultar si el producto ya existe en la base de datos
                prod_q = await session.execute(
                    select(ProductEntity).where(ProductEntity.id == prod_id)
                )
                prod_entity = prod_q.scalar_one_or_none()

                if not prod_entity:
                    prod_entity = ProductEntity(
                        id=prod_id,
                        title=item["title"],
                        category=item["category"],
                        brand=item["brand"],
                        best_price=best_price,
                        original_price=orig_price,
                        best_store_name=best_store,
                        discount_percentage=discount,
                        available_stores_count=available_count,
                        image_url=real_image,
                        description=item["description"],
                        features_json=json.dumps(item["features"], ensure_ascii=False),
                        tech_specs_json=json.dumps(item["tech_specs"], ensure_ascii=False),
                        is_favorite=False,
                    )
                    session.add(prod_entity)
                else:
                    prod_entity.best_price = best_price
                    prod_entity.original_price = orig_price
                    prod_entity.best_store_name = best_store
                    prod_entity.discount_percentage = discount
                    prod_entity.available_stores_count = available_count
                    if real_image:
                        prod_entity.image_url = real_image
                    prod_entity.updated_at = datetime.now(timezone.utc)

                # Eliminar ofertas previas para este producto e insertar las ofertas verificadas actuales
                await session.execute(
                    delete(StoreOfferEntity).where(StoreOfferEntity.product_id == prod_id)
                )
                for idx, off in enumerate(verified_offers):
                    store_entity = StoreOfferEntity(
                        product_id=prod_id,
                        store_id=off["store_id"],
                        store_name=off["store_name"],
                        price=off["price"],
                        original_price=off.get("original_price"),
                        offer_url=off["offer_url"],
                        is_best_price=(idx == 0),
                        last_scraped_at=datetime.now(timezone.utc),
                    )
                    session.add(store_entity)
                    total_offers_updated += 1

                # Actualizar Historial Real (punto de 'Hoy', day_offset = 0)
                today_q = await session.execute(
                    select(PriceHistoryEntity).where(
                        PriceHistoryEntity.product_id == prod_id,
                        PriceHistoryEntity.day_offset == 0,
                    )
                )
                today_point = today_q.scalar_one_or_none()
                if today_point:
                    today_point.price = best_price
                    today_point.recorded_at = datetime.now(timezone.utc)
                else:
                    new_hist = PriceHistoryEntity(
                        product_id=prod_id,
                        day_offset=0,
                        date_label="Hoy",
                        price=best_price,
                        recorded_at=datetime.now(timezone.utc),
                    )
                    session.add(new_hist)

                # Recalcular mínimo histórico real desde los snapshots guardados en BD
                all_hist_q = await session.execute(
                    select(PriceHistoryEntity.price).where(PriceHistoryEntity.product_id == prod_id)
                )
                all_prices = all_hist_q.scalars().all()
                hist_min = min(all_prices) if all_prices else best_price
                prod_entity.historical_min_price = hist_min
                prod_entity.is_historical_min = best_price <= hist_min

        await session.commit()

        if on_cache_invalidate:
            on_cache_invalidate()

        total_duration = time.time() - start_time
        self.last_sync_timestamp = datetime.now(timezone.utc).isoformat()
        self._is_syncing = False

        logger.info(
            f"Sincronización en vivo finalizada en {total_duration:.2f}s. Ofertas reales actualizadas: {total_offers_updated}"
        )

        return {
            "status": "success",
            "updated_offers": total_offers_updated,
            "duration_seconds": round(total_duration, 2),
            "timestamp": self.last_sync_timestamp,
        }


orchestrator = CollectorOrchestrator()
