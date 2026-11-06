from typing import Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.property_booking_engine_config import PropertyBookingEngineConfig
from app.schemas.property_booking_engine_config import (
    PropertyBookingEngineConfigCreate,
    PropertyBookingEngineConfigUpdate,
)


class CRUDPropertyBookingEngineConfig(
    CRUDBase[PropertyBookingEngineConfig, PropertyBookingEngineConfigCreate, PropertyBookingEngineConfigUpdate]
):
    async def get_by_property(
        self, db: AsyncSession, property_id: str
    ) -> Optional[PropertyBookingEngineConfig]:
        result = await db.execute(
            select(self.model).where(self.model.property_id == property_id)
        )
        return result.scalars().first()

    async def get_by_slug(
        self, db: AsyncSession, slug: str
    ) -> Optional[PropertyBookingEngineConfig]:
        result = await db.execute(
            select(self.model).where(self.model.slug == slug)
        )
        return result.scalars().first()

    async def get_by_custom_domain(
        self, db: AsyncSession, domain: str
    ) -> Optional[PropertyBookingEngineConfig]:
        clean_domain = domain.lower().strip()
        result = await db.execute(
            select(self.model).where(self.model.custom_domain == clean_domain)
        )
        return result.scalars().first()

    async def resolve_by_ingress(
        self, db: AsyncSession, identifier: str
    ) -> Optional[PropertyBookingEngineConfig]:
        """
        Resolves booking engine config by custom domain, slug, or property_id.
        """
        clean_id = identifier.lower().strip()
        result = await db.execute(
            select(self.model).where(
                or_(
                    self.model.custom_domain == clean_id,
                    self.model.slug == clean_id,
                    self.model.property_id == identifier,
                )
            )
        )
        return result.scalars().first()


crud_property_booking_engine_config = CRUDPropertyBookingEngineConfig(PropertyBookingEngineConfig)

