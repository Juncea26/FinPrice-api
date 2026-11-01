"""
Endpoints de publicaciones y ofertas de la Comunidad:
- GET /api/v1/community/posts (Listar publicaciones)
- POST /api/v1/community/posts (Crear publicación)
- GET /api/v1/community/posts/{post_id} (Detalle de publicación)
- PUT /api/v1/community/posts/{post_id} (Editar publicación)
- GET y POST /api/v1/community-offers (Retrocompatibilidad total con ofertas físicas)
- PUT /api/v1/community-offers/{offer_id} (Editar oferta física)
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import check_read_rate_limit, check_write_rate_limit, sanitize_input_text
from app.models.schemas import (
    CommunityOfferCreateSchema,
    CommunityPhysicalOfferSchema,
    CommunityPostCreateSchema,
    CommunityPostSchema,
    CommunityPostUpdateSchema,
)
from app.services.catalog_service import catalog_service

router = APIRouter(tags=["Comunidad"])


# ==============================================================================
# PUBLICACIONES DE LA COMUNIDAD (/api/v1/community/posts)
# ==============================================================================

@router.get(
    "/community/posts",
    response_model=List[CommunityPostSchema],
    summary="Listar publicaciones de ofertas de la comunidad",
    dependencies=[Depends(check_read_rate_limit)],
)
async def list_community_posts(
    department: Optional[str] = Query(None, max_length=80),
    province: Optional[str] = Query(None, max_length=80),
    district: Optional[str] = Query(None, max_length=80),
    product_id: Optional[str] = Query(None, max_length=80),
    search: Optional[str] = Query(None, max_length=100),
    session: AsyncSession = Depends(get_db),
):
    """Retorna publicaciones de ofertas compartidas por la comunidad de usuarios."""
    clean_dept = sanitize_input_text(department, max_length=80)
    clean_prov = sanitize_input_text(province, max_length=80)
    clean_dist = sanitize_input_text(district, max_length=80)
    clean_prod = sanitize_input_text(product_id, max_length=80)
    clean_search = sanitize_input_text(search, max_length=100)

    return await catalog_service.get_community_posts(
        session=session,
        department=clean_dept,
        province=clean_prov,
        district=clean_dist,
        product_id=clean_prod,
        search=clean_search,
    )


@router.post(
    "/community/posts",
    response_model=CommunityPostSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva publicación en la comunidad",
    dependencies=[Depends(check_write_rate_limit)],
)
async def create_community_post(
    post_in: CommunityPostCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """Crea una publicación comunitaria sobre una oferta encontrada en tiendas de Perú."""
    return await catalog_service.create_community_post(session=session, post_in=post_in)


@router.get(
    "/community/posts/{post_id}",
    response_model=CommunityPostSchema,
    summary="Detalle de una publicación comunitaria",
    dependencies=[Depends(check_read_rate_limit)],
)
async def get_community_post(
    post_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Obtiene una publicación específica por su identificador."""
    clean_id = sanitize_input_text(post_id, max_length=80)
    post = await catalog_service.get_community_post_by_id(session=session, post_id=clean_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publicación con ID '{clean_id}' no encontrada.",
        )
    return post


@router.put(
    "/community/posts/{post_id}",
    response_model=CommunityPostSchema,
    summary="Editar una publicación comunitaria",
    dependencies=[Depends(check_write_rate_limit)],
)
async def update_community_post(
    post_id: str,
    post_in: CommunityPostUpdateSchema,
    session: AsyncSession = Depends(get_db),
):
    """Permite editar campos de una publicación existente en la comunidad."""
    clean_id = sanitize_input_text(post_id, max_length=80)
    return await catalog_service.update_community_post(
        session=session, post_id=clean_id, post_in=post_in
    )


# ==============================================================================
# OFERTAS FÍSICAS COMUNITARIAS (/api/v1/community-offers y /api/v1/community/offers)
# ==============================================================================

@router.get(
    "/community-offers",
    response_model=List[CommunityPhysicalOfferSchema],
    summary="Listar ofertas físicas reportadas por la comunidad",
    dependencies=[Depends(check_read_rate_limit)],
)
@router.get(
    "/community/offers",
    response_model=List[CommunityPhysicalOfferSchema],
    include_in_schema=False,
    dependencies=[Depends(check_read_rate_limit)],
)
async def list_community_offers(
    department: Optional[str] = Query(None, max_length=80),
    province: Optional[str] = Query(None, max_length=80),
    district: Optional[str] = Query(None, max_length=80),
    product_id: Optional[str] = Query(None, max_length=80),
    session: AsyncSession = Depends(get_db),
):
    """Retorna la lista de ofertas físicas reales reportadas por usuarios en tiendas y malls del Perú."""
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
    "/community-offers",
    response_model=CommunityPhysicalOfferSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva oferta física de tienda retail",
    dependencies=[Depends(check_write_rate_limit)],
)
@router.post(
    "/community/offers",
    response_model=CommunityPhysicalOfferSchema,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    dependencies=[Depends(check_write_rate_limit)],
)
async def create_community_offer(
    offer_in: CommunityOfferCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """Registra una oferta física real encontrada en tienda local."""
    return await catalog_service.create_community_offer(session=session, offer_in=offer_in)


@router.put(
    "/community-offers/{offer_id}",
    response_model=CommunityPhysicalOfferSchema,
    summary="Actualizar una oferta física comunitaria existente",
    dependencies=[Depends(check_write_rate_limit)],
)
@router.put(
    "/community/offers/{offer_id}",
    response_model=CommunityPhysicalOfferSchema,
    include_in_schema=False,
    dependencies=[Depends(check_write_rate_limit)],
)
async def update_community_offer_endpoint(
    offer_id: str,
    offer_in: Dict[str, Any],
    session: AsyncSession = Depends(get_db),
):
    """Actualiza los datos de una oferta física reportada previamente."""
    clean_id = sanitize_input_text(offer_id, max_length=80)
    return await catalog_service.update_community_offer(
        session=session, offer_id=clean_id, offer_update=offer_in
    )
