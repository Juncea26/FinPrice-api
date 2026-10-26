"""
Endpoint de facetas dinámicas: GET /api/v1/filters
Calcula en tiempo real desde la base de datos las categorías, marcas por categoría
y especificaciones técnicas (RAM, Almacenamiento, Procesador, Conectividad, etc.) por categoría.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import check_read_rate_limit
from app.models.schemas import DynamicFiltersSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/filters", tags=["Filtros & Facetas Dinámicas"])


@router.get(
    "",
    response_model=DynamicFiltersSchema,
    summary="Facetas dinámicas de filtrado por categoría, marca y especificaciones técnicas",
    dependencies=[Depends(check_read_rate_limit)],
)
async def get_dynamic_filters(session: AsyncSession = Depends(get_db)):
    """
    Calcula dinámicamente a partir de los productos activos en la base de datos:
    - categories: ['Todos', 'Smartphones', 'Laptops', 'Tablets', 'TVs']
    - brands_by_category: {'Todos': ['Todas', ...], 'Smartphones': ['Todas', ...]}
    - specs_by_category: {'Smartphones': {'Memoria RAM': ['Todas', ...], 'Almacenamiento': ['Todos', ...]}}
    """
    return await catalog_service.get_dynamic_filters(session=session)
