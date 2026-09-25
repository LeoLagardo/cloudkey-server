from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.property_booking_settings import PropertyBookingSettings
from app.schemas.property_booking_settings import (
    PropertyBookingSettingsCreate,
    PropertyBookingSettingsUpdate,
)


class CRUDPropertyBookingSettings(
    CRUDBase[PropertyBookingSettings, PropertyBookingSettingsCreate, PropertyBookingSettingsUpdate]
):
    async def get_by_property(
        self, db: AsyncSession, *, property_id: str
    ) -> Optional[PropertyBookingSettings]:
        result = await db.execute(
            select(PropertyBookingSettings).where(
                PropertyBookingSettings.property_id == property_id
            )
        )
        return result.scalars().first()


crud_property_booking_settings = CRUDPropertyBookingSettings(PropertyBookingSettings)
