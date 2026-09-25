from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.property_settings import (
    PropertySettingsUpdate,
    PropertySettingsResponse,
)
from app.services.property_settings_service import property_settings_service

router = APIRouter(prefix="/properties/{property_id}/settings", tags=["Property Settings"])


@router.get("", response_model=PropertySettingsResponse)
async def get_property_settings(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get regional, audit rollover, and operational settings for a property."""
    return await property_settings_service.get_by_property(db, property_id=property_id)


@router.put("", response_model=PropertySettingsResponse)
@router.patch("", response_model=PropertySettingsResponse)
async def update_property_settings(
    property_id: str,
    settings_in: PropertySettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update settings for a property."""
    return await property_settings_service.update_settings(
        db, property_id=property_id, settings_in=settings_in
    )
