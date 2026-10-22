"""
Endpoints de productos: GET /api/v1/products y GET /api/v1/products/{product_id}
"""
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import check_read_rate_limit, sanitize_input_text
from app.models.domain import get_db
from app.models.schemas import ProductSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/products", tags=["Productos"])


@router.get(
    "",
    response_model=List[ProductSchema],
    summary="Listado y filtrado avanzado de productos multitienda",
    dependencies=[Depends(check_read_rate_limit)],
)
def get_products(
    search: Optional[str] = Query(None, max_length=80, description="Búsqueda en título, categoría o mejor tienda"),
    category: Optional[str] = Query(None, max_length=80, description="Filtrar por categoría (ej. Smartphones, Laptops, Tablets, TVs)"),
    brand: Optional[str] = Query(None, max_length=80, description="Filtrar por marca (ej. Samsung, Apple, Asus, LG, Xiaomi)"),
    processor: Optional[str] = Query(None, max_length=80, description="Filtrar por procesador (en título o especificaciones)"),
    ram: Optional[str] = Query(None, max_length=80, description="Filtrar por RAM (ej. 8GB, 12GB, 16GB, 32GB)"),
    storage: Optional[str] = Query(None, max_length=80, description="Filtrar por almacenamiento (ej. 128GB, 256GB, 512GB, 1TB)"),
    tv_resolution: Optional[str] = Query(None, max_length=80, description="Filtrar por resolución de pantalla o TV (ej. 4K, QHD, FHD)"),
    enabled_stores: Optional[str] = Query(
        None,
        max_length=150,
        description="Lista separada por comas de tiendas permitidas (ej. 'efe,falabella,ripley'). Recalcula dinámicamente el mejor precio.",
    ),
    sort_order: Literal["LOW_TO_HIGH", "HIGH_TO_LOW"] = Query(
        "LOW_TO_HIGH", description="Criterio de ordenación por precio: LOW_TO_HIGH o HIGH_TO_LOW"
    ),
    db: Session = Depends(get_db),
):
    """
    Retorna los productos filtrados y ordenados con sus ofertas por tienda y serie de 30 días.
    Ejecuta en < 50ms gracias a la caché en memoria y pre-cálculo optimizado.
    """
    clean_search = sanitize_input_text(search, max_length=80)
    clean_category = sanitize_input_text(category, max_length=80)
    clean_brand = sanitize_input_text(brand, max_length=80)
    clean_processor = sanitize_input_text(processor, max_length=80)
    clean_ram = sanitize_input_text(ram, max_length=80)
    clean_storage = sanitize_input_text(storage, max_length=80)
    clean_tv_res = sanitize_input_text(tv_resolution, max_length=80)
    clean_stores = sanitize_input_text(enabled_stores, max_length=150)

    return catalog_service.get_products(
        db=db,
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
    summary="Detalle completo de producto con ofertas por tienda e historial",
    dependencies=[Depends(check_read_rate_limit)],
)
def get_product_by_id(
    product_id: str,
    db: Session = Depends(get_db),
):
    """
    Retorna el detalle exhaustivo del producto identificado por product_id,
    incluyendo sus ofertas ordenadas de menor a mayor precio y sus 30 días de historial.
    """
    clean_id = sanitize_input_text(product_id, max_length=50)
    product = catalog_service.get_product_by_id(product_id=clean_id, db=db)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con ID '{clean_id}' no encontrado en FinPrice API.",
        )
    return product
