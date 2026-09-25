from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.property_booking_settings import PropertyBookingSettingsResponse
from app.schemas.property_setup import (
    PropertyDashboardResponse,
    SetupBookingSettingsRequest,
    SetupCompleteResponse,
    SetupRatePlansRequest,
    SetupRoomTypesRequest,
    SetupRoomsRequest,
    SetupStatusResponse,
    SetupTaxesRequest,
)
from app.schemas.rate_plan import RatePlanResponse
from app.schemas.room import RoomResponse
from app.schemas.room_type import RoomTypeResponse
from app.schemas.tax import TaxGroupResponse
from app.services.property_setup_service import property_setup_service

router = APIRouter(prefix="/properties/{property_id}", tags=["Property Setup & Dashboard"])


@router.get(
    "/setup/status",
    response_model=SetupStatusResponse,
    summary="Get Property Setup Wizard Status",
    description="Inspects current setup progress and determines the active wizard step.",
)
async def get_setup_status(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SetupStatusResponse:
    return await property_setup_service.get_setup_status(db, property_id=property_id)


@router.post(
    "/setup/room-types",
    response_model=List[RoomTypeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Step 1: Save Initial Room Types",
    description="Batch or single creation of room types during property onboarding.",
)
async def setup_room_types(
    property_id: str,
    data: SetupRoomTypesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[RoomTypeResponse]:
    return await property_setup_service.setup_room_types(
        db, property_id=property_id, data=data
    )


@router.post(
    "/setup/rooms",
    response_model=List[RoomResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Step 2: Save Initial Rooms (Single or Bulk Generated)",
    description="Provisions rooms individually or in generated numerical ranges for room types.",
)
async def setup_rooms(
    property_id: str,
    data: SetupRoomsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[RoomResponse]:
    return await property_setup_service.setup_rooms(
        db, property_id=property_id, data=data
    )


@router.post(
    "/setup/rate-plans",
    response_model=List[RatePlanResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Step 3: Save Initial Rate Plans & Pricing",
    description="Creates rate plans and associates initial room type rate structures.",
)
async def setup_rate_plans(
    property_id: str,
    data: SetupRatePlansRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[RatePlanResponse]:
    return await property_setup_service.setup_rate_plans(
        db, property_id=property_id, data=data
    )


@router.post(
    "/setup/taxes",
    response_model=List[TaxGroupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Step 4: Save Initial Taxes & Tax Groups",
    description="Provisions tax heads, rates, and tax groups and associates them with rate plans.",
)
async def setup_taxes(
    property_id: str,
    data: SetupTaxesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[TaxGroupResponse]:
    return await property_setup_service.setup_taxes(
        db, property_id=property_id, data=data
    )


@router.put(
    "/setup/booking-settings",
    response_model=PropertyBookingSettingsResponse,
    summary="Step 4: Configure Property Booking Settings",
    description="Updates check-in/out times, nightly/hourly rules, and stay duration parameters.",
)
async def setup_booking_settings(
    property_id: str,
    data: SetupBookingSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PropertyBookingSettingsResponse:
    return await property_setup_service.setup_booking_settings(
        db, property_id=property_id, data=data
    )


@router.post(
    "/setup/complete",
    response_model=SetupCompleteResponse,
    summary="Step 5: Finalize Setup & Unlock Operations",
    description="Validates completeness (min. 1 room type, 1 room, 1 rate plan), marks setup complete.",
)
async def complete_setup(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SetupCompleteResponse:
    return await property_setup_service.complete_setup(db, property_id=property_id)


@router.get(
    "/dashboard",
    response_model=PropertyDashboardResponse,
    summary="PMS Property Dashboard",
    description="Delivers operational metrics, room counts, rate plan summary, and readiness indicators.",
)
async def get_dashboard(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PropertyDashboardResponse:
    return await property_setup_service.get_dashboard(db, property_id=property_id)
