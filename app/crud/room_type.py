from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.room_type import RoomType
from app.schemas.room_type import RoomTypeCreate, RoomTypeUpdate


class CRUDRoomType(CRUDBase[RoomType, RoomTypeCreate, RoomTypeUpdate]):
    async def get_by_property(
        self, db: AsyncSession, *, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[RoomType]:
        result = await db.execute(
            select(RoomType)
            .where(RoomType.property_id == property_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, property_id: str, code: str
    ) -> Optional[RoomType]:
        result = await db.execute(
            select(RoomType).where(
                RoomType.property_id == property_id,
                RoomType.code == code,
            )
        )
        return result.scalars().first()


crud_room_type = CRUDRoomType(RoomType)
