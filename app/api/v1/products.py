"""
Endpoints de productos: GET /api/v1/products y GET /api/v1/products/{product_id}
"""
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import check_read_rate_limit, sanitize_input_text
from app.models.schemas import ProductSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/products", tags=["Productos"])


@router.get(
    "",
    response_model=List[ProductSchema],
    summary="Listado y filtrado de productos con precios reales",
    dependencies=[Depends(check_read_rate_limit)],
)
async def get_products(
    search: Optional[str] = Query(None, max_length=80),
    category: Optional[str] = Query(None, max_length=80),
    brand: Optional[str] = Query(None, max_length=80),
    processor: Optional[str] = Query(None, max_length=80),
    ram: Optional[str] = Query(None, max_length=80),
    storage: Optional[str] = Query(None, max_length=80),
    tv_resolution: Optional[str] = Query(None, max_length=80),
    enabled_stores: Optional[str] = Query(None, max_length=150),
    sort_order: Literal["LOW_TO_HIGH", "HIGH_TO_LOW"] = Query("LOW_TO_HIGH"),
    session: AsyncSession = Depends(get_db),
):
    """
    Retorna los productos con precios reales extraídos de tiendas de Perú.
    Soporta recálculo dinámico con enabled_stores y filtrado en memoria < 50ms.
    """
    clean_search = sanitize_input_text(search, max_length=80)
    clean_category = sanitize_input_text(category, max_length=80)
    clean_brand = sanitize_input_text(brand, max_length=80)
    clean_processor = sanitize_input_text(processor, max_length=80)
    clean_ram = sanitize_input_text(ram, max_length=80)
    clean_storage = sanitize_input_text(storage, max_length=80)
    clean_tv_res = sanitize_input_text(tv_resolution, max_length=80)
    clean_stores = sanitize_input_text(enabled_stores, max_length=150)

    return await catalog_service.get_products(
        session=session,
        search=clean_search,
        category=clean_category,
        brand=clean_brand,
        processor=clean_processor,
        ram=clean_ram,
        storage=clean_storage,
        tv_resolution=clean_tv_res,
        enabled_stores=clean_stores,
        sort_order=sort_order,
    )


@router.get(
    "/{product_id}",
    response_model=ProductSchema,
    summary="Detalle completo de producto con historial y ofertas por tienda",
    dependencies=[Depends(check_read_rate_limit)],
)
async def get_product_by_id(
    product_id: str,
    session: AsyncSession = Depends(get_db),
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
