from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.property_booking_engine_config import (
    PublicResolvedPropertyResponse,
    PublicBookingEngineConfigResponse,
    PublicAvailabilitySearchResponse,
    PublicRateCalendarDay,
    PublicQuoteRequest,
    PublicQuoteResponse,
    PublicBookingCreateRequest,
    PublicBookingConfirmationResponse,
    PublicBookingLookupResponse,
    PublicBookingCancelRequest,
    PublicBookingCancelResponse,
)
from app.services.public_booking_service import public_booking_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(
    prefix="/public/booking-engine",
    tags=["Public Booking Engine (Guest Facing)"],
)


@router.get(
    "/resolve",
    response_model=PublicResolvedPropertyResponse,
    summary="Resolve Property & Hotel Group Context",
    dependencies=[Depends(rate_limit("public_resolve", 60, 60))],
)
async def resolve_booking_engine_property(
    request: Request,
    domain: Optional[str] = Query(None, description="Custom domain host, e.g. reservations.tajhotels.com"),
    slug: Optional[str] = Query(None, description="Property URL slug, e.g. taj-bangalore"),
    property_id: Optional[str] = Query(None, description="Direct property UUID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Public entrypoint called on app bootstrap.
    Resolves property context, identifies whether the hotel belongs to a group (e.g. Taj Hotels),
    and provides the sibling hotels list for the group switcher.
    """
    host_header = domain or request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    return await public_booking_service.resolve_property(
        db, domain=host_header, slug=slug, property_id=property_id
    )


@router.get(
    "/config",
    response_model=PublicBookingEngineConfigResponse,
    summary="Get Public Theme, Branding & Policies (Query param)",
    dependencies=[Depends(rate_limit("public_config", 60, 60))],
)
async def get_public_booking_config_by_query(
    property_id: Optional[str] = Query(None, description="Property UUID or slug"),
    slug: Optional[str] = Query(None, description="Property slug"),
    db: AsyncSession = Depends(get_db),
):
    target = property_id or slug
    if not target:
        resolved = await public_booking_service.resolve_property(db)
        target = resolved.property_id
    else:
        resolved = await public_booking_service.resolve_property(db, slug=target, property_id=target)
        target = resolved.property_id
    return await public_booking_service.get_public_config(db, property_id=target)


@router.get(
    "/{property_id}/config",
    response_model=PublicBookingEngineConfigResponse,
    summary="Get Public Theme, Branding & Policies",
    dependencies=[Depends(rate_limit("public_config", 60, 60))],
)
async def get_public_booking_config(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Returns safe public theme CSS variables, branding assets, policies, and payment gateway public keys."""
    resolved = await public_booking_service.resolve_property(db, slug=property_id, property_id=property_id)
    return await public_booking_service.get_public_config(db, property_id=resolved.property_id)


@router.get(
    "/availability",
    response_model=PublicAvailabilitySearchResponse,
    summary="Search Available Room Types & Rates (Query param)",
    dependencies=[Depends(rate_limit("public_availability", 60, 60))],
)
async def search_availability_by_query(
    property_id: Optional[str] = Query(None, description="Property UUID or slug"),
    check_in: date = Query(..., description="Arrival date (YYYY-MM-DD)"),
    check_out: date = Query(..., description="Departure date (YYYY-MM-DD)"),
    adults: int = Query(2, ge=1, description="Adult guests count"),
    children: int = Query(0, ge=0, description="Children count"),
    rooms_count: int = Query(1, ge=1, description="Number of rooms requested"),
    promo_code: Optional[str] = Query(None, description="Promotional voucher code"),
    db: AsyncSession = Depends(get_db),
):
    target = property_id
    if not target:
        resolved = await public_booking_service.resolve_property(db)
        target = resolved.property_id
    else:
        resolved = await public_booking_service.resolve_property(db, slug=target, property_id=target)
        target = resolved.property_id

    return await public_booking_service.search_availability(
        db,
        property_id=target,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        rooms_count=rooms_count,
        promo_code=promo_code,
    )


@router.get(
    "/{property_id}/availability",
    response_model=PublicAvailabilitySearchResponse,
    summary="Search Available Room Types & Rates",
    dependencies=[Depends(rate_limit("public_availability", 60, 60))],
)
async def search_availability(
    property_id: str,
    check_in: date = Query(..., description="Arrival date (YYYY-MM-DD)"),
    check_out: date = Query(..., description="Departure date (YYYY-MM-DD)"),
    adults: int = Query(2, ge=1, description="Adult guests count"),
    children: int = Query(0, ge=0, description="Children count"),
    rooms_count: int = Query(1, ge=1, description="Number of rooms requested"),
    promo_code: Optional[str] = Query(None, description="Promotional voucher code"),
    db: AsyncSession = Depends(get_db),
):
    """Real-time availability search with live inventory, room photos, amenities, and published rate plans."""
    resolved = await public_booking_service.resolve_property(db, slug=property_id, property_id=property_id)
    return await public_booking_service.search_availability(
        db,
        property_id=resolved.property_id,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        rooms_count=rooms_count,
        promo_code=promo_code,
    )


@router.get(
    "/rate-calendar",
    response_model=List[PublicRateCalendarDay],
    summary="Get 30-Day Rate Calendar Matrix (Query param)",
    dependencies=[Depends(rate_limit("public_calendar", 30, 60))],
)
async def get_rate_calendar_by_query(
    property_id: Optional[str] = Query(None, description="Property UUID or slug"),
    start_date: date = Query(default_factory=lambda: datetime.now().date(), description="Calendar window start date"),
    days: int = Query(30, ge=7, le=60, description="Days range"),
    db: AsyncSession = Depends(get_db),
):
    target = property_id
    if not target:
        resolved = await public_booking_service.resolve_property(db)
        target = resolved.property_id
    else:
        resolved = await public_booking_service.resolve_property(db, slug=target, property_id=target)
        target = resolved.property_id

    return await public_booking_service.get_rate_calendar(
        db, property_id=target, start_date=start_date, days=days
    )


@router.get(
    "/{property_id}/rate-calendar",
    response_model=List[PublicRateCalendarDay],
    summary="Get 30-Day Rate Calendar Matrix",
    dependencies=[Depends(rate_limit("public_calendar", 30, 60))],
)
async def get_rate_calendar(
    property_id: str,
    start_date: date = Query(default_factory=lambda: datetime.now().date(), description="Calendar window start date"),
    days: int = Query(30, ge=7, le=60, description="Days range"),
    db: AsyncSession = Depends(get_db),
):
    """Returns daily minimum rate and availability status for the calendar date picker modal."""
    resolved = await public_booking_service.resolve_property(db, slug=property_id, property_id=property_id)
    return await public_booking_service.get_rate_calendar(
        db, property_id=resolved.property_id, start_date=start_date, days=days
    )


@router.post(
    "/quote",
    response_model=PublicQuoteResponse,
    summary="Calculate Price Breakdown & Quote (Query param)",
    dependencies=[Depends(rate_limit("public_quote", 30, 60))],
)
async def calculate_quote_by_query(
    payload: PublicQuoteRequest,
    property_id: Optional[str] = Query(None, description="Property UUID or slug"),
    db: AsyncSession = Depends(get_db),
):
    target = property_id
    if not target:
        resolved = await public_booking_service.resolve_property(db)
        target = resolved.property_id
    else:
        resolved = await public_booking_service.resolve_property(db, slug=target, property_id=target)
        target = resolved.property_id

    return await public_booking_service.calculate_quote(
        db, property_id=target, quote_in=payload
    )


@router.post(
    "/{property_id}/quote",
    response_model=PublicQuoteResponse,
    summary="Calculate Price Breakdown & Quote",
    dependencies=[Depends(rate_limit("public_quote", 30, 60))],
)
async def calculate_quote(
    property_id: str,
    payload: PublicQuoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculates authoritative total, room rates, taxes, direct host discounts, and deposit rules."""
    resolved = await public_booking_service.resolve_property(db, slug=property_id, property_id=property_id)
    return await public_booking_service.calculate_quote(
        db, property_id=resolved.property_id, quote_in=payload
    )


@router.post(
    "/bookings",
    response_model=PublicBookingConfirmationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Guaranteed Public Reservation (Query param)",
    dependencies=[Depends(rate_limit("public_booking", 10, 60))],
)
async def create_public_booking_by_query(
    request: Request,
    payload: PublicBookingCreateRequest,
    property_id: Optional[str] = Query(None, description="Property UUID or slug"),
    db: AsyncSession = Depends(get_db),
):
    target = property_id
    if not target:
        resolved = await public_booking_service.resolve_property(db)
        target = resolved.property_id
    else:
        resolved = await public_booking_service.resolve_property(db, slug=target, property_id=target)
        target = resolved.property_id

    client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else None)
    return await public_booking_service.create_public_booking(
        db, property_id=target, booking_in=payload, client_ip=client_ip
    )


@router.post(
    "/{property_id}/bookings",
    response_model=PublicBookingConfirmationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Guaranteed Public Reservation",
    dependencies=[Depends(rate_limit("public_booking", 10, 60))],
)
async def create_public_booking(
    request: Request,
    property_id: str,
    payload: PublicBookingCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Creates real reservation in CloudKey PMS, locks category inventory, creates guest profile, and opens folio."""
    resolved = await public_booking_service.resolve_property(db, slug=property_id, property_id=property_id)
    client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else None)
    return await public_booking_service.create_public_booking(
        db, property_id=resolved.property_id, booking_in=payload, client_ip=client_ip
    )


@router.get(
    "/manage",
    response_model=PublicBookingLookupResponse,
    summary="Lookup Reservation for Guest Self-Service",
    dependencies=[Depends(rate_limit("public_manage", 20, 60))],
)
async def lookup_public_booking(
    booking_number: str = Query(..., description="Booking reference code, e.g. TAJB-2611-4K8P9Q"),
    email: str = Query(..., description="Booker email address"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves booking record, room selections, stay dates, and cancellation eligibility."""
    return await public_booking_service.lookup_booking(
        db, booking_number=booking_number, email=email
    )


@router.post(
    "/manage/cancel",
    response_model=PublicBookingCancelResponse,
    summary="Cancel Confirmed Reservation",
    dependencies=[Depends(rate_limit("public_manage", 10, 60))],
)
async def cancel_public_booking(
    payload: PublicBookingCancelRequest,
    db: AsyncSession = Depends(get_db),
):
    """Cancels reservation and releases category inventory back to availability."""
    return await public_booking_service.cancel_public_booking(
        db, booking_number=payload.booking_number, email=payload.email, reason=payload.reason
    )

