from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.organization import crud_organization
from app.crud.property import crud_property
from app.crud.property_booking_settings import crud_property_booking_settings
from app.crud.property_settings import crud_property_settings
from app.models.property import Property
from app.schemas.property import PropertyCreate, PropertyUpdate
from app.schemas.property_booking_settings import PropertyBookingSettingsCreate
from app.schemas.property_settings import PropertySettingsCreate
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
)


class PropertyService:
    async def get_by_id(self, db: AsyncSession, property_id: str) -> Property:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)
        return prop

    async def list_by_organization(
        self, db: AsyncSession, organization_id: str, skip: int = 0, limit: int = 100
    ) -> List[Property]:
        return await crud_property.get_by_organization(
            db, organization_id=organization_id, skip=skip, limit=limit
        )

    async def create_property(
        self, db: AsyncSession, organization_id: str, prop_in: PropertyCreate
    ) -> Property:
        org = await crud_organization.get(db, organization_id)
        if not org:
            raise EntityNotFoundException("Organization", organization_id)

        existing = await crud_property.get_by_code(
            db, organization_id=organization_id, code=prop_in.code
        )
        if existing:
            raise DuplicateEntityException("Property", "code", prop_in.code)

        prop_data = prop_in.model_dump(exclude_unset=True)
        prop_data["organization_id"] = organization_id
        prop = await crud_property.create(db, obj_in=prop_data)

        # Initialize default booking settings for property matching schema
        default_settings = PropertyBookingSettingsCreate(property_id=prop.id)
        settings_data = default_settings.model_dump(exclude_unset=True)
        settings_data["property_id"] = prop.id
        await crud_property_booking_settings.create(db, obj_in=settings_data)

        # Initialize default property settings
        default_prop_settings = PropertySettingsCreate(property_id=prop.id)
        prop_settings_data = default_prop_settings.model_dump(exclude_unset=True)
        prop_settings_data["property_id"] = prop.id
        await crud_property_settings.create(db, obj_in=prop_settings_data)

        return prop

    async def update_property(
        self, db: AsyncSession, property_id: str, prop_in: PropertyUpdate
    ) -> Property:
        prop = await self.get_by_id(db, property_id)
        if prop_in.code and prop_in.code != prop.code:
            existing = await crud_property.get_by_code(
                db, organization_id=prop.organization_id, code=prop_in.code
            )
            if existing:
                raise DuplicateEntityException("Property", "code", prop_in.code)
        return await crud_property.update(db, db_obj=prop, obj_in=prop_in)

    async def delete_property(self, db: AsyncSession, property_id: str) -> Property:
        prop = await self.get_by_id(db, property_id)
        await crud_property.remove(db, id=property_id)
        return prop


property_service = PropertyService()
