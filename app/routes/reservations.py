from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.reservation import (
    ReservationCreate,
    ReservationResponse,
)
from app.services.reservation_service import reservation_service
from app.crud.reservation import crud_reservation

router = APIRouter(prefix="/reservations", tags=["Reservations"])


@router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    property_id: str = Query(..., description="Property ID to create reservation for"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Create a new reservation in CloudKey PMS:
    - Generates unique hotel-code-prefixed booking number
    - Finds or creates booker in guests table
    - Creates reservation master row with status CONFIRMED
    - Creates reservation_rooms (room_id can stay NULL until check-in)
    - Links occupants in reservation_guests
    - Snapshots daily/hourly prices in reservation_room_rates
    - Opens 1 guest folio in folios table
    - If advance payment is taken: records payment and folio_transaction CREDIT
    - Records 1 audit log entry
    """
    return await reservation_service.create_reservation(
        db,
        property_id=property_id,
        res_in=payload,
        current_user_id=current_user.id,
    )


@router.get("", response_model=List[ReservationResponse])
async def list_reservations(
    property_id: str = Query(..., description="Property ID to filter reservations"),
    reservation_status: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. CONFIRMED, CHECKED_IN)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List reservations for a property."""
    reservations = await crud_reservation.list_by_property(
        db, property_id=property_id, status=reservation_status, skip=skip, limit=limit
    )
    result = []
    for r in reservations:
        folio = await crud_reservation.get_reservation_folio(db, reservation_id=r.id)
        payments = await crud_reservation.get_reservation_payments(db, reservation_id=r.id)
        result.append(
            ReservationResponse(
                id=r.id,
                property_id=r.property_id,
                booking_number=r.booking_number,
                guest_id=r.guest_id,
                company_id=r.company_id,
                booking_type=r.booking_type,
                source=r.source,
                channel_name=r.channel_name,
                channel_booking_ref=r.channel_booking_ref,
                status=r.status,
                check_in_at=r.check_in_at,
                check_out_at=r.check_out_at,
                currency=r.currency,
                total_amount=r.total_amount,
                total_tax_amount=r.total_tax_amount,
                special_requests=r.special_requests,
                created_at=r.created_at,
                cancelled_at=r.cancelled_at,
                cancellation_reason=r.cancellation_reason,
                updated_at=r.updated_at,
                booker=r.guest,
                rooms=r.rooms,
                folio=folio,
                payments=payments,
            )
        )
    return result


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: str,
    property_id: Optional[str] = Query(None, description="Optional property ID check"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get detailed reservation by ID."""
    return await reservation_service.get_reservation(
        db,
        property_id=property_id or "",
        reservation_id=reservation_id,
    )


@router.post("/{reservation_id}/rooms/{room_reservation_id}/assign", response_model=ReservationResponse)
async def assign_room(
    reservation_id: str,
    room_reservation_id: str,
    room_id: str = Query(..., description="Physical Room ID to assign"),
    property_id: str = Query(..., description="Property ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Assign physical room number to reservation room."""
    return await reservation_service.assign_room(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
        reservation_room_id=room_reservation_id,
        room_id=room_id,
        current_user_id=current_user.id,
    )


@router.post("/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: str,
    property_id: str = Query(..., description="Property ID"),
    reason: Optional[str] = Query(None, description="Cancellation reason"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Cancel a reservation and release inventory for remaining future nights."""
    return await reservation_service.cancel_reservation(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
        reason=reason,
        current_user_id=current_user.id,
    )


@router.post("/{reservation_id}/no-show", response_model=ReservationResponse)
async def no_show_reservation(
    reservation_id: str,
    property_id: str = Query(..., description="Property ID"),
    reason: Optional[str] = Query(None, description="No-show reason"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Mark a confirmed reservation as NO_SHOW and release inventory."""
    return await reservation_service.no_show_reservation(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
        reason=reason,
        current_user_id=current_user.id,
    )


@router.post("/{reservation_id}/check-in", response_model=ReservationResponse)
async def check_in_reservation(
    reservation_id: str,
    property_id: str = Query(..., description="Property ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Check-in reservation (no inventory change, room remains sold)."""
    return await reservation_service.check_in_reservation(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
        current_user_id=current_user.id,
    )


@router.post("/{reservation_id}/check-out", response_model=ReservationResponse)
async def check_out_reservation(
    reservation_id: str,
    property_id: str = Query(..., description="Property ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Check-out reservation."""
    return await reservation_service.check_out_reservation(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
        current_user_id=current_user.id,
    )


@router.post("/{reservation_id}/payments", response_model=ReservationResponse)
async def record_reservation_folio_payment(
    reservation_id: str,
    payload: dict,
    property_id: str = Query(..., description="Property ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Record a folio payment directly on a reservation and return refreshed reservation state."""
    from app.services.payment_service import payment_service
    from app.schemas.payment import PaymentCreateInput
    from decimal import Decimal

    payment_in = PaymentCreateInput(
        amount=Decimal(str(payload.get("amount", 0))),
        payment_method=payload.get("payment_method") or payload.get("payment_method_id", "CREDIT_CARD"),
        payment_type=payload.get("payment_type", "SETTLEMENT"),
        status=payload.get("status", "COMPLETED"),
        currency=payload.get("currency"),
        gateway=payload.get("gateway"),
        gateway_reference=payload.get("reference") or payload.get("gateway_reference"),
        card_last4=payload.get("card_last4"),
        notes=payload.get("notes"),
        reservation_id=reservation_id,
    )
    await payment_service.record_payment(
        db,
        property_id=property_id,
        payload=payment_in,
        current_user_id=current_user.id,
        reservation_id=reservation_id,
    )
    return await reservation_service.get_reservation(
        db,
        property_id=property_id,
        reservation_id=reservation_id,
    )


