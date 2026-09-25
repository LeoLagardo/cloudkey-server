from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.property_user import PropertyUser
from app.schemas.property_user import PropertyUserCreate, PropertyUserUpdate


class CRUDPropertyUser(CRUDBase[PropertyUser, PropertyUserCreate, PropertyUserUpdate]):
    async def get_by_property_and_user(
        self, db: AsyncSession, *, property_id: str, user_id: str
    ) -> Optional[PropertyUser]:
        result = await db.execute(
            select(PropertyUser).where(
                PropertyUser.property_id == property_id,
                PropertyUser.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_by_property(
        self, db: AsyncSession, *, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[PropertyUser]:
        result = await db.execute(
            select(PropertyUser)
            .where(PropertyUser.property_id == property_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_property_user = CRUDPropertyUser(PropertyUser)
