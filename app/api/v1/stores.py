"""
Endpoints de tiendas: GET /api/v1/stores
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
    Lista las 8 tiendas retail del Perú oficiales (Efe, Falabella, Ripley, Curacao, Hiraoka, Tottus, Metro, Wong)
    junto al estado en tiempo real de su Circuit Breaker (CLOSED, OPEN, HALF_OPEN).
    """
    return catalog_service.get_stores()
