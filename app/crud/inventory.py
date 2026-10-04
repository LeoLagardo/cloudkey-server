from datetime import date
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room_type_inventory import RoomTypeInventory


class CRUDInventory:
    async def get_by_date(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        room_type_id: str,
        stay_date: date,
        for_update: bool = False,
    ) -> Optional[RoomTypeInventory]:
        query = select(RoomTypeInventory).where(
            RoomTypeInventory.property_id == property_id,
            RoomTypeInventory.room_type_id == room_type_id,
            RoomTypeInventory.stay_date == stay_date,
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_range(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        room_type_id: str,
        start_date: date,
        end_date: date,
        for_update: bool = False,
    ) -> List[RoomTypeInventory]:
        """Fetch inventory rows for stay dates in [start_date, end_date] ordered by date."""
        query = (
            select(RoomTypeInventory)
            .where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.room_type_id == room_type_id,
                RoomTypeInventory.stay_date >= start_date,
                RoomTypeInventory.stay_date <= end_date,
            )
            .order_by(RoomTypeInventory.stay_date.asc())
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_grid(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        start_date: date,
        end_date: date,
        room_type_ids: Optional[List[str]] = None,
    ) -> List[RoomTypeInventory]:
        """Fetch inventory grid for a property across all or specific room types in date range."""
        conditions = [
            RoomTypeInventory.property_id == property_id,
            RoomTypeInventory.stay_date >= start_date,
            RoomTypeInventory.stay_date <= end_date,
        ]
        if room_type_ids:
            conditions.append(RoomTypeInventory.room_type_id.in_(room_type_ids))

        query = (
            select(RoomTypeInventory)
            .where(and_(*conditions))
            .order_by(RoomTypeInventory.stay_date.asc(), RoomTypeInventory.room_type_id.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_future_by_room_type(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        room_type_id: str,
        from_date: date,
    ) -> List[RoomTypeInventory]:
        """Fetch all inventory records for a room type from from_date onwards."""
        query = (
            select(RoomTypeInventory)
            .where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.room_type_id == room_type_id,
                RoomTypeInventory.stay_date >= from_date,
            )
            .order_by(RoomTypeInventory.stay_date.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())


crud_inventory = CRUDInventory()
