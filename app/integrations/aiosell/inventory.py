from datetime import date
from typing import Any, Dict, List, Optional
import logging
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.aiosell.client import AiosellClient
from app.integrations.aiosell.exceptions import AiosellConfigError
from app.integrations.aiosell.mappings import (
    get_aiosell_client_for_property,
    resolve_aiosell_room_code,
)
from app.integrations.aiosell.schemas import (
    AiosellDataFetchRequest,
    AiosellStandardResponse,
    InventoryPushRequest,
    InventoryUpdateBlock,
    RoomInventoryItem,
)
from app.models.room_type_inventory import RoomTypeInventory

logger = logging.getLogger(__name__)


async def push_property_inventory(
    db: AsyncSession,
    property_id: str,
    start_date: date,
    end_date: date,
    room_type_ids: Optional[List[str]] = None,
) -> Optional[AiosellStandardResponse]:
    """
    Push room availability from CloudKey PMS to Aiosell for a given date range.
    Queries RoomTypeInventory table and translates room types to Aiosell room codes.
    """
    client, config = await get_aiosell_client_for_property(db, property_id)
    if not config.sync_inventory:
        logger.info(f"[Aiosell] Inventory sync is disabled for property {property_id}")
        return None

    # Query local inventory records
    stmt = select(RoomTypeInventory).where(
        RoomTypeInventory.property_id == property_id,
        RoomTypeInventory.stay_date >= start_date,
        RoomTypeInventory.stay_date <= end_date,
    )
    if room_type_ids:
        stmt = stmt.where(RoomTypeInventory.room_type_id.in_(room_type_ids))

    result = await db.execute(stmt)
    records = result.scalars().all()

    if not records:
        logger.warning(
            f"[Aiosell] No inventory records found for property {property_id} between {start_date} and {end_date}"
        )
        return None

    # Group inventory by stay_date
    date_to_rooms: Dict[date, List[RoomInventoryItem]] = defaultdict(list)
    for inv in records:
        try:
            room_code = await resolve_aiosell_room_code(db, property_id, inv.room_type_id)
            available_count = max(0, inv.available)
            date_to_rooms[inv.stay_date].append(
                RoomInventoryItem(roomCode=room_code, available=available_count)
            )
        except Exception as e:
            logger.warning(f"[Aiosell] Skipping unmapped room_type {inv.room_type_id}: {e}")

    if not date_to_rooms:
        return None

    # Build updates (per day)
    updates: List[InventoryUpdateBlock] = []
    for stay_dt, room_items in sorted(date_to_rooms.items()):
        if room_items:
            dt_str = stay_dt.isoformat()
            updates.append(
                InventoryUpdateBlock(
                    startDate=dt_str,
                    endDate=dt_str,
                    rooms=room_items,
                )
            )

    payload = InventoryPushRequest(
        hotelCode=config.aiosell_hotel_code,
        updates=updates,
    )

    logger.info(
        f"[Aiosell] Pushing inventory to hotelCode {config.aiosell_hotel_code} for {len(updates)} date blocks"
    )
    return await client.push_inventory(payload, pms_slug=config.pms_slug)


async def fetch_remote_inventory(
    db: AsyncSession,
    property_id: str,
    start_date: date,
    end_date: date,
) -> Any:
    """Fetch current inventory status from Aiosell Channel Manager."""
    client, config = await get_aiosell_client_for_property(db, property_id)
    payload = AiosellDataFetchRequest(
        type="inventory",
        hotelCode=config.aiosell_hotel_code,
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
    )
    return await client.fetch_data(payload, pms_slug=config.pms_slug)
