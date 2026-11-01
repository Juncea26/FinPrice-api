"""
Endpoints para Libro de Reclamaciones y Sugerencias de Cancelación de Suscripción:
- POST /api/v1/complaints (y /api/v1/reclamaciones): Registrar queja o reclamo formal.
- GET /api/v1/complaints (y /api/v1/reclamaciones): Listar reclamaciones.
- GET /api/v1/complaints/{claim_id} (y /api/v1/reclamaciones/{claim_id}): Consulta de reclamo.
- POST /api/v1/complaints/cancel-suggestions (y /api/v1/cancellations): Sugerencias de cancelación.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import check_read_rate_limit, check_write_rate_limit, sanitize_input_text
from app.models.schemas import (
    CancellationSuggestionCreateSchema,
    CancellationSuggestionSchema,
    ComplaintCreateSchema,
    ComplaintSchema,
)
from app.services.catalog_service import catalog_service

router = APIRouter(tags=["Libro de Reclamaciones y Cancelaciones"])


@router.post(
    "/complaints",
    response_model=ComplaintSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un reclamo, queja o sugerencia formal",
    dependencies=[Depends(check_write_rate_limit)],
)
@router.post(
    "/reclamaciones",
    response_model=ComplaintSchema,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    dependencies=[Depends(check_write_rate_limit)],
)
async def create_complaint(
    complaint_in: ComplaintCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """
    Registra formalmente una hoja de reclamación en el Libro de Reclamaciones virtual
    conforme al Código de Protección y Defensa del Consumidor del Perú (Ley 29571).
    Genera un número de registro único correlativo (ej. REC-2026-XXXX).
    """
    return await catalog_service.create_complaint(session=session, complaint_in=complaint_in)


@router.get(
    "/complaints",
    response_model=List[ComplaintSchema],
    summary="Listar reclamaciones registradas",
    dependencies=[Depends(check_read_rate_limit)],
)
@router.get(
    "/reclamaciones",
    response_model=List[ComplaintSchema],
    include_in_schema=False,
    dependencies=[Depends(check_read_rate_limit)],
)
async def list_complaints(
    email: Optional[str] = Query(None, max_length=120),
    document_number: Optional[str] = Query(None, max_length=30),
    claim_number: Optional[str] = Query(None, max_length=60),
    session: AsyncSession = Depends(get_db),
):
    """Permite consultar el estado de quejas y reclamos mediante email, DNI o código de reclamo."""
    clean_email = sanitize_input_text(email, max_length=120)
    clean_doc = sanitize_input_text(document_number, max_length=30)
    clean_claim = sanitize_input_text(claim_number, max_length=60)

    return await catalog_service.get_complaints(
        session=session,
        email=clean_email,
        document_number=clean_doc,
        claim_number=clean_claim,
    )


@router.get(
    "/complaints/{claim_id}",
    response_model=ComplaintSchema,
    summary="Consultar detalle de una reclamación específica",
    dependencies=[Depends(check_read_rate_limit)],
)
@router.get(
    "/reclamaciones/{claim_id}",
    response_model=ComplaintSchema,
    include_in_schema=False,
    dependencies=[Depends(check_read_rate_limit)],
)
async def get_complaint(
    claim_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Retorna los detalles y estado de atención de una hoja de reclamación por su ID o código REC."""
    clean_id = sanitize_input_text(claim_id, max_length=60)
    complaint = await catalog_service.get_complaint_by_id(session=session, claim_identifier=clean_id)
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reclamación con identificador '{clean_id}' no encontrada.",
        )
    return complaint


@router.post(
    "/complaints/cancel-suggestions",
    response_model=CancellationSuggestionSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar sugerencia de cancelación de suscripción",
    dependencies=[Depends(check_write_rate_limit)],
)
@router.post(
    "/cancellations",
    response_model=CancellationSuggestionSchema,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    dependencies=[Depends(check_write_rate_limit)],
)
async def create_cancellation_suggestion(
    suggestion_in: CancellationSuggestionCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """Registra motivos y sugerencias cuando un usuario cancela o evalúa cancelar su suscripción."""
    return await catalog_service.create_cancellation_suggestion(
        session=session, suggestion_in=suggestion_in
    )
