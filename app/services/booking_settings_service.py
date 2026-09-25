from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.property_booking_settings import crud_property_booking_settings
from app.models.property_booking_settings import PropertyBookingSettings
from app.schemas.property_booking_settings import (
    PropertyBookingSettingsCreate,
    PropertyBookingSettingsUpdate,
)
from app.utils.exceptions import EntityNotFoundException


class BookingSettingsService:
    async def get_by_property(
        self, db: AsyncSession, property_id: str
    ) -> PropertyBookingSettings:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        settings = await crud_property_booking_settings.get_by_property(
            db, property_id=property_id
        )
        if not settings:
            # Create default if not present
            data = PropertyBookingSettingsCreate(property_id=property_id).model_dump(
                exclude_unset=True
            )
            data["property_id"] = property_id
            settings = await crud_property_booking_settings.create(db, obj_in=data)
        return settings

    async def update_settings(
        self,
        db: AsyncSession,
        property_id: str,
        settings_in: PropertyBookingSettingsUpdate,
    ) -> PropertyBookingSettings:
        settings = await self.get_by_property(db, property_id)
        return await crud_property_booking_settings.update(
            db, db_obj=settings, obj_in=settings_in
        )


booking_settings_service = BookingSettingsService()
