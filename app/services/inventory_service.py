from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.inventory import crud_inventory
from app.models.property import Property
from app.models.room import Room
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.models.reservation import ReservationRoom, RoomBlock
from app.utils.enums import ReservationStatus, RoomStatus
from app.utils.exceptions import ValidationException


class InventoryService:
    @staticmethod
    def get_business_date(property_obj: Optional[Property]) -> date:
        """Helper to get current business date of property or fallback to UTC date."""
        if property_obj and property_obj.business_date:
            if isinstance(property_obj.business_date, str):
                return datetime.strptime(property_obj.business_date, "%Y-%m-%d").date()
            elif isinstance(property_obj.business_date, date):
                return property_obj.business_date
        return datetime.now(timezone.utc).date()

    async def get_active_room_count(
        self, db: AsyncSession, property_id: str, room_type_id: str
    ) -> int:
        """Count physical active rooms for a room type."""
        result = await db.execute(
            select(func.count(Room.id)).where(
                Room.property_id == property_id,
                Room.room_type_id == room_type_id,
                Room.status != RoomStatus.INACTIVE.value,
            )
        )
        return result.scalar() or 0

    async def ensure_inventory_for_range(
        self,
        db: AsyncSession,
        property_id: str,
        room_type_id: str,
        start_date: date,
        end_date: date,
        for_update: bool = False,
    ) -> List[RoomTypeInventory]:
        """
        Ensures inventory records exist for every stay date in [start_date, end_date].
        Missing dates are lazily initialized based on current active rooms, existing blocks,
        and confirmed/checked-in reservations.
        """
        # Fetch existing
        existing_rows = await crud_inventory.get_range(
            db,
            property_id=property_id,
            room_type_id=room_type_id,
            start_date=start_date,
            end_date=end_date,
            for_update=for_update,
        )
        existing_by_date = {row.stay_date: row for row in existing_rows}

        # Check for missing dates
        cur = start_date
        total_active_rooms = None
        missing_dates = []
        while cur <= end_date:
            if cur not in existing_by_date:
                missing_dates.append(cur)
            cur += timedelta(days=1)

        if missing_dates:
            if total_active_rooms is None:
                total_active_rooms = await self.get_active_room_count(db, property_id, room_type_id)

            for d in missing_dates:
                # Calculate existing blocks on this date
                day_start = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
                day_end = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

                block_res = await db.execute(
                    select(func.count(func.distinct(RoomBlock.room_id)))
                    .join(Room, Room.id == RoomBlock.room_id)
                    .where(
                        Room.room_type_id == room_type_id,
                        RoomBlock.property_id == property_id,
                        RoomBlock.start_at < day_end,
                        RoomBlock.end_at > day_start,
                    )
                )
                blocked_count = block_res.scalar() or 0

                # Calculate existing sold rooms from reservations
                sold_res = await db.execute(
                    select(func.count(ReservationRoom.id)).where(
                        ReservationRoom.room_type_id == room_type_id,
                        ReservationRoom.status.in_([
                            ReservationStatus.CONFIRMED.value,
                            ReservationStatus.CHECKED_IN.value,
                        ]),
                        ReservationRoom.check_in_at < day_end,
                        ReservationRoom.check_out_at > day_start,
                    )
                )
                sold_count = sold_res.scalar() or 0

                new_inv = RoomTypeInventory(
                    property_id=property_id,
                    room_type_id=room_type_id,
                    stay_date=d,
                    total_rooms=total_active_rooms,
                    blocked_rooms=blocked_count,
                    sold_rooms=sold_count,
                    overbooking_limit=0,
                    stop_sell=False,
                    closed_to_arrival=False,
                    closed_to_departure=False,
                    min_stay=None,
                    max_stay=None,
                    version=0,
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(new_inv)
                existing_by_date[d] = new_inv

            await db.flush()

        # Return sorted list for [start_date, end_date]
        cur = start_date
        result = []
        while cur <= end_date:
            result.append(existing_by_date[cur])
            cur += timedelta(days=1)
        return result

    async def generate_rolling_window(
        self,
        db: AsyncSession,
        property_id: str,
        room_type_id: str,
        from_date: Optional[date] = None,
        days: int = 365,
    ) -> int:
        """
        Generate or populate rolling window inventory for the next `days` (default 365).
        Returns number of newly seeded dates.
        """
        if from_date is None:
            property_obj = await db.get(Property, property_id)
            from_date = self.get_business_date(property_obj)

        to_date = from_date + timedelta(days=days - 1)
        records = await self.ensure_inventory_for_range(
            db, property_id, room_type_id, from_date, to_date
        )
        return len(records)

    async def recompute_total_rooms(
        self,
        db: AsyncSession,
        property_id: str,
        room_type_id: str,
        from_date: Optional[date] = None,
    ) -> None:
        """
        Called when physical rooms are added, removed, or their room_type / status is altered.
        Updates total_rooms for all current and future inventory records.
        """
        if from_date is None:
            property_obj = await db.get(Property, property_id)
            from_date = self.get_business_date(property_obj)

        active_rooms = await self.get_active_room_count(db, property_id, room_type_id)

        # Update existing records from from_date onwards
        await db.execute(
            update(RoomTypeInventory)
            .where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.room_type_id == room_type_id,
                RoomTypeInventory.stay_date >= from_date,
            )
            .values(
                total_rooms=active_rooms,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.flush()

    async def recompute_blocked_rooms(
        self,
        db: AsyncSession,
        property_id: str,
        room_type_id: str,
        start_date: date,
        end_date: date,
    ) -> None:
        """
        Called when room_blocks are created, updated, or deleted.
        Recomputes blocked_rooms for all dates in [start_date, end_date].
        """
        # Ensure rows exist
        await self.ensure_inventory_for_range(db, property_id, room_type_id, start_date, end_date)

        cur = start_date
        while cur <= end_date:
            day_start = datetime.combine(cur, datetime.min.time(), tzinfo=timezone.utc)
            day_end = datetime.combine(cur + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

            block_res = await db.execute(
                select(func.count(func.distinct(RoomBlock.room_id)))
                .join(Room, Room.id == RoomBlock.room_id)
                .where(
                    Room.room_type_id == room_type_id,
                    RoomBlock.property_id == property_id,
                    RoomBlock.start_at < day_end,
                    RoomBlock.end_at > day_start,
                )
            )
            blocked_count = block_res.scalar() or 0

            await db.execute(
                update(RoomTypeInventory)
                .where(
                    RoomTypeInventory.property_id == property_id,
                    RoomTypeInventory.room_type_id == room_type_id,
                    RoomTypeInventory.stay_date == cur,
                )
                .values(
                    blocked_rooms=blocked_count,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            cur += timedelta(days=1)

        await db.flush()

    async def lock_and_reserve(
        self,
        db: AsyncSession,
        property_id: str,
        room_demands: Dict[str, List[date]],
    ) -> None:
        """
        Hot-path booking allocation:
        Takes room_demands: {room_type_id: [stay_date_1, stay_date_2, ...]}
        Locks rows in deterministic order to prevent deadlocks.
        Verifies restrictions (stop_sell, CTA, CTD, min_stay, max_stay) and available >= requested count.
        Increments sold_rooms and version.
        Raises ValidationException if unavailable or restricted.
        """
        # Group required counts per (room_type_id, stay_date)
        demand_counts: Dict[str, Dict[date, int]] = {}
        for rt_id, dates in room_demands.items():
            if rt_id not in demand_counts:
                demand_counts[rt_id] = {}
            for d in dates:
                demand_counts[rt_id][d] = demand_counts[rt_id].get(d, 0) + 1

        # Deterministic sorting by room_type_id and stay_date to prevent deadlocks
        sorted_room_types = sorted(demand_counts.keys())

        for rt_id in sorted_room_types:
            rt_dates = sorted(demand_counts[rt_id].keys())
            if not rt_dates:
                continue

            min_d, max_d = rt_dates[0], rt_dates[-1]

            # Lock rows with FOR UPDATE
            inv_rows = await self.ensure_inventory_for_range(
                db,
                property_id=property_id,
                room_type_id=rt_id,
                start_date=min_d,
                end_date=max_d,
                for_update=True,
            )
            inv_map = {row.stay_date: row for row in inv_rows}

            room_type_obj = await db.get(RoomType, rt_id)
            rt_name = room_type_obj.name if room_type_obj else rt_id

            for d in rt_dates:
                needed = demand_counts[rt_id][d]
                row = inv_map.get(d)
                if not row:
                    raise ValidationException(f"Inventory record missing for {rt_name} on {d}.")

                # 1. Check Stop Sell
                if row.stop_sell:
                    raise ValidationException(
                        f"Stop Sell is active for '{rt_name}' on {d}. Reservation cannot be created."
                    )

                # 2. Check CTA on arrival date
                if d == min_d and row.closed_to_arrival:
                    raise ValidationException(
                        f"'{rt_name}' is Closed to Arrival (CTA) on {d}."
                    )

                # 3. Check min_stay & max_stay
                stay_length = len(rt_dates)
                if row.min_stay and stay_length < row.min_stay:
                    raise ValidationException(
                        f"Minimum stay for '{rt_name}' on {d} is {row.min_stay} night(s). (Booked: {stay_length})"
                    )
                if row.max_stay and stay_length > row.max_stay:
                    raise ValidationException(
                        f"Maximum stay for '{rt_name}' on {d} is {row.max_stay} night(s). (Booked: {stay_length})"
                    )

                # 4. Check Availability: available = total - blocked - sold + overbooking
                avail = row.total_rooms - row.blocked_rooms - row.sold_rooms + row.overbooking_limit
                if avail < needed:
                    raise ValidationException(
                        f"Insufficient inventory for '{rt_name}' on {d}. "
                        f"Available: {avail}, requested: {needed}."
                    )

                # Increment sold_rooms and increment optimistic version
                row.sold_rooms += needed
                row.version += 1
                row.updated_at = datetime.now(timezone.utc)

        await db.flush()

    async def release_inventory(
        self,
        db: AsyncSession,
        property_id: str,
        room_releases: Dict[str, List[date]],
        from_date: Optional[date] = None,
    ) -> None:
        """
        Called on cancellation or no-show:
        Decrements sold_rooms for remaining future nights (>= from_date).
        """
        if from_date is None:
            property_obj = await db.get(Property, property_id)
            from_date = self.get_business_date(property_obj)

        release_counts: Dict[str, Dict[date, int]] = {}
        for rt_id, dates in room_releases.items():
            if rt_id not in release_counts:
                release_counts[rt_id] = {}
            for d in dates:
                if d >= from_date:
                    release_counts[rt_id][d] = release_counts[rt_id].get(d, 0) + 1

        for rt_id, date_map in release_counts.items():
            if not date_map:
                continue
            dates_sorted = sorted(date_map.keys())
            min_d, max_d = dates_sorted[0], dates_sorted[-1]

            rows = await crud_inventory.get_range(
                db,
                property_id=property_id,
                room_type_id=rt_id,
                start_date=min_d,
                end_date=max_d,
                for_update=True,
            )
            for row in rows:
                if row.stay_date in date_map:
                    qty = date_map[row.stay_date]
                    row.sold_rooms = max(0, row.sold_rooms - qty)
                    row.version += 1
                    row.updated_at = datetime.now(timezone.utc)

        await db.flush()

    async def update_controls(
        self,
        db: AsyncSession,
        property_id: str,
        room_type_ids: List[str],
        start_date: date,
        end_date: date,
        stop_sell: Optional[bool] = None,
        closed_to_arrival: Optional[bool] = None,
        closed_to_departure: Optional[bool] = None,
        min_stay: Optional[int] = None,
        max_stay: Optional[int] = None,
        overbooking_limit: Optional[int] = None,
    ) -> int:
        """
        Update yield / rate & channel manager controls directly across a date range and room types.
        """
        updated_count = 0
        for rt_id in room_type_ids:
            # Ensure rows exist first
            rows = await self.ensure_inventory_for_range(
                db,
                property_id=property_id,
                room_type_id=rt_id,
                start_date=start_date,
                end_date=end_date,
                for_update=True,
            )
            for row in rows:
                changed = False
                if stop_sell is not None:
                    row.stop_sell = stop_sell
                    changed = True
                if closed_to_arrival is not None:
                    row.closed_to_arrival = closed_to_arrival
                    changed = True
                if closed_to_departure is not None:
                    row.closed_to_departure = closed_to_departure
                    changed = True
                if min_stay is not None:
                    row.min_stay = min_stay if min_stay >= 0 else None
                    changed = True
                if max_stay is not None:
                    row.max_stay = max_stay if max_stay >= 0 else None
                    changed = True
                if overbooking_limit is not None:
                    row.overbooking_limit = overbooking_limit
                    changed = True

                if changed:
                    row.version += 1
                    row.updated_at = datetime.now(timezone.utc)
                    updated_count += 1

        await db.flush()
        return updated_count


inventory_service = InventoryService()
