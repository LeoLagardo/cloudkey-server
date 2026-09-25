from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.property import Property
from app.schemas.property import PropertyCreate, PropertyUpdate


class CRUDProperty(CRUDBase[Property, PropertyCreate, PropertyUpdate]):
    async def get_by_organization(
        self, db: AsyncSession, *, organization_id: str, skip: int = 0, limit: int = 100
    ) -> List[Property]:
        result = await db.execute(
            select(Property)
            .where(Property.organization_id == organization_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, organization_id: str, code: str
    ) -> Optional[Property]:
        result = await db.execute(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.code == code,
            )
        )
        return result.scalars().first()


crud_property = CRUDProperty(Property)
