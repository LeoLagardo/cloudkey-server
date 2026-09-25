from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.property_settings import PropertySettings
from app.schemas.property_settings import (
    PropertySettingsCreate,
    PropertySettingsUpdate,
)


class CRUDPropertySettings(
    CRUDBase[PropertySettings, PropertySettingsCreate, PropertySettingsUpdate]
):
    async def get_by_property(
        self, db: AsyncSession, *, property_id: str
    ) -> Optional[PropertySettings]:
        result = await db.execute(
            select(PropertySettings).where(
                PropertySettings.property_id == property_id
            )
        )
        return result.scalars().first()


crud_property_settings = CRUDPropertySettings(PropertySettings)
