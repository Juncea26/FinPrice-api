"""
Endpoints de ofertas físicas comunitarias: GET y POST /api/v1/community-offers
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import check_read_rate_limit, check_write_rate_limit, sanitize_input_text
from app.models.schemas import CommunityOfferCreateSchema, CommunityPhysicalOfferSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/community-offers", tags=["Comunidad"])


@router.get(
    "",
    response_model=List[CommunityPhysicalOfferSchema],
    summary="Listar ofertas físicas reportadas por la comunidad",
    dependencies=[Depends(check_read_rate_limit)],
)
async def list_community_offers(
    department: Optional[str] = Query(None, max_length=80),
    province: Optional[str] = Query(None, max_length=80),
    district: Optional[str] = Query(None, max_length=80),
    product_id: Optional[str] = Query(None, max_length=80),
    session: AsyncSession = Depends(get_db),
):
    """
    Retorna la lista de ofertas físicas reales reportadas por usuarios en tiendas y malls del Perú.
    """
    clean_dept = sanitize_input_text(department, max_length=80)
    clean_prov = sanitize_input_text(province, max_length=80)
    clean_dist = sanitize_input_text(district, max_length=80)
    clean_prod = sanitize_input_text(product_id, max_length=80)

    return await catalog_service.get_community_offers(
        session=session,
        department=clean_dept,
        province=clean_prov,
        district=clean_dist,
        product_id=clean_prod,
    )


@router.post(
    "",
    response_model=CommunityPhysicalOfferSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva oferta física de tienda retail",
    dependencies=[Depends(check_write_rate_limit)],
)
async def create_community_offer(
    offer_in: CommunityOfferCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """
    Registra una oferta física real encontrada en tienda local.
    Valida departamento contra ubigeo peruano y vincula al producto existente.
    """
    return await catalog_service.create_community_offer(session=session, offer_in=offer_in)
