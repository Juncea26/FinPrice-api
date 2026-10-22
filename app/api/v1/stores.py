"""
Endpoints de tiendas retail oficiales: GET /api/v1/stores
"""
from typing import List
from fastapi import APIRouter, Depends

from app.core.security import check_read_rate_limit
from app.models.schemas import StoreSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/stores", tags=["Tiendas"])


@router.get(
    "",
    response_model=List[StoreSchema],
    summary="Listado oficial de tiendas retail peruanas soportadas",
    dependencies=[Depends(check_read_rate_limit)],
)
def get_stores():
    """
    Lista las tiendas retail del Perú y el estado en tiempo real de su Circuit Breaker.
    """
    return catalog_service.get_stores()
