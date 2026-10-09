from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from app.models.reservation import RoomBlock, ReservationRoom
from app.schemas.room_block import RoomBlockCreate, RoomBlockUpdate
from app.services.inventory_service import inventory_service
from app.utils.exceptions import EntityNotFoundException, ValidationException
from app.utils.enums import ReservationStatus, RoomStatus, RoomBlockType


class RoomBlockService:
    async def get_by_id(self, db: AsyncSession, block_id: str) -> RoomBlock:
        stmt = (
            select(RoomBlock)
            .options(selectinload(RoomBlock.room))
            .where(RoomBlock.id == block_id)
        )
        res = await db.execute(stmt)
        block = res.scalar_one_or_none()
        if not block:
            raise EntityNotFoundException("RoomBlock", block_id)
        return block

    async def list_by_property(
        self,
        db: AsyncSession,
        property_id: str,
        room_id: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[RoomBlock]:
        query = (
            select(RoomBlock)
            .options(selectinload(RoomBlock.room))
            .where(RoomBlock.property_id == property_id)
        )
        if room_id:
            query = query.where(RoomBlock.room_id == room_id)
        if from_date:
            query = query.where(RoomBlock.end_at >= from_date)
        if to_date:
            query = query.where(RoomBlock.start_at <= to_date)

        query = query.order_by(RoomBlock.start_at.asc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create_room_block(
        self,
        db: AsyncSession,
        property_id: str,
        block_in: RoomBlockCreate,
        current_user_id: Optional[str] = None,
    ) -> RoomBlock:
        room = await db.get(Room, block_in.room_id)
        if not room or room.property_id != property_id:
            raise ValidationException("Room not found or does not belong to this property.")

        if block_in.start_at >= block_in.end_at:
            raise ValidationException("Start date/time must be strictly before end date/time.")

        # Check overlapping active reservations for this physical room
        overlap_res = await db.execute(
            select(ReservationRoom).where(
                ReservationRoom.room_id == block_in.room_id,
                ReservationRoom.status.in_([
                    ReservationStatus.CONFIRMED.value,
                    ReservationStatus.CHECKED_IN.value,
                ]),
                ReservationRoom.check_in_at < block_in.end_at,
                ReservationRoom.check_out_at > block_in.start_at,
            )
        )
        overlap = overlap_res.scalars().first()
        if overlap:
            raise ValidationException(
                f"Room {room.room_number} has an existing reservation overlapping this block period."
            )

        block = RoomBlock(
            property_id=property_id,
            room_id=block_in.room_id,
            block_type=block_in.block_type.value,
            start_at=block_in.start_at,
            end_at=block_in.end_at,
            reason=block_in.reason,
            created_by=current_user_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(block)

        # Synchronize physical room status if block is currently active
        now = datetime.now(timezone.utc)
        if block.start_at <= now <= block.end_at:
            if block.block_type == RoomBlockType.MAINTENANCE.value:
                room.status = RoomStatus.MAINTENANCE.value
            else:
                room.status = RoomStatus.OUT_OF_SERVICE.value

        await db.flush()

        # Recompute inventory blocked_rooms for affected dates
        start_d = block.start_at.date()
        end_d = block.end_at.date()
        await inventory_service.recompute_blocked_rooms(
            db, property_id=property_id, room_type_id=room.room_type_id, start_date=start_d, end_date=end_d
        )
        await db.commit()
        return await self.get_by_id(db, block.id)

    async def update_room_block(
        self,
        db: AsyncSession,
        block_id: str,
        block_in: RoomBlockUpdate,
    ) -> RoomBlock:
        block = await self.get_by_id(db, block_id)
        room = await db.get(Room, block.room_id)
        old_start_d = block.start_at.date()
        old_end_d = block.end_at.date()

        if block_in.block_type is not None:
            block.block_type = block_in.block_type.value
        if block_in.start_at is not None:
            block.start_at = block_in.start_at
        if block_in.end_at is not None:
            block.end_at = block_in.end_at
        if block_in.reason is not None:
            block.reason = block_in.reason

        if block.start_at >= block.end_at:
            raise ValidationException("Start date/time must be strictly before end date/time.")

        # Re-check overlapping active reservations
        overlap_res = await db.execute(
            select(ReservationRoom).where(
                ReservationRoom.room_id == block.room_id,
                ReservationRoom.status.in_([
                    ReservationStatus.CONFIRMED.value,
                    ReservationStatus.CHECKED_IN.value,
                ]),
                ReservationRoom.check_in_at < block.end_at,
                ReservationRoom.check_out_at > block.start_at,
            )
        )
        if overlap_res.scalars().first():
            raise ValidationException(
                f"Room {room.room_number} has an existing reservation overlapping this updated block period."
            )

        now = datetime.now(timezone.utc)
        if block.start_at <= now <= block.end_at:
            if block.block_type == RoomBlockType.MAINTENANCE.value:
                room.status = RoomStatus.MAINTENANCE.value
            else:
                room.status = RoomStatus.OUT_OF_SERVICE.value

        await db.flush()

        new_start_d = block.start_at.date()
        new_end_d = block.end_at.date()
        min_d = min(old_start_d, new_start_d)
        max_d = max(old_end_d, new_end_d)

        await inventory_service.recompute_blocked_rooms(
            db, property_id=block.property_id, room_type_id=room.room_type_id, start_date=min_d, end_date=max_d
        )
        await db.commit()
        return await self.get_by_id(db, block.id)

    async def delete_room_block(
        self,
        db: AsyncSession,
        block_id: str,
    ) -> RoomBlock:
        block = await self.get_by_id(db, block_id)
        room = await db.get(Room, block.room_id)
        prop_id = block.property_id
        rt_id = room.room_type_id
        start_d = block.start_at.date()
        end_d = block.end_at.date()

        # Check if another active block covers today; if none, revert room status to AVAILABLE
        now = datetime.now(timezone.utc)
        rem_res = await db.execute(
            select(RoomBlock).where(
                RoomBlock.room_id == room.id,
                RoomBlock.id != block_id,
                RoomBlock.start_at <= now,
                RoomBlock.end_at >= now,
            )
        )
        if not rem_res.scalars().first():
            if room.status in (RoomStatus.MAINTENANCE.value, RoomStatus.OUT_OF_SERVICE.value):
                room.status = RoomStatus.AVAILABLE.value

        await db.delete(block)
        await db.flush()

        await inventory_service.recompute_blocked_rooms(
            db, property_id=prop_id, room_type_id=rt_id, start_date=start_d, end_date=end_d
        )
        await db.commit()
        return block


room_block_service = RoomBlockService()
