"""
Orquestador concurrente de recolección real de precios multitienda con Triple Candado de Integridad:
1. Candado 1: Validación de identidad de producto (validate_product_identity)
2. Candado 2: Parsers con aislamiento de DOM principal (.product-info-main)
3. Candado 3: Filtro estadístico anti-outliers de precio (validate_cross_store_prices)
   y protección de imagen oficial de alta resolución (select_best_canonical_image).
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.catalog_urls import CATALOG_PRODUCTS, STORES_INFO
from app.collectors.http_client import fetch_page
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.collectors.spec_extractor import (
    generate_product_features,
    merge_product_specs,
    normalize_brand,
)
from app.collectors.validators import (
    select_best_canonical_image,
    validate_cross_store_prices,
    validate_product_identity,
)
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


def get_parser_for_store(store_id: str) -> Optional[Callable[..., Optional[Dict[str, Any]]]]:
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

    async def scrape_store_url(
        self,
        store_id: str,
        url: str,
        canonical_title: Optional[str] = None,
        tech_specs: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Descarga, parsea y valida una URL real de tienda respetando el Circuit Breaker
        y el Candado 1 de Identidad de Producto.
        """
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

            is_search = "/catalogsearch/result" in url or "?q=" in url or "&q=" in url
            if is_search:
                data = parser(html, url, canonical_title=canonical_title)
            else:
                data = parser(html, url)

            if not data or not data.get("price") or data["price"] <= 0:
                if cb:
                    cb.record_failure("No se pudo extraer precio válido")
                return None

            # Registrar éxito de red/extracción en el Circuit Breaker
            if cb:
                cb.record_success()

            # CANDADO 1: Validar identidad estricta del producto antes de aceptar la oferta
            if canonical_title:
                scraped_title = str(data.get("title") or "").strip()
                scraped_url = str(data.get("offer_url") or url).strip()
                if not validate_product_identity(
                    canonical_title=canonical_title,
                    scraped_title=scraped_title,
                    scraped_url=scraped_url,
                    store_id=store_id,
                    tech_specs=tech_specs,
                ):
                    return None

            return data
        except Exception as e:
            if cb:
                cb.record_failure(e)
            logger.warning(f"Error procesando {url} ({store_id}): {e}")
            return None

    async def sanitize_database_offers(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, int]:
        """
        Rutina de saneamiento que se ejecuta en el arranque (lifespan) y durante sync:
        1. Elimina de la BD cualquier store_price que falle validate_product_identity o validate_cross_store_prices.
        2. Recalcula inmediatamente best_price, best_store_name, original_price, discount_percentage
           y available_stores_count.
        3. Limpia puntos contaminados en el historial de precios y protege la imagen oficial.
        """
        stmt = (
            select(ProductEntity)
            .options(
                selectinload(ProductEntity.store_offers),
                selectinload(ProductEntity.price_history),
            )
            .execution_options(populate_existing=True)
        )
        res = await session.execute(stmt)
        products = res.scalars().all()

        removed_offers_count = 0
        recalculated_products_count = 0

        for prod in products:
            tech_specs = json.loads(prod.tech_specs_json) if prod.tech_specs_json else {}
            current_offers = list(prod.store_offers)
            if not current_offers:
                continue

            # 1. Filtrar por Candado 1: Identidad de Producto (sobre URL y título canónico)
            identity_valid_offers: List[StoreOfferEntity] = []
            for off in current_offers:
                if validate_product_identity(
                    canonical_title=prod.title,
                    scraped_title="",
                    scraped_url=off.offer_url,
                    store_id=off.store_id,
                    tech_specs=tech_specs,
                ):
                    identity_valid_offers.append(off)
                else:
                    await session.delete(off)
                    removed_offers_count += 1

            # 2. Filtrar por Candado 3: Anti-Outliers de Precio Inter-Tienda
            clean_offers = validate_cross_store_prices(identity_valid_offers)
            clean_ids = {id(o) for o in clean_offers}
            for off in identity_valid_offers:
                if id(off) not in clean_ids:
                    await session.delete(off)
                    removed_offers_count += 1

            # 3. Recalcular métricas del producto si quedaron ofertas válidas
            if clean_offers:
                clean_offers.sort(key=lambda x: x.price)
                for idx, off in enumerate(clean_offers):
                    off.is_best_price = idx == 0

                best_offer = clean_offers[0]
                best_price = best_offer.price
                best_store = best_offer.store_name
                orig_price = best_offer.original_price or best_price
                if orig_price < best_price:
                    orig_price = best_price

                discount = (
                    round(((orig_price - best_price) / orig_price) * 100)
                    if orig_price > best_price
                    else 0
                )

                needs_update = (
                    prod.best_price != best_price
                    or prod.best_store_name != best_store
                    or prod.original_price != orig_price
                    or prod.discount_percentage != discount
                    or prod.available_stores_count != len(clean_offers)
                    or len(clean_offers) != len(current_offers)
                )

                prod.best_price = best_price
                prod.best_store_name = best_store
                prod.original_price = orig_price
                prod.discount_percentage = discount
                prod.available_stores_count = len(clean_offers)

                # Si la imagen del producto pertenecía a una tienda descartada, limpiarla o actualizarla
                valid_store_ids = {o.store_id.lower() for o in clean_offers}
                if prod.image_url:
                    img_lower = prod.image_url.lower()
                    for s_id, s_info in STORES_INFO.items():
                        domain_host = s_info["base_url"].replace("https://", "").replace("www.", "")
                        if domain_host in img_lower and s_id not in valid_store_ids:
                            prod.image_url = ""
                            break

                # Limpiar puntos de historial contaminados (outliers < 55% del best_price)
                valid_history_prices: List[float] = []
                for hp in list(prod.price_history):
                    if hp.price < (best_price * 0.55):
                        await session.delete(hp)
                    else:
                        if hp.day_offset == 0:
                            hp.price = best_price
                        valid_history_prices.append(hp.price)

                hist_min = min(valid_history_prices) if valid_history_prices else best_price
                prod.historical_min_price = hist_min
                prod.is_historical_min = best_price <= hist_min

                # Normalizar y enriquecer tech_specs, brand y features automáticamente
                normalized_specs = merge_product_specs(
                    specs_list=[tech_specs],
                    base_specs=tech_specs,
                    title=prod.title,
                )
                normalized_brand = normalized_specs.get("Marca") or normalize_brand(prod.brand, prod.title)
                existing_feats = json.loads(prod.features_json) if prod.features_json else []
                normalized_feats = generate_product_features(
                    soup=None,
                    tech_specs=normalized_specs,
                    title=prod.title,
                    existing_features=existing_feats,
                )
                prod.brand = normalized_brand
                prod.tech_specs_json = json.dumps(normalized_specs, ensure_ascii=False)
                prod.features_json = json.dumps(normalized_feats, ensure_ascii=False)

                if needs_update:
                    recalculated_products_count += 1

        await session.commit()
        if on_cache_invalidate:
            on_cache_invalidate()

        if removed_offers_count > 0 or recalculated_products_count > 0:
            logger.info(
                f"Saneamiento de BD completado: {removed_offers_count} ofertas intrusas/outliers eliminadas, "
                f"{recalculated_products_count} productos recalculados."
            )

        return {
            "removed_offers": removed_offers_count,
            "recalculated_products": recalculated_products_count,
        }

    async def sync_all_catalog_products(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la recolección en vivo de precios reales aplicando el Triple Candado de Integridad:
        1. Filtra cada oferta extraída con validate_product_identity.
        2. Filtra las ofertas del producto con validate_cross_store_prices.
        3. Protege la imagen oficial canónica con select_best_canonical_image.
        4. Ejecuta saneamiento integral de la base de datos.
        """
        if self._is_syncing:
            return {"status": "in_progress", "message": "Sincronización en ejecución."}

        self._is_syncing = True
        start_time = time.time()
        logger.info("Iniciando recolección REAL en vivo con Triple Candado de Integridad...")

        # Primero sanear cualquier oferta inválida existente en BD
        await self.sanitize_database_offers(session=session)

        total_offers_updated = 0

        for item in CATALOG_PRODUCTS:
            prod_id = item["id"]
            canonical_title = item["title"]
            tech_specs = item.get("tech_specs", {})
            store_urls: Dict[str, str] = item.get("store_urls", {})
            identity_verified_offers: List[Dict[str, Any]] = []

            # Scrapear concurrentemente las tiendas reales de este producto
            scrape_tasks = [
                self.scrape_store_url(
                    store_id=store_id,
                    url=url,
                    canonical_title=canonical_title,
                    tech_specs=tech_specs,
                )
                for store_id, url in store_urls.items()
            ]
            results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

            for store_id, res in zip(store_urls.keys(), results):
                if isinstance(res, dict) and res.get("price"):
                    identity_verified_offers.append({
                        "store_id": store_id,
                        "store_name": STORES_INFO[store_id]["name"],
                        "title": res.get("title", ""),
                        "price": res["price"],
                        "original_price": res.get("original_price"),
                        "offer_url": res["offer_url"],
                        "image_url": res.get("image_url"),
                        "brand": res.get("brand"),
                        "tech_specs": res.get("tech_specs") or {},
                        "features": res.get("features") or [],
                    })

            # CANDADO 3: Filtro estadístico anti-outliers de precio inter-tienda
            verified_offers = validate_cross_store_prices(identity_verified_offers)

            # Si no hubo respuesta en vivo (ej. falla de red temporal), buscar si ya existían ofertas previas válidas en BD
            if not verified_offers:
                existing_q = await session.execute(
                    select(ProductEntity).where(ProductEntity.id == prod_id)
                )
                existing_prod = existing_q.scalar_one_or_none()
                if existing_prod and existing_prod.store_offers:
                    logger.info(f"Conservando instantánea previa validada para '{prod_id}' ante error temporal de scraping.")
                    continue

            # Si se obtuvieron ofertas reales verificadas, actualizar base de datos
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

                # Protección de imagen oficial: solo de tiendas que aprobaron identidad y anti-outlier,
                # priorizando Hiraoka, Falabella o Ripley (imágenes de catálogo de alta resolución)
                real_image = select_best_canonical_image(verified_offers)

                # Fusión Multi-Tienda de especificaciones técnicas, marca y características (features)
                merged_specs = merge_product_specs(
                    specs_list=[o.get("tech_specs", {}) for o in verified_offers],
                    base_specs=tech_specs,
                    title=canonical_title,
                )
                merged_brand = (
                    merged_specs.get("Marca")
                    or normalize_brand(item.get("brand"), canonical_title)
                )
                scraped_feats: List[str] = []
                for o in verified_offers:
                    scraped_feats.extend(o.get("features") or [])
                scraped_feats.extend(item.get("features") or [])
                merged_features = generate_product_features(
                    soup=None,
                    tech_specs=merged_specs,
                    title=canonical_title,
                    existing_features=scraped_feats,
                )

                prod_q = await session.execute(
                    select(ProductEntity).where(ProductEntity.id == prod_id)
                )
                prod_entity = prod_q.scalar_one_or_none()

                if not prod_entity:
                    prod_entity = ProductEntity(
                        id=prod_id,
                        title=canonical_title,
                        category=item["category"],
                        brand=merged_brand,
                        best_price=best_price,
                        original_price=orig_price,
                        best_store_name=best_store,
                        discount_percentage=discount,
                        available_stores_count=available_count,
                        image_url=real_image,
                        description=item["description"],
                        features_json=json.dumps(merged_features, ensure_ascii=False),
                        tech_specs_json=json.dumps(merged_specs, ensure_ascii=False),
                        is_favorite=False,
                    )
                    session.add(prod_entity)
                else:
                    prod_entity.title = canonical_title
                    prod_entity.brand = merged_brand
                    prod_entity.best_price = best_price
                    prod_entity.original_price = orig_price
                    prod_entity.best_store_name = best_store
                    prod_entity.discount_percentage = discount
                    prod_entity.available_stores_count = available_count
                    prod_entity.features_json = json.dumps(merged_features, ensure_ascii=False)
                    prod_entity.tech_specs_json = json.dumps(merged_specs, ensure_ascii=False)
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

                # Recalcular mínimo histórico real desde los snapshots válidos guardados en BD
                all_hist_q = await session.execute(
                    select(PriceHistoryEntity.price).where(
                        PriceHistoryEntity.product_id == prod_id,
                        PriceHistoryEntity.price >= (best_price * 0.55),
                    )
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
            f"Sincronización en vivo finalizada en {total_duration:.2f}s. Ofertas reales verificadas: {total_offers_updated}"
        )

        return {
            "status": "success",
            "updated_offers": total_offers_updated,
            "duration_seconds": round(total_duration, 2),
            "timestamp": self.last_sync_timestamp,
        }


orchestrator = CollectorOrchestrator()
