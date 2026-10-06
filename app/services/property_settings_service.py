from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.property_settings import crud_property_settings
from app.models.property_settings import PropertySettings
from app.schemas.property_settings import (
    PropertySettingsCreate,
    PropertySettingsUpdate,
)
from app.utils.exceptions import EntityNotFoundException


class PropertySettingsService:
    async def get_by_property(
        self, db: AsyncSession, property_id: str
    ) -> PropertySettings:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        settings = await crud_property_settings.get_by_property(
            db, property_id=property_id
        )
        if not settings:
            # Create default if not present
            data = PropertySettingsCreate(property_id=property_id).model_dump(
                exclude_unset=True
            )
            data["property_id"] = property_id
            settings = await crud_property_settings.create(db, obj_in=data)
        return settings

    async def update_settings(
        self,
        db: AsyncSession,
        property_id: str,
        settings_in: PropertySettingsUpdate,
    ) -> PropertySettings:
        settings = await self.get_by_property(db, property_id)
        update_data = settings_in.model_dump(exclude_unset=True)
        if "night_audit_config" in update_data and update_data["night_audit_config"] is not None:
            existing_config = dict(settings.night_audit_config or {})
            existing_config.update(update_data["night_audit_config"])
            update_data["night_audit_config"] = existing_config
        return await crud_property_settings.update(
            db, db_obj=settings, obj_in=update_data
        )


property_settings_service = PropertySettingsService()
