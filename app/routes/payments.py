from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.payment import PaymentCreateInput, PaymentDetailResponse
from app.services.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=PaymentDetailResponse, status_code=status.HTTP_201_CREATED)
async def record_payment(
    payload: PaymentCreateInput,
    property_id: str = Query(..., description="Property ID to record payment for"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Record a new payment for a reservation folio:
    - Verifies reservation & folio
    - Ensures payment method exists
    - Inserts payment row
    - Posts CREDIT ledger row in folio_transactions
    - Logs audit record
    """
    return await payment_service.record_payment(
        db,
        property_id=property_id,
        payload=payload,
        current_user_id=current_user.id,
    )


@router.get("", response_model=List[PaymentDetailResponse])
async def list_payments(
    property_id: str = Query(..., description="Property ID to list payments for"),
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    payment_method: Optional[str] = Query(None, description="Optional payment method filter"),
    search: Optional[str] = Query(None, description="Search term across guests, booking #, folio #, ref"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all payments for a property with booking and guest details."""
    return await payment_service.list_payments(
        db,
        property_id=property_id,
        status=status,
        payment_method=payment_method,
        search=search,
        skip=skip,
        limit=limit,
    )
