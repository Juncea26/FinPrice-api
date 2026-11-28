"""
Endpoints de productos: GET /api/v1/products y GET /api/v1/products/{product_id}
Soporta filtrado dinámico sobre cualquier faceta extraída de tech_specs.
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Literal, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import WriterSessionLocal, get_read_db, is_test
from app.core.security import check_read_rate_limit, sanitize_input_text, verify_api_token_or_client
from app.collectors.orchestrator import get_today_peru, orchestrator
from app.collectors.spec_extractor import CANONICAL_SPEC_MAP, map_to_canonical_key
from app.models.schemas import CategoriesResponseSchema, PricePointSchema, ProductSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/products", tags=["Productos"])
categories_router = APIRouter(prefix="/categories", tags=["Categorías"])


async def _run_catchup_in_background() -> None:
    try:
        async with WriterSessionLocal() as bg_session:
            if await orchestrator.needs_scheduled_catchup(bg_session):
                await orchestrator.run_scheduled_price_update(
                    session=bg_session,
                    on_cache_invalidate=catalog_service.invalidate_cache,
                )
    except Exception:
        pass

RESERVED_QUERY_PARAMS = {
    "search",
    "category",
    "brand",
    "processor",
    "ram",
    "storage",
    "tv_resolution",
    "connectivity",
    "screen",
    "os",
    "enabled_stores",
    "sort_order",
    "limit",
    "offset",
    "store",
    "min_stores",
    "sort",
}


@router.get(
    "",
    response_model=List[ProductSchema],
    summary="Listado y filtrado dinámico de productos con precios y specs reales",
    dependencies=[Depends(check_read_rate_limit), Depends(verify_api_token_or_client)],
)
async def get_products(
    request: Request,
    search: Optional[str] = Query(None, max_length=80),
    category: Optional[str] = Query(None, max_length=80),
    brand: Optional[str] = Query(None, max_length=80),
    processor: Optional[str] = Query(None, max_length=80),
    ram: Optional[str] = Query(None, max_length=80),
    storage: Optional[str] = Query(None, max_length=80),
    tv_resolution: Optional[str] = Query(None, max_length=80),
    connectivity: Optional[str] = Query(None, max_length=80),
    screen: Optional[str] = Query(None, max_length=80),
    os: Optional[str] = Query(None, max_length=80),
    enabled_stores: Optional[str] = Query(None, max_length=150),
    store: Optional[str] = Query(None, max_length=50, description="Filtra productos disponibles en una tienda oficial"),
    min_stores: Optional[int] = Query(None, ge=1, le=8, description="Mínimo de tiendas con stock activo"),
    sort: Optional[Literal["discount", "price_asc", "price_desc", "stores_desc"]] = Query(
        None,
        description="Ordenamiento opcional (discount, price_asc, price_desc, stores_desc)",
    ),
    sort_order: Optional[Literal["LOW_TO_HIGH", "HIGH_TO_LOW"]] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Límite opcional de productos a retornar"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    session: AsyncSession = Depends(get_read_db),
):
    """
    Retorna los productos con precios y fichas técnicas reales extraídas de tiendas de Perú.
    Soporta tanto parámetros directos (ram, storage, processor, connectivity, tv_resolution,
    store, min_stores, sort, limit, offset) como cualquier clave canónica dinámica de tech_specs.
    """
    clean_search = sanitize_input_text(search, max_length=80)
    clean_category = sanitize_input_text(category, max_length=80)
    clean_brand = sanitize_input_text(brand, max_length=80)
    clean_processor = sanitize_input_text(processor, max_length=80)
    clean_ram = sanitize_input_text(ram, max_length=80)
    clean_storage = sanitize_input_text(storage, max_length=80)
    clean_tv_res = sanitize_input_text(tv_resolution, max_length=80)
    clean_conn = sanitize_input_text(connectivity, max_length=80)
    clean_screen = sanitize_input_text(screen, max_length=80)
    clean_os = sanitize_input_text(os, max_length=80)
    clean_stores = sanitize_input_text(enabled_stores, max_length=150)
    clean_store = sanitize_input_text(store, max_length=50)

    # Capturar cualquier filtro dinámico adicional que corresponda a una clave de tech_specs
    dynamic_specs: Dict[str, str] = {}
    for q_key, q_val in request.query_params.items():
        if q_key in RESERVED_QUERY_PARAMS or not q_val:
            continue
        canonical_key = q_key if q_key in CANONICAL_SPEC_MAP else map_to_canonical_key(q_key)
        if canonical_key:
            clean_val = sanitize_input_text(q_val, max_length=80)
            if clean_val:
                dynamic_specs[canonical_key] = clean_val

    # Catch-Up en segundo plano en la primera petición GET /api/v1/products del día
    # si last_sync_date < today_peru y la hora en Perú ya pasó de las 00:59 AM
    if not is_test and not orchestrator._is_syncing:
        now_peru = datetime.now(ZoneInfo("America/Lima"))
        today_peru = now_peru.date()
        is_past_0059 = (now_peru.hour > 0) or (now_peru.hour == 0 and now_peru.minute >= 59)
        if is_past_0059 and (orchestrator.last_sync_date is None or orchestrator.last_sync_date < today_peru):
            if await orchestrator.needs_daily_catchup(session):
                asyncio.create_task(_run_catchup_in_background())

    payload_bytes = await catalog_service.get_products_serialized_json(
        session=session,
        search=clean_search,
        category=clean_category,
        brand=clean_brand,
        processor=clean_processor,
        ram=clean_ram,
        storage=clean_storage,
        tv_resolution=clean_tv_res,
        connectivity=clean_conn,
        screen=clean_screen,
        os_filter=clean_os,
        dynamic_specs=dynamic_specs if dynamic_specs else None,
        enabled_stores=clean_stores,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
        store=clean_store,
        min_stores=min_stores,
        sort=sort,
    )
    return Response(content=payload_bytes, media_type="application/json")


@router.get(
    "/search",
    response_model=List[ProductSchema],
    summary="Búsqueda rápida de productos por palabra clave",
    dependencies=[Depends(check_read_rate_limit), Depends(verify_api_token_or_client)],
)
async def search_products(
    request: Request,
    q: Optional[str] = Query(None, max_length=80),
    search: Optional[str] = Query(None, max_length=80),
    category: Optional[str] = Query(None, max_length=80),
    brand: Optional[str] = Query(None, max_length=80),
    limit: int = Query(250, ge=1, le=500, description="Límite de productos"),
    session: AsyncSession = Depends(get_read_db),
):
    """Búsqueda directa de productos por término (compatible con app Android)."""
    search_term = q or search
    clean_search = sanitize_input_text(search_term, max_length=80)
    clean_category = sanitize_input_text(category, max_length=80)
    clean_brand = sanitize_input_text(brand, max_length=80)
    # Catch-Up en segundo plano en la primera petición GET /api/v1/products del día
    # si last_sync_date < today_peru y la hora en Perú ya pasó de las 00:59 AM
    if not is_test and not orchestrator._is_syncing:
        now_peru = datetime.now(ZoneInfo("America/Lima"))
        today_peru = now_peru.date()
        is_past_0059 = (now_peru.hour > 0) or (now_peru.hour == 0 and now_peru.minute >= 59)
        if is_past_0059 and (orchestrator.last_sync_date is None or orchestrator.last_sync_date < today_peru):
            if await orchestrator.needs_daily_catchup(session):
                asyncio.create_task(_run_catchup_in_background())

    return await catalog_service.get_products(
        session=session,
        search=clean_search,
        category=clean_category,
        brand=clean_brand,
        limit=limit,
    )


@router.get(
    "/{product_id}",
    response_model=ProductSchema,
    summary="Detalle completo de producto con historial y ofertas por tienda",
    dependencies=[Depends(check_read_rate_limit), Depends(verify_api_token_or_client)],
)
async def get_product_by_id(
    product_id: str,
    session: AsyncSession = Depends(get_read_db),
):
    """Retorna el detalle completo y serie de precios reales observados para el producto."""
    clean_id = sanitize_input_text(product_id, max_length=80)
    product = await catalog_service.get_product_by_id(product_id=clean_id, session=session)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con ID '{clean_id}' no encontrado en FinPrice API.",
        )
    return product


@router.get(
    "/{product_id}/history",
    response_model=List[PricePointSchema],
    summary="Historial de precios de los últimos 30 días para gráfica móvil",
    dependencies=[Depends(check_read_rate_limit), Depends(verify_api_token_or_client)],
)
async def get_product_price_history(
    product_id: str,
    session: AsyncSession = Depends(get_read_db),
):
    """Retorna la serie temporal de precios reales observados en los últimos 30 días."""
    clean_id = sanitize_input_text(product_id, max_length=80)
    product = await catalog_service.get_product_by_id(product_id=clean_id, session=session)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con ID '{clean_id}' no encontrado en FinPrice API.",
        )
    return product.price_history_30_days


@categories_router.get(
    "",
    response_model=CategoriesResponseSchema,
    summary="Listado dinámico de categorías activas y conteo real de productos",
    dependencies=[Depends(check_read_rate_limit), Depends(verify_api_token_or_client)],
)
async def get_active_categories(
    store: Optional[str] = Query(None, max_length=50, description="Filtra conteos por tienda oficial"),
    enabled_stores: Optional[str] = Query(None, max_length=150, description="Lista de tiendas habilitadas separadas por coma"),
    session: AsyncSession = Depends(get_read_db),
):
    """
    Devuelve dinámicamente todas las categorías con al menos un producto activo (`price > 0` y stock)
    mediante `GROUP BY`, ordenadas según `STANDARD_CATEGORY_ORDER` y luego alfabéticamente.
    """
    clean_store = sanitize_input_text(store, max_length=50)
    clean_stores = sanitize_input_text(enabled_stores, max_length=150)
    payload_bytes = await catalog_service.get_categories_serialized_json(
        session=session,
        store=clean_store,
        enabled_stores=clean_stores,
    )
    return Response(content=payload_bytes, media_type="application/json")
