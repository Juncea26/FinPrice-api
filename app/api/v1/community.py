"""
Endpoints de ofertas físicas comunitarias: GET y POST /api/v1/community-offers
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import check_read_rate_limit, check_write_rate_limit, sanitize_input_text
from app.models.domain import get_db
from app.models.schemas import CommunityOfferCreateSchema, CommunityPhysicalOfferSchema
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/community-offers", tags=["Comunidad"])


@router.get(
    "",
    response_model=List[CommunityPhysicalOfferSchema],
    summary="Listar ofertas físicas reportadas por la comunidad",
    dependencies=[Depends(check_read_rate_limit)],
)
def list_community_offers(
    department: Optional[str] = Query(None, max_length=80, description="Filtrar por departamento peruano (ej. Lambayeque, Lima)"),
    province: Optional[str] = Query(None, max_length=80, description="Filtrar por provincia (ej. Chiclayo, Lima)"),
    district: Optional[str] = Query(None, max_length=80, description="Filtrar por distrito"),
    product_id: Optional[str] = Query(None, max_length=80, description="Filtrar por ID de producto"),
    db: Session = Depends(get_db),
):
    """
    Retorna la lista de ofertas físicas vistas por usuarios en tiendas y malls del Perú,
    filtrables por ubicación geográfica y producto.
    """
    clean_dept = sanitize_input_text(department, max_length=80)
    clean_prov = sanitize_input_text(province, max_length=80)
    clean_dist = sanitize_input_text(district, max_length=80)
    clean_prod = sanitize_input_text(product_id, max_length=80)

    return catalog_service.get_community_offers(
        db=db,
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
def create_community_offer(
    offer_in: CommunityOfferCreateSchema,
    db: Session = Depends(get_db),
):
    """
    Registra una oferta física en vitrina o tienda local.
    Valida departamento contra ubigeo oficial peruano, sanitiza comentarios y vincula al producto existente.
    """
    return catalog_service.create_community_offer(db=db, offer_in=offer_in)
