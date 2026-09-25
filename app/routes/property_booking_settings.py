from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.property_booking_settings import (
    PropertyBookingSettingsUpdate,
    PropertyBookingSettingsResponse,
)
from app.services.booking_settings_service import booking_settings_service

router = APIRouter(prefix="/booking-settings", tags=["Booking Settings"])


@router.get("/{property_id}", response_model=PropertyBookingSettingsResponse)
async def get_property_booking_settings(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get booking settings for a property."""
    return await booking_settings_service.get_by_property(db, property_id=property_id)


@router.put("/{property_id}", response_model=PropertyBookingSettingsResponse)
async def update_property_booking_settings(
    property_id: str,
    settings_in: PropertyBookingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update booking settings for a property."""
    return await booking_settings_service.update_settings(
        db, property_id=property_id, settings_in=settings_in
    )
