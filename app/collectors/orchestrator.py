"""
Orquestador concurrente de recolección real de precios multitienda con Triple Candado de Integridad:
1. Candado 1: Validación de identidad de producto (validate_product_identity)
2. Candado 2: Parsers con aislamiento de DOM principal (.product-info-main)
3. Candado 3: Filtro estadístico anti-outliers de precio (validate_cross_store_prices)
   y protección de imagen oficial de alta resolución (select_best_canonical_image).
"""
import asyncio
import gc
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.color_stripper import strip_color_tokens
from app.collectors.catalog_urls import (
    CATALOG_PRODUCTS,
    STORES_INFO,
    load_persisted_urls_from_db,
    register_verified_store_url,
)
from app.collectors.graph.smart_multi_graph import (
    ALL_8_PERU_STORES,
    FinPriceMultiStoreGraph,
    finprice_multi_store_graph,
)
from app.collectors.fingerprint_matcher import (
    ProductFingerprint,
    build_fingerprint_from_catalog_item,
    discover_product_across_8_stores,
    matches_fingerprint,
)
from app.collectors.http_client import (
    LAST_FETCH_STATUS,
    fetch_page,
    fetch_page as default_fetch_page,
    is_transient_fetch_failure,
)
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.collectors.parsers.tottus import parse_tottus
from app.collectors.parsers.vtex_cencosud import parse_vtex_cencosud
from app.collectors.spec_extractor import (
    generate_product_features,
    merge_product_specs,
    normalize_brand,
)
from app.collectors.url_utils import (
    build_store_search_url,
    build_vtex_api_url_for_product,
    canonicalize_store_url,
    is_marketplace_url,
)
from app.collectors.query_builder import build_search_queries, build_short_search_query
from app.collectors.universal_matcher import (
    extract_search_candidate_links,
    filter_offers_by_price_sanity,
    match_product_universal,
    normalize_product_signature,
    universal_resolver,
)
from app.collectors.validators import (
    check_is_in_stock,
    select_best_canonical_image,
    validate_cross_store_prices,
    validate_product_identity,
)
from app.models.entities import (
    PriceHistoryEntity,
    ProductEntity,
    StoreListing,
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
    def __init__(
        self,
        store_id: str,
        failure_threshold: Optional[int] = None,
        recovery_seconds: Optional[float] = None,
    ):
        self.store_id = store_id
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds

    @property
    def _effective_failure_threshold(self) -> int:
        if self.failure_threshold is not None:
            return max(1, int(self.failure_threshold))
        return max(3, int(settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD))

    @property
    def _effective_recovery_seconds(self) -> float:
        if self.recovery_seconds is not None:
            return max(1.0, float(self.recovery_seconds))
        return max(1.0, float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS))

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        now = time.time()
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time >= self._effective_recovery_seconds):
                self.state = CircuitState.HALF_OPEN
                logger.info(
                    f"Circuit Breaker para '{self.store_id}' pasó a HALF_OPEN tras cooldown "
                    f"({self._effective_recovery_seconds:.0f}s)."
                )
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self, err: Any):
        was_half_open = self.state == CircuitState.HALF_OPEN
        self.failure_count += 1
        self.last_failure_time = time.time()
        if was_half_open or self.failure_count >= self._effective_failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit Breaker para '{self.store_id}' activado (OPEN) "
                f"tras {self.failure_count} fallos consecutivos. Error: {err}"
            )


# Mapa de Circuit Breakers por tienda
CIRCUIT_BREAKERS: Dict[str, StoreCircuitBreaker] = {
    s_id: StoreCircuitBreaker(s_id) for s_id in STORES_INFO
}


def get_parser_for_store(store_id: str) -> Optional[Callable[..., Optional[Dict[str, Any]]]]:
    if store_id == "falabella":
        return parse_falabella
    elif store_id == "tottus":
        return parse_tottus
    elif store_id in {"efe", "curacao"}:
        return parse_conectaretail
    elif store_id == "ripley":
        return parse_ripley
    elif store_id == "hiraoka":
        return parse_hiraoka
    elif store_id in {"metro", "wong"}:
        return parse_vtex_cencosud
    return None


def utc_now() -> datetime:
    """Retorna fecha y hora actual en UTC sin tzinfo para compatibilidad con Neon PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


SPANISH_MONTHS_SHORT = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}

# 4 ventanas diarias de actualización programada en hora oficial de Perú (America/Lima, UTC-5)
SCHEDULE_WINDOWS = [(0, 59), (6, 59), (12, 59), (18, 59)]
SCHEDULE_WINDOWS_LABELS = ["00:59", "06:59", "12:59", "18:59"]


def calculate_seconds_until_next_window(
    tz_name: str = "America/Lima",
) -> Tuple[float, str]:
    """
    Calcula los segundos exactos restantes hasta el próximo corte programado
    entre las 4 ventanas diarias: 00:59, 06:59, 12:59 y 18:59 (America/Lima).
    Retorna (segundos_restantes, etiqueta_ventana).
    """
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    candidates = []
    for hour, minute in SCHEDULE_WINDOWS:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        candidates.append((candidate, f"{hour:02d}:{minute:02d}"))
    next_dt, label = min(candidates, key=lambda item: item[0])
    return max(1.0, (next_dt - now).total_seconds()), label


def get_today_peru() -> date:
    """Retorna siempre la fecha actual en zona horaria de Perú (America/Lima)."""
    return datetime.now(ZoneInfo("America/Lima")).date()


def get_now_peru() -> datetime:
    """Retorna la fecha y hora actual en zona horaria de Perú (America/Lima)."""
    return datetime.now(ZoneInfo("America/Lima"))


def get_latest_scheduled_cutoff_peru(now_peru: Optional[datetime] = None) -> datetime:
    """
    Retorna el instante exacto del último corte programado (00:59, 06:59, 12:59 o 18:59 America/Lima)
    que ya ocurrió respecto a now_peru.
    """
    tz = ZoneInfo("America/Lima")
    current = now_peru.astimezone(tz) if now_peru else datetime.now(tz)
    candidates = [
        current.replace(hour=h, minute=m, second=0, microsecond=0)
        for h, m in SCHEDULE_WINDOWS
    ]
    passed = [c for c in candidates if c <= current]
    if passed:
        return max(passed)
    yesterday = current - timedelta(days=1)
    return yesterday.replace(hour=18, minute=59, second=0, microsecond=0)


def format_peru_date_label(d: date) -> str:
    """Formatea una fecha como etiqueta calendario en español (ej. '09 Nov')."""
    return f"{d.day:02d} {SPANISH_MONTHS_SHORT.get(d.month, 'Nov')}"


def build_daily_history_points_for_product(
    best_price: float,
    original_price: float,
    today_peru: Optional[date] = None,
    existing_by_date: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Construye la serie histórica diaria de precios con CERO datos inventados o simulados:
    - PROHIBIDO inventar, simular o rellenar hacia atrás precios de días pasados.
    - Preserva únicamente filas de fechas ISO reales previas (si existieran de días anteriores reales)
      y registra para hoy (today_peru, day_offset = 0) una única fila con el menor precio observado en el día:
      daily_record.price = min(existing_today_price, best_price).
    """
    t_peru = today_peru or get_today_peru()
    t_iso = t_peru.isoformat()
    t_label = format_peru_date_label(t_peru)
    existing_map = dict(existing_by_date or {})

    points: List[Dict[str, Any]] = []
    min_allowed_date = t_peru - timedelta(days=29)

    # Preservar únicamente fechas ISO reales observadas previamente (sin rellenar fechas faltantes)
    real_past_dates: List[date] = []
    for k, val in existing_map.items():
        if not isinstance(k, str) or len(k) != 10:
            continue
        try:
            parsed_d = date.fromisoformat(k)
        except ValueError:
            continue
        if min_allowed_date <= parsed_d < t_peru and val and float(val) > 0:
            real_past_dates.append(parsed_d)

    for past_d in sorted(set(real_past_dates)):
        d_iso = past_d.isoformat()
        p_val = round(float(existing_map[d_iso]), 2)
        points.append(
            {
                "day_offset": (past_d - t_peru).days,
                "date_label": format_peru_date_label(past_d),
                "recorded_date": d_iso,
                "price": p_val,
            }
        )

    # Fila única de HOY (control de mínimo intradía: min(precio_existente_hoy, nuevo_best_price))
    today_price = round(float(best_price), 2)
    if t_iso in existing_map and existing_map[t_iso] and float(existing_map[t_iso]) > 0:
        today_price = round(min(float(existing_map[t_iso]), today_price), 2)

    points.append(
        {
            "day_offset": 0,
            "date_label": t_label,
            "recorded_date": t_iso,
            "price": today_price,
        }
    )

    return points


class CollectorOrchestrator:
    def __init__(self):
        self.last_sync_timestamp: Optional[str] = None
        self.last_sync_date: Optional[date] = None
        self._is_syncing: bool = False
        self.graph: FinPriceMultiStoreGraph = finprice_multi_store_graph

    async def run_multi_store_graph(
        self,
        target_product: Any,
        stores_to_check: Optional[List[str]] = None,
        enable_cascade_search: bool = True,
        enable_external_dork: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta el pipeline de grafo dirigido FinPriceMultiStoreGraph (5 nodos al estilo ScrapeGraphAI)
        para sincronizar un producto contra las 8 tiendas oficiales del Perú.
        """
        return await self.graph.run(
            target_product=target_product,
            stores_to_check=stores_to_check,
            enable_cascade_search=enable_cascade_search,
            enable_external_dork=enable_external_dork,
            fetch_fn=fetch_page,
        )

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
        fingerprint: Optional[ProductFingerprint] = None,
        target_product: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Descarga, parsea y valida una URL real de tienda respetando el Circuit Breaker,
        la canonicalización de URLs de las 8 tiendas, la resolución de variantes Multi-SKU
        y el Validador Universal sobre el Corpus Completo (match_product_universal).
        """
        cb = CIRCUIT_BREAKERS.get(store_id)
        if cb and not cb.can_execute():
            logger.info(f"Omitiendo llamada a '{store_id}' (Circuit Breaker OPEN).")
            return None

        parser = get_parser_for_store(store_id)
        if not parser:
            return None

        is_search = any(
            m in url
            for m in ("/catalogsearch/result", "/api/catalog_system/", "?q=", "&q=", "?ft=", "?s=")
        )
        target_url = url
        if not is_search:
            _, clean_u = canonicalize_store_url(url)
            target_url = clean_u or url

        try:
            html = None
            if store_id in {"metro", "wong"} and not is_search and "/api/catalog_system/" not in target_url:
                vtex_api_url = build_vtex_api_url_for_product(target_url)
                if vtex_api_url:
                    api_resp = await fetch_page(vtex_api_url)
                    if api_resp and api_resp.lstrip().startswith(("[", "{")) and len(api_resp.strip()) > 5:
                        html = api_resp
            if not html:
                html = await fetch_page(target_url)
            if not html:
                _, clean_t_url = canonicalize_store_url(target_url)
                last_st = LAST_FETCH_STATUS.get(target_url) or LAST_FETCH_STATUS.get(clean_t_url or "")
                if cb and last_st not in {"ok", "not_found"}:
                    cb.record_failure(f"Respuesta vacía o error HTTP ({last_st or 'unknown'})")
                return None

            if is_search:
                data = parser(html, target_url, canonical_title=canonical_title)
                # Si la grilla de búsqueda no tiene todos los atributos en el título de la tarjeta
                # (ej. Efe, Curacao, Hiraoka, Falabella o Tottus), inspeccionar las fichas de los primeros 5 candidatos
                if not data and canonical_title:
                    queries = build_search_queries(canonical_title, tech_specs)
                    broad_q = queries[-1] if queries else canonical_title
                    candidate_links = extract_search_candidate_links(
                        html=html,
                        search_url=target_url,
                        broad_model_query=broad_q,
                        limit=5,
                    )
                    for cand_link in candidate_links:
                        _, clean_cand_link = canonicalize_store_url(cand_link)
                        cand_html = await fetch_page(clean_cand_link or cand_link)
                        if not cand_html:
                            continue
                        cand_data = parser(
                            cand_html,
                            clean_cand_link or cand_link,
                            canonical_title=canonical_title,
                        )
                        if cand_data and cand_data.get("price") and float(cand_data["price"]) > 0:
                            effective_target = target_product or {
                                "title": canonical_title,
                                "tech_specs": tech_specs or {},
                            }
                            if match_product_universal(effective_target, cand_data):
                                data = cand_data
                                break
            elif store_id in {"falabella", "tottus"} and canonical_title:
                data = parser(html, target_url, canonical_title=canonical_title)
            else:
                data = parser(html, target_url)

            if not data or not data.get("price") or data["price"] <= 0:
                _, clean_t_url = canonicalize_store_url(target_url)
                last_st = LAST_FETCH_STATUS.get(target_url) or LAST_FETCH_STATUS.get(clean_t_url or "")
                if cb:
                    if last_st == "ok":
                        cb.record_success()
                    elif last_st is not None and last_st != "not_found":
                        cb.record_failure(f"Error de transporte HTTP ({last_st})")
                return None

            if data.get("in_stock") is False:
                if cb:
                    cb.record_success()
                return None

            # Registrar éxito de red/extracción en el Circuit Breaker
            if cb:
                cb.record_success()

            raw_offer_url = str(data.get("offer_url") or target_url).strip()
            _, clean_offer_url = canonicalize_store_url(raw_offer_url)
            data["offer_url"] = clean_offer_url or raw_offer_url
            scraped_title = str(data.get("title") or "").strip()

            # Validar con Validador Universal sobre Corpus Completo y Candado 1 de Identidad
            if canonical_title:
                effective_target = target_product or {
                    "title": canonical_title,
                    "tech_specs": tech_specs or {},
                }
                if not match_product_universal(effective_target, data):
                    return None
                if not validate_product_identity(
                    canonical_title=canonical_title,
                    scraped_title=scraped_title,
                    scraped_url=data["offer_url"],
                    store_id=store_id,
                    tech_specs=data.get("tech_specs") or tech_specs,
                    description=str(data.get("description") or ""),
                ):
                    return None

            if fingerprint is not None:
                if not matches_fingerprint(
                    fingerprint=fingerprint,
                    candidate_title=scraped_title,
                    candidate_specs=data.get("tech_specs") or tech_specs,
                    candidate_url=data["offer_url"],
                ):
                    return None

            return data
        except Exception as e:
            if cb:
                cb.record_failure(e)
            logger.warning(f"Error procesando {target_url} ({store_id}): {e}")
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

        catalog_map = {item["id"]: item for item in CATALOG_PRODUCTS}

        listing_canon_by_key: Dict[Tuple[str, str], Optional[str]] = {}
        listing_title_by_key: Dict[Tuple[str, str], str] = {}
        if any(str(p.id).startswith("auto_") for p in products):
            l_res = await session.execute(
                select(
                    StoreListing.store,
                    StoreListing.url,
                    StoreListing.title,
                    StoreListing.canonical_product_id,
                )
            )
            for l_store, l_url, l_title, l_canon in l_res.all():
                _, clean_lu = canonicalize_store_url(l_url or "")
                eff_lu = clean_lu or (l_url or "")
                l_key = (str(l_store or "").strip().lower(), eff_lu)
                listing_title_by_key[l_key] = str(l_title or "")
                listing_canon_by_key[l_key] = l_canon

        for prod in products:
            cat_item = catalog_map.get(prod.id)
            raw_canonical_title = cat_item["title"] if cat_item else prod.title
            clean_canonical_title = strip_color_tokens(raw_canonical_title)
            if prod.title != clean_canonical_title:
                prod.title = clean_canonical_title

            fingerprint = build_fingerprint_from_catalog_item(cat_item) if cat_item else None
            tech_specs = json.loads(prod.tech_specs_json) if prod.tech_specs_json else {}
            current_offers = list(prod.store_offers)
            if not current_offers:
                continue

            is_auto_prod = str(prod.id).startswith("auto_")

            # 1. Filtrar por Candado 1: Identidad de Producto + Huella Técnica + Canonicalización de URL + Cero Marketplace
            identity_valid_offers: List[StoreOfferEntity] = []
            for off in current_offers:
                _, clean_u = canonicalize_store_url(off.offer_url)
                if clean_u and clean_u != off.offer_url:
                    off.offer_url = clean_u

                if is_marketplace_url(off.store_id, off.offer_url):
                    await session.delete(off)
                    removed_offers_count += 1
                    continue

                lookup_key = (str(off.store_id or "").strip().lower(), clean_u or off.offer_url)
                scraped_title_hint = listing_title_by_key.get(lookup_key, "")
                linked_canon_id = listing_canon_by_key.get(lookup_key)

                if is_auto_prod and (linked_canon_id == prod.id or bool(scraped_title_hint)):
                    is_valid_id = True
                else:
                    is_valid_id = validate_product_identity(
                        canonical_title=prod.title,
                        scraped_title=scraped_title_hint,
                        scraped_url=off.offer_url,
                        store_id=off.store_id,
                        target_tech_specs=tech_specs,
                    )
                if is_valid_id:
                    if off.price and float(off.price) > 0:
                        identity_valid_offers.append(off)
                else:
                    await session.delete(off)
                    removed_offers_count += 1

            # 2. Filtrar por Candado 3: Anti-Outliers de Precio Inter-Tienda (solo ofertas en stock con price > 0)
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
                prod.best_store_url = best_offer.offer_url
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
                sorted_hist = sorted(list(prod.price_history), key=lambda h: h.day_offset)
                for hp in sorted_hist:
                    if hp.price < (best_price * 0.55):
                        await session.delete(hp)
                    else:
                        if hp.day_offset == 0:
                            hp.price = best_price
                        valid_history_prices.append(hp.price)

                hist_min = min(valid_history_prices + [best_price]) if valid_history_prices else best_price
                prod.historical_min_price = hist_min
                prod.is_historical_min = best_price <= hist_min
                prod.days_tracked = max(1, len(valid_history_prices))
                prev_p = valid_history_prices[-2] if len(valid_history_prices) >= 2 else orig_price
                prod.previous_best_price = prev_p
                prod.price_drop_amount = round(max(0.0, float(prev_p) - float(best_price)), 2)

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

    async def _sync_all_products_history_and_min_price(
        self,
        session: AsyncSession,
        today_peru: Optional[date] = None,
    ) -> None:
        """
        Módulo 4.3: Bucle Independiente de Historial y Precio Mínimo en Cada Corte.
        Recorre TODOS los 25 productos de la tabla `products` de manera 100% independiente:
        - Recalcula best_price = min(o.price for o in active_offers), best_store_name, best_store_url
          y available_stores_count = len(active_offers).
        - Hace UPSERT en price_history para la fecha actual today_peru guardando
          min(precio_guardado_hoy, product.best_price) (sin inventar jamás fechas pasadas).
        - Actualiza product.historical_min_price = min(product.historical_min_price, product.best_price)
          y product.is_historical_min = (product.best_price <= product.historical_min_price).
        """
        t_peru = today_peru or get_today_peru()
        t_iso = t_peru.isoformat()
        t_label = format_peru_date_label(t_peru)
        min_allowed_date = t_peru - timedelta(days=29)

        stmt = (
            select(ProductEntity)
            .options(
                selectinload(ProductEntity.store_offers),
                selectinload(ProductEntity.price_history),
            )
            .execution_options(populate_existing=True)
        )
        res = await session.execute(stmt)
        all_products = res.scalars().all()

        for product in all_products:
            active_offers = [
                o
                for o in product.store_offers
                if o.price and float(o.price) > 0 and getattr(o, "in_stock", True) is not False
            ]
            if active_offers:
                active_offers.sort(key=lambda o: float(o.price))
                for idx, off in enumerate(active_offers):
                    off.is_best_price = idx == 0
                best_offer = active_offers[0]
                best_price = round(float(best_offer.price), 2)
                orig_price = round(float(best_offer.original_price or best_price), 2)
                if orig_price < best_price:
                    orig_price = best_price
                discount = (
                    round(((orig_price - best_price) / orig_price) * 100)
                    if orig_price > best_price
                    else 0
                )
                product.best_price = best_price
                product.best_store_name = best_offer.store_name
                product.best_store_url = best_offer.offer_url
                product.original_price = orig_price
                product.discount_percentage = discount
                product.available_stores_count = len(active_offers)
            else:
                best_price = round(float(product.best_price or 0.0), 2)
                orig_price = round(float(product.original_price or best_price), 2)

            if best_price <= 0:
                continue

            # Actualizar day_offset de días reales previos y hacer UPSERT para today_peru
            today_row: Optional[PriceHistoryEntity] = None
            valid_hist_rows: List[PriceHistoryEntity] = []
            for h_row in list(product.price_history):
                r_date_str = str(getattr(h_row, "recorded_date", "") or "").strip()
                parsed_d: Optional[date] = None
                if len(r_date_str) == 10:
                    try:
                        parsed_d = date.fromisoformat(r_date_str)
                    except ValueError:
                        parsed_d = None

                if parsed_d == t_peru or (parsed_d is None and h_row.day_offset == 0):
                    if today_row is None:
                        today_row = h_row
                    else:
                        today_row.price = round(min(float(today_row.price), float(h_row.price)), 2)
                        await session.delete(h_row)
                elif parsed_d is not None and min_allowed_date <= parsed_d < t_peru and float(h_row.price or 0) > 0:
                    h_row.day_offset = (parsed_d - t_peru).days
                    h_row.date_label = format_peru_date_label(parsed_d)
                    valid_hist_rows.append(h_row)
                else:
                    await session.delete(h_row)

            if today_row is not None:
                today_row.price = round(min(float(today_row.price), best_price), 2)
                today_row.day_offset = 0
                today_row.date_label = t_label
                today_row.recorded_date = t_iso
                today_row.recorded_at = utc_now()
                valid_hist_rows.append(today_row)
            else:
                today_row = PriceHistoryEntity(
                    product_id=product.id,
                    day_offset=0,
                    date_label=t_label,
                    recorded_date=t_iso,
                    price=best_price,
                    recorded_at=utc_now(),
                )
                session.add(today_row)
                valid_hist_rows.append(today_row)

            valid_hist_rows.sort(key=lambda r: r.day_offset)
            all_observed_prices = [float(r.price) for r in valid_hist_rows if r.price and float(r.price) > 0] + [best_price]
            current_hist_min = (
                float(product.historical_min_price)
                if product.historical_min_price and float(product.historical_min_price) > 0
                else best_price
            )
            new_hist_min = round(min(all_observed_prices + [current_hist_min]), 2)
            product.historical_min_price = new_hist_min
            product.is_historical_min = bool(best_price <= new_hist_min)
            product.days_tracked = max(1, len(valid_hist_rows))
            prev_p = float(valid_hist_rows[-2].price) if len(valid_hist_rows) >= 2 else orig_price
            product.previous_best_price = round(prev_p, 2)
            product.price_drop_amount = round(max(0.0, prev_p - best_price), 2)

    async def discover_missing_stores_for_catalog(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Módulo 1.3: Barrido Automático de Tiendas Faltantes (discover_missing_stores_for_catalog).
        Recorre los 25 productos actuales en Neon PostgreSQL y, para cada producto, consulta
        las 8 tiendas oficiales usando build_short_search_query(product) y normalize_product_signature,
        agregando automáticamente en store_offers todas las tiendas oficiales 1P donde el producto
        realmente exista y tenga stock hoy.
        """
        return await self.sync_all_catalog_products(
            session=session,
            on_cache_invalidate=on_cache_invalidate,
            discover_missing_stores=True,
        )

    @staticmethod
    def _is_explicit_out_of_stock_document(store_id: str, content: str) -> bool:
        """
        Determina si una respuesta HTTP 200 OK contiene evidencia explícita de producto agotado
        (sin confundirlo con errores de red, WAF 403/429/5xx o carcasas HTML vacías).
        """
        if not content or not content.strip():
            return False

        s_id = (store_id or "").lower().strip()
        raw_low = content.lower()

        if not check_is_in_stock(s_id, content, status_code=200, has_valid_price=True):
            return True

        if s_id in {"efe", "curacao", "hiraoka"}:
            has_cart = any(
                m in raw_low
                for m in ("agregar al carrito", "añadir al carro", "anadir al carro", "product-addtocart-button")
            )
            if not has_cart and (
                "stock unavailable" in raw_low
                or "no está disponible" in raw_low
                or "no esta disponible" in raw_low
            ):
                return True

        if s_id == "ripley":
            if (
                '"isoutofstock":true' in raw_low.replace(" ", "")
                or '"buyable":false' in raw_low.replace(" ", "")
                or "schema.org/outofstock" in raw_low
                or "schema.org/soldout" in raw_low
                or ("out-of-stock" in raw_low and "add-to-cart" not in raw_low)
            ):
                return True

        if s_id in {"metro", "wong"} and content.lstrip().startswith("["):
            try:
                items = json.loads(content)
                if isinstance(items, list):
                    if len(items) == 0:
                        return True
                    any_avail = False
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        for sku in item.get("items") or []:
                            if not isinstance(sku, dict):
                                continue
                            for seller in sku.get("sellers") or []:
                                if not isinstance(seller, dict):
                                    continue
                                if str(seller.get("sellerId") or "1").strip() != "1":
                                    continue
                                co = seller.get("commertialOffer") or {}
                                qty = int(co.get("AvailableQuantity") or 0)
                                is_av = co.get("IsAvailable", qty > 0)
                                if qty > 0 and is_av:
                                    any_avail = True
                    if not any_avail:
                        return True
            except Exception:
                pass

        return False

    async def sync_all_catalog_products(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
        discover_missing_stores: bool = False,
        only_stores: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la recolección en vivo de precios reales aplicando:
        1. Algoritmo general de descubrimiento y emparejamiento multi-tienda (Módulo 1).
        2. Extractor en vivo de precios reales por motor de tienda (Módulo 2).
        3. Política general anti-borrado de tiendas ante fallos de red/WAF mediante UPSERT granular por (product_id, store_id).
        4. Bucle independiente de historial y precio mínimo sobre los 25 productos (Módulo 4).
        """
        if self._is_syncing:
            return {"status": "in_progress", "message": "Sincronización en ejecución."}

        allowed_stores_set: Optional[set] = None
        if only_stores is not None:
            allowed_stores_set = {
                s.strip().lower()
                for s in only_stores
                if isinstance(s, str) and s.strip().lower() in STORES_INFO
            }

        self._is_syncing = True
        start_time = time.time()
        store_stats: Dict[str, Dict[str, int]] = {
            s_id: {"ok_200": 0, "retained_error": 0, "out_of_stock": 0}
            for s_id in ALL_8_PERU_STORES
        }
        try:
            for cb in CIRCUIT_BREAKERS.values():
                cb.record_success()

            is_real_live_network = (fetch_page is default_fetch_page)
            enable_discovery = discover_missing_stores or is_real_live_network
            if allowed_stores_set is not None:
                logger.info(
                    f"Iniciando recolección REAL en vivo (discover_missing_stores={enable_discovery}, "
                    f"only_stores={sorted(allowed_stores_set)})..."
                )
            else:
                logger.info(
                    f"Iniciando recolección REAL en vivo (discover_missing_stores={enable_discovery})..."
                )

            # Primero sanear cualquier oferta inválida existente en BD y poblar caché de URLs verificadas
            await self.sanitize_database_offers(session=session)
            await load_persisted_urls_from_db(session=session)

            seed_urls_by_prod: Dict[str, Dict[str, str]] = {}
            if is_real_live_network:
                try:
                    from app.core.seed_data import SEED_STORE_OFFERS
                    for so in SEED_STORE_OFFERS:
                        pid_s = so.get("product_id")
                        sid_s = so.get("store_id")
                        url_s = so.get("offer_url")
                        if pid_s and sid_s and url_s:
                            _, clean_s = canonicalize_store_url(url_s)
                            seed_urls_by_prod.setdefault(pid_s, {})[sid_s] = clean_s or url_s
                except Exception:
                    pass

            total_offers_updated = 0

            for item in CATALOG_PRODUCTS:
                prod_id = item["id"]
                canonical_title = strip_color_tokens(item["title"])
                tech_specs = item.get("tech_specs", {})
                store_urls: Dict[str, str] = dict(item.get("store_urls", {}))
                for s_seed, u_seed in seed_urls_by_prod.get(prod_id, {}).items():
                    if s_seed not in store_urls:
                        store_urls[s_seed] = u_seed

                # Cargar producto y ofertas previas de BD para aplicar UPSERT granular y Retención Tolerante a Fallos
                existing_q = await session.execute(
                    select(ProductEntity)
                    .options(
                        selectinload(ProductEntity.store_offers),
                        selectinload(ProductEntity.price_history),
                    )
                    .where(ProductEntity.id == prod_id)
                    .execution_options(populate_existing=True)
                )
                existing_prod = existing_q.scalar_one_or_none()
                existing_offers_by_store: Dict[str, StoreOfferEntity] = {}
                if existing_prod and existing_prod.store_offers:
                    for db_off in existing_prod.store_offers:
                        existing_offers_by_store[db_off.store_id] = db_off
                        if db_off.store_id not in store_urls and db_off.offer_url:
                            store_urls[db_off.store_id] = db_off.offer_url

                target_item = dict(item)
                if allowed_stores_set is None:
                    target_item["store_urls"] = store_urls
                    stores_to_query = (
                        list(ALL_8_PERU_STORES)
                        if enable_discovery
                        else list(store_urls.keys())
                    )
                else:
                    target_item["store_urls"] = {
                        k: v for k, v in store_urls.items() if k in allowed_stores_set
                    }
                    stores_to_query = (
                        [s for s in ALL_8_PERU_STORES if s in allowed_stores_set]
                        if enable_discovery
                        else [s for s in store_urls.keys() if s in allowed_stores_set]
                    )
                    if not stores_to_query:
                        stores_to_query = [s for s in ALL_8_PERU_STORES if s in allowed_stores_set]

                state = await self.graph.execute_state(
                    target_product=target_item,
                    stores_to_check=stores_to_query,
                    enable_cascade_search=enable_discovery,
                    fetch_fn=fetch_page,
                )

                for doc in state.fetched_documents:
                    if doc.content and doc.store_id in CIRCUIT_BREAKERS:
                        CIRCUIT_BREAKERS[doc.store_id].record_success()

                verified_offers = [
                    off.to_offer_dict()
                    for off in state.verified_offers
                    if off.in_stock and float(off.price or 0) > 0
                ]

                fetched_detail_urls = {
                    d.canonical_url
                    for d in state.fetched_documents
                    if not d.is_search_page
                }

                # Confirmar ficha en vivo solo para tiendas descubiertas directamente desde resultados de búsqueda sin ficha descargada
                if enable_discovery and verified_offers:
                    confirmed_offers: List[Dict[str, Any]] = []
                    for off in verified_offers:
                        s_id = off["store_id"]
                        off_url = off["offer_url"]
                        if (
                            s_id not in existing_offers_by_store
                            and s_id not in item.get("store_urls", {})
                            and s_id not in {"metro", "wong"}
                            and off_url not in fetched_detail_urls
                        ):
                            live_detail = await self.scrape_store_url(
                                store_id=s_id,
                                url=off_url,
                                canonical_title=canonical_title,
                                tech_specs=tech_specs,
                                target_product=target_item,
                            )
                            if live_detail and live_detail.get("price") and float(live_detail["price"]) > 0:
                                off["price"] = round(float(live_detail["price"]), 2)
                                off["original_price"] = round(
                                    float(live_detail.get("original_price") or live_detail["price"]), 2
                                )
                                off["offer_url"] = live_detail.get("offer_url") or off_url
                                if live_detail.get("image_url"):
                                    off["image_url"] = live_detail["image_url"]
                                confirmed_offers.append(off)
                            elif is_transient_fetch_failure(off_url):
                                confirmed_offers.append(off)
                        else:
                            confirmed_offers.append(off)
                    verified_offers = confirmed_offers

                verified_store_ids = {off["store_id"] for off in verified_offers}
                fetched_docs_by_store: Dict[str, List[Any]] = {}
                for doc in state.fetched_documents:
                    if not doc.is_search_page:
                        fetched_docs_by_store.setdefault(doc.store_id, []).append(doc)

                parsed_nodes_by_store: Dict[str, List[Any]] = {}
                for p_node in state.parsed_nodes:
                    if not p_node.is_search_page:
                        parsed_nodes_by_store.setdefault(p_node.store_id, []).append(p_node)

                extracted_by_store: Dict[str, List[Any]] = {}
                for ext_off in state.extracted_offers:
                    extracted_by_store.setdefault(ext_off.store_id, []).append(ext_off)

                # Si alguna tienda con URL directa devolvió 200 OK agotado en ese color, buscar otra variante en stock
                if enable_discovery:
                    fallback_search_stores: List[str] = []
                    for s_id in stores_to_query:
                        if s_id in verified_store_ids:
                            continue
                        docs_s = fetched_docs_by_store.get(s_id, [])
                        if docs_s and any(
                            self._is_explicit_out_of_stock_document(s_id, d.content)
                            for d in docs_s
                        ):
                            fallback_search_stores.append(s_id)
                        elif s_id in store_urls:
                            _, clean_su = canonicalize_store_url(store_urls[s_id])
                            st_val = LAST_FETCH_STATUS.get(store_urls[s_id]) or LAST_FETCH_STATUS.get(clean_su or "")
                            if st_val == "not_found":
                                fallback_search_stores.append(s_id)

                    if fallback_search_stores:
                        search_target = dict(item)
                        search_target["id"] = ""
                        search_target["store_urls"] = {}
                        fallback_state = await self.graph.execute_state(
                            target_product=search_target,
                            stores_to_check=fallback_search_stores,
                            enable_cascade_search=True,
                            fetch_fn=fetch_page,
                        )
                        for fb_off in fallback_state.verified_offers:
                            if fb_off.in_stock and float(fb_off.price or 0) > 0:
                                fb_dict = fb_off.to_offer_dict()
                                if fb_dict["store_id"] not in verified_store_ids:
                                    verified_offers.append(fb_dict)
                                    verified_store_ids.add(fb_dict["store_id"])

                # Contabilizar tiendas exitosas 200 OK
                for off in verified_offers:
                    s_id = off["store_id"]
                    if s_id in store_stats:
                        store_stats[s_id]["ok_200"] += 1

                # MÓDULO 3.1: POLÍTICA ANTI-BORRADO Y UPSERT GRANULAR POR (product_id, store_id)
                out_of_stock_stores: List[str] = []
                contaminated_stores_to_delete: List[str] = []
                retained_offers: List[Dict[str, Any]] = []

                for s_id, prev_off in existing_offers_by_store.items():
                    if s_id in verified_store_ids:
                        continue

                    if allowed_stores_set is not None and s_id not in allowed_stores_set:
                        if (
                            prev_off.price
                            and float(prev_off.price) > 0
                            and getattr(prev_off, "in_stock", True) is not False
                        ):
                            retained_offers.append(
                                {
                                    "store_id": prev_off.store_id,
                                    "store_name": prev_off.store_name,
                                    "title": canonical_title,
                                    "price": float(prev_off.price),
                                    "original_price": float(prev_off.original_price or prev_off.price),
                                    "offer_url": prev_off.offer_url,
                                    "image_url": existing_prod.image_url if existing_prod else None,
                                    "in_stock": True,
                                    "tech_specs": tech_specs,
                                    "features": item.get("features") or [],
                                    "_retained": True,
                                }
                            )
                        continue

                    prev_url = prev_off.offer_url
                    docs_s = fetched_docs_by_store.get(s_id, [])
                    ext_s = extracted_by_store.get(s_id, [])
                    parsed_s = parsed_nodes_by_store.get(s_id, [])

                    # 1. Error temporal explícito (timeout, 403, 429, 500, 502, 503, 504) o sin respuesta HTTP 200 OK
                    if is_transient_fetch_failure(prev_url) or not docs_s:
                        if prev_off.price and float(prev_off.price) > 0:
                            logger.warning(
                                f"[RETENCIÓN TOLERANTE A FALLOS] Conservando oferta de '{prev_off.store_name}' "
                                f"(S/ {prev_off.price:.2f}) para '{prod_id}' ante fallo temporal en {prev_url}."
                            )
                            retained_offers.append(
                                {
                                    "store_id": prev_off.store_id,
                                    "store_name": prev_off.store_name,
                                    "title": canonical_title,
                                    "price": float(prev_off.price),
                                    "original_price": float(prev_off.original_price or prev_off.price),
                                    "offer_url": prev_url,
                                    "image_url": existing_prod.image_url if existing_prod else None,
                                    "in_stock": True,
                                    "tech_specs": tech_specs,
                                    "features": item.get("features") or [],
                                    "_retained": True,
                                }
                            )
                            if s_id in store_stats:
                                store_stats[s_id]["retained_error"] += 1
                        continue

                    # 2. HTTP 200 OK recibido: distinguir entre agotado explícito, producto intruso o WAF/challenge 200
                    is_explicit_oos = any(e.in_stock is False for e in ext_s) or any(
                        self._is_explicit_out_of_stock_document(s_id, d.content)
                        for d in docs_s
                    )
                    if is_explicit_oos:
                        logger.info(
                            f"[SIN_STOCK_200] '{prev_off.store_name}' respondió 200 OK agotado para '{prod_id}' ({prev_url}). "
                            "Marcando in_stock=False sin eliminar fila."
                        )
                        out_of_stock_stores.append(s_id)
                        if s_id in store_stats:
                            store_stats[s_id]["out_of_stock"] += 1
                        continue

                    # Si se extrajo un producto distinto (falló Candado 1 o Candado 3) o H1 válido no coincide, limpiar intruso
                    has_wrong_product = bool(ext_s) or any(
                        bool(pn.h1_title)
                        and not any(
                            waf_kw in pn.h1_title.lower()
                            for waf_kw in ("access denied", "just a moment", "forbidden", "robot", "attention required")
                        )
                        and not validate_product_identity(
                            canonical_title=canonical_title,
                            scraped_title=pn.h1_title,
                            scraped_url=prev_url,
                            store_id=s_id,
                            tech_specs=pn.tech_specs or tech_specs,
                            description=pn.description,
                        )
                        for pn in parsed_s
                    )
                    if has_wrong_product:
                        logger.warning(
                            f"[IDENTITY_CLEANUP] Eliminando oferta no coincidente de '{prev_off.store_name}' en '{prod_id}' ({prev_url})."
                        )
                        contaminated_stores_to_delete.append(s_id)
                        continue

                    # Respuesta 200 OK ambigua (WAF/challenge/shell sin H1 ni texto de agotado): conservar oferta previa
                    if prev_off.price and float(prev_off.price) > 0:
                        logger.warning(
                            f"[RETENCIÓN 200 AMBIGUO] Conservando oferta de '{prev_off.store_name}' "
                            f"(S/ {prev_off.price:.2f}) para '{prod_id}' ante respuesta sin ficha completa."
                        )
                        retained_offers.append(
                            {
                                "store_id": prev_off.store_id,
                                "store_name": prev_off.store_name,
                                "title": canonical_title,
                                "price": float(prev_off.price),
                                "original_price": float(prev_off.original_price or prev_off.price),
                                "offer_url": prev_url,
                                "image_url": existing_prod.image_url if existing_prod else None,
                                "in_stock": True,
                                "tech_specs": tech_specs,
                                "features": item.get("features") or [],
                                "_retained": True,
                            }
                        )
                        if s_id in store_stats:
                            store_stats[s_id]["retained_error"] += 1

                # Combinar ofertas 200 OK en stock con ofertas conservadas por fallo temporal
                active_offers_combined = verified_offers + retained_offers

                # Aplicar filtro anti-outliers inter-tienda y ordenar de menor a mayor precio
                active_offers = validate_cross_store_prices(
                    filter_offers_by_price_sanity(active_offers_combined)
                )

                # Aplicar baja de stock / limpieza intrusa antes de continuar si no quedaron ofertas activas
                for s_id in out_of_stock_stores:
                    existing_row = existing_offers_by_store.get(s_id)
                    if existing_row is not None:
                        existing_row.price = 0.0
                        existing_row.is_best_price = False
                        existing_row.in_stock = False
                        existing_row.last_scraped_at = utc_now()

                for s_id in contaminated_stores_to_delete:
                    existing_row = existing_offers_by_store.get(s_id)
                    if existing_row is not None:
                        await session.delete(existing_row)

                if not active_offers:
                    if existing_prod and existing_prod.store_offers:
                        logger.warning(
                            f"Sin ofertas activas nuevas para '{prod_id}'; preservando historial y estado sin borrar tiendas por error temporal."
                        )
                    continue

                active_offers.sort(key=lambda x: float(x["price"]))
                best_offer = active_offers[0]
                best_price = round(float(best_offer["price"]), 2)
                best_store = best_offer["store_name"]
                orig_price = round(float(best_offer.get("original_price") or best_price), 2)
                if orig_price < best_price:
                    orig_price = best_price

                discount = (
                    round(((orig_price - best_price) / orig_price) * 100)
                    if orig_price > best_price
                    else 0
                )
                available_count = len(active_offers)

                real_image = select_best_canonical_image(active_offers)

                merged_specs = merge_product_specs(
                    specs_list=[o.get("tech_specs", {}) for o in active_offers],
                    base_specs=tech_specs,
                    title=canonical_title,
                )
                merged_brand = (
                    merged_specs.get("Marca")
                    or normalize_brand(item.get("brand"), canonical_title)
                )
                scraped_feats: List[str] = []
                for o in active_offers:
                    scraped_feats.extend(o.get("features") or [])
                scraped_feats.extend(item.get("features") or [])
                merged_features = generate_product_features(
                    soup=None,
                    tech_specs=merged_specs,
                    title=canonical_title,
                    existing_features=scraped_feats,
                )

                prod_entity = existing_prod
                best_url = best_offer["offer_url"]

                if not prod_entity:
                    prod_entity = ProductEntity(
                        id=prod_id,
                        title=canonical_title,
                        category=item["category"],
                        brand=merged_brand,
                        best_price=best_price,
                        original_price=orig_price,
                        best_store_name=best_store,
                        best_store_url=best_url,
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
                    prod_entity.best_store_url = best_url
                    prod_entity.discount_percentage = discount
                    prod_entity.available_stores_count = available_count
                    prod_entity.features_json = json.dumps(merged_features, ensure_ascii=False)
                    prod_entity.tech_specs_json = json.dumps(merged_specs, ensure_ascii=False)
                    if real_image:
                        prod_entity.image_url = real_image
                    prod_entity.updated_at = utc_now()

                # UPSERT granular en store_offers por (product_id, store_id)
                for idx, off in enumerate(active_offers):
                    s_id = off["store_id"]
                    register_verified_store_url(
                        product_id=prod_id,
                        store_id=s_id,
                        offer_url=off["offer_url"],
                    )
                    is_best = idx == 0
                    new_price = round(float(off["price"]), 2)
                    new_orig = round(float(off.get("original_price") or new_price), 2)
                    if new_orig < new_price:
                        new_orig = new_price

                    existing_row = existing_offers_by_store.get(s_id)
                    if existing_row is not None:
                        if not off.get("_retained"):
                            existing_row.store_name = off["store_name"]
                            existing_row.price = new_price
                            existing_row.original_price = new_orig
                            existing_row.offer_url = off["offer_url"]
                            existing_row.last_scraped_at = utc_now()
                            total_offers_updated += 1
                        existing_row.is_best_price = is_best
                        existing_row.in_stock = True
                    else:
                        store_entity = StoreOfferEntity(
                            product_id=prod_id,
                            store_id=s_id,
                            store_name=off["store_name"],
                            price=new_price,
                            original_price=new_orig,
                            offer_url=off["offer_url"],
                            is_best_price=is_best,
                            last_scraped_at=utc_now(),
                        )
                        store_entity.in_stock = True
                        session.add(store_entity)
                        total_offers_updated += 1

                del verified_offers
                del active_offers
                gc.collect()

            await session.flush()

            # MÓDULO 4.3: Ejecutar SIEMPRE al final un bucle independiente sobre TODOS los 25 productos
            # de la tabla `products` para hacer UPSERT en price_history de today_peru y actualizar historical_min_price.
            await self._sync_all_products_history_and_min_price(session=session)
            await session.commit()

            if on_cache_invalidate:
                on_cache_invalidate()

            total_duration = time.time() - start_time
            self.last_sync_timestamp = datetime.now(timezone.utc).isoformat()
            self.last_sync_date = get_today_peru()

            # Calcular resumen de productos actualizados, bajadas de precio y días de historial
            prods_summary_q = await session.execute(select(ProductEntity))
            all_prods_after = prods_summary_q.scalars().all()
            updated_products_count = len(all_prods_after)
            price_drops_count = sum(
                1 for p in all_prods_after if (getattr(p, "price_drop_amount", 0.0) or 0.0) > 0 or p.best_price < p.original_price
            )
            max_days_tracked = max((getattr(p, "days_tracked", 1) or 1 for p in all_prods_after), default=1)

            stores_to_report = (
                [s for s in ALL_8_PERU_STORES if s in allowed_stores_set]
                if allowed_stores_set is not None
                else list(ALL_8_PERU_STORES)
            )
            for s_id in stores_to_report:
                st = store_stats[s_id]
                logger.info(
                    f"[SYNC_STORE_SUMMARY] tienda={s_id} | 200_OK={st['ok_200']} | "
                    f"conservadas_error_temporal={st['retained_error']} | sin_stock(in_stock=False)={st['out_of_stock']}"
                )

            logger.info(
                f"Sincronización en vivo finalizada en {total_duration:.2f}s. Ofertas reales verificadas: {total_offers_updated}"
            )

            return {
                "status": "success",
                "updated_products": updated_products_count,
                "updated_offers": total_offers_updated,
                "price_drops_count": price_drops_count,
                "days_tracked": max_days_tracked,
                "peru_date": self.last_sync_date.isoformat(),
                "schedule_windows": SCHEDULE_WINDOWS_LABELS,
                "duration_seconds": round(total_duration, 2),
                "timestamp": self.last_sync_timestamp,
                "store_stats": store_stats,
            }
        finally:
            self._is_syncing = False

    async def record_intraday_price_observation(
        self,
        session: AsyncSession,
        product_id: str,
        new_best_price: float,
        today_peru: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Control de Precio Actual vs Mínimo Intradía en price_history:
        - product.best_price siempre muestra el precio vigente del último corte (00:59, 06:59, 12:59 o 18:59).
        - En price_history existe 1 sola fila por fecha calendario (UNIQUE(product_id, recorded_date)).
          Si el precio cambia 2 o más veces en el mismo día, hace UPSERT sobre la única fila de hoy
          guardando daily_record.price = min(daily_record.price, new_best_price) y actualiza
          historical_min_price = min(historical_min_price, new_best_price).
        """
        t_peru = today_peru or get_today_peru()
        t_iso = t_peru.isoformat()
        t_label = format_peru_date_label(t_peru)
        clean_new_price = round(float(new_best_price), 2)

        if isinstance(product_id, ProductEntity):
            prod = product_id
            resolved_product_id = prod.id
        else:
            resolved_product_id = str(product_id)
            prod_res = await session.execute(
                select(ProductEntity).where(ProductEntity.id == resolved_product_id)
            )
            prod = prod_res.scalar_one_or_none()

        if prod:
            prod.best_price = clean_new_price
            current_hist_min = prod.historical_min_price if prod.historical_min_price else clean_new_price
            prod.historical_min_price = round(min(float(current_hist_min), clean_new_price), 2)
            prod.is_historical_min = bool(clean_new_price <= prod.historical_min_price)
            prod.updated_at = utc_now()

        hist_res = await session.execute(
            select(PriceHistoryEntity).where(
                (PriceHistoryEntity.product_id == resolved_product_id)
                & (
                    (PriceHistoryEntity.recorded_date == t_iso)
                    | (PriceHistoryEntity.day_offset == 0)
                )
            )
        )
        daily_record = hist_res.scalars().first()
        if daily_record:
            daily_record.price = round(min(float(daily_record.price), clean_new_price), 2)
            daily_record.recorded_date = t_iso
            daily_record.date_label = t_label
            daily_record.day_offset = 0
            daily_record.recorded_at = utc_now()
        else:
            daily_record = PriceHistoryEntity(
                product_id=resolved_product_id,
                day_offset=0,
                date_label=t_label,
                recorded_date=t_iso,
                price=clean_new_price,
                recorded_at=utc_now(),
            )
            session.add(daily_record)

        if prod and daily_record.price < (prod.historical_min_price or clean_new_price):
            prod.historical_min_price = daily_record.price
            prod.is_historical_min = bool(prod.best_price <= prod.historical_min_price)

        await session.commit()
        return {
            "product_id": product_id,
            "current_best_price": clean_new_price,
            "daily_min_price": daily_record.price,
            "historical_min_price": prod.historical_min_price if prod else daily_record.price,
            "recorded_date": t_iso,
        }

    async def needs_scheduled_catchup(self, session: AsyncSession) -> bool:
        """
        Verifica si se requiere Catch-Up automático al despertar:
        1. Si aún no existe la fila de HOY (today_peru) en price_history, o
        2. Si ya pasó el último corte de 6 horas (00:59, 06:59, 12:59 o 18:59 America/Lima)
           desde la última sincronización registrada.
        """
        today_peru = get_today_peru()
        today_iso = today_peru.isoformat()

        stmt = select(PriceHistoryEntity.id).where(
            PriceHistoryEntity.recorded_date == today_iso
        ).limit(1)
        res = await session.execute(stmt)
        has_today = res.scalar_one_or_none() is not None
        if not has_today:
            return True

        if not self.last_sync_timestamp:
            return False

        try:
            raw_ts = self.last_sync_timestamp.replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(raw_ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            last_peru = last_dt.astimezone(ZoneInfo("America/Lima"))
            latest_cutoff = get_latest_scheduled_cutoff_peru()
            return last_peru < latest_cutoff
        except Exception:
            return False

    async def needs_daily_catchup(self, session: AsyncSession) -> bool:
        """Alias compatible con verificaciones previas de Catch-Up."""
        return await self.needs_scheduled_catchup(session)

    async def run_scheduled_price_update(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
        only_stores: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Rutina programada ejecutada 4 veces al día (00:59, 06:59, 12:59 y 18:59 America/Lima)
        o en Catch-Up al despertar el contenedor:
        1. Actualiza precios y stock en vivo con concurrencia controlada y Triple Candado de Integridad.
        2. Si una tienda se quedó SIN STOCK (in_stock == False), la desactiva automáticamente de las ofertas
           de ese producto y recalcula best_price solo entre las tiendas con stock activo.
        3. Hace UPSERT sobre la única fila de hoy en price_history guardando el mínimo intradía.
        """
        logger.info("Iniciando actualización programada de precios (ventanas 00:59, 06:59, 12:59, 18:59 America/Lima)...")
        result = await self.sync_all_catalog_products(
            session=session,
            on_cache_invalidate=on_cache_invalidate,
            only_stores=only_stores,
        )

        if settings.ENABLE_AUTO_CATEGORY_DISCOVERY:
            try:
                from app.collectors.catalog_promoter import promote_store_listings
                from app.collectors.category_crawler import crawl_categories

                crawl_res = await crawl_categories(
                    stores=only_stores,
                    max_pages=max(1, int(settings.AUTO_CATEGORY_MAX_PAGES)),
                    dry_run=False,
                    session=session,
                )
                promo_res = await promote_store_listings(
                    session=session,
                    dry_run=False,
                )
                if on_cache_invalidate:
                    on_cache_invalidate()
                result["auto_category_discovery"] = {
                    "extracted_1p": crawl_res.extracted_1p,
                    "inserted_listings": crawl_res.inserted,
                    "updated_listings": crawl_res.updated,
                    "promoted_multi_store": promo_res.new_multi_store_groups,
                    "promoted_single_store": promo_res.new_single_store_products,
                    "linked_existing": promo_res.linked_to_existing_products,
                }
            except Exception as exc:
                logger.warning(
                    f"Auto category discovery/promotion falló sin bloquear flujo principal: {exc}"
                )

        gc.collect()
        logger.info(f"Actualización programada completada exitosamente: {result}")
        return result

    async def run_daily_price_update(
        self,
        session: AsyncSession,
        on_cache_invalidate: Optional[Callable[[], None]] = None,
        only_stores: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Alias compatible que delega a run_scheduled_price_update."""
        return await self.run_scheduled_price_update(
            session=session,
            on_cache_invalidate=on_cache_invalidate,
            only_stores=only_stores,
        )


orchestrator = CollectorOrchestrator()
