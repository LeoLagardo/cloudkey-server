from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.room import Room
from app.schemas.room import RoomCreate, RoomUpdate


class CRUDRoom(CRUDBase[Room, RoomCreate, RoomUpdate]):
    async def get_by_property(
        self, db: AsyncSession, *, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[Room]:
        result = await db.execute(
            select(Room)
            .where(Room.property_id == property_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_number(
        self, db: AsyncSession, *, property_id: str, room_number: str
    ) -> Optional[Room]:
        result = await db.execute(
            select(Room).where(
                Room.property_id == property_id,
                Room.room_number == room_number,
            )
        )
        return result.scalars().first()

    async def get_by_room_type(
        self, db: AsyncSession, *, room_type_id: str
    ) -> List[Room]:
        result = await db.execute(
            select(Room).where(Room.room_type_id == room_type_id)
        )
        return list(result.scalars().all())


crud_room = CRUDRoom(Room)
