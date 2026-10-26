from datetime import date
from typing import Dict, List, Optional
import logging
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.aiosell.client import AiosellClient
from app.integrations.aiosell.mappings import (
    get_aiosell_client_for_property,
    resolve_aiosell_rateplan_code,
    resolve_aiosell_room_code,
)
from app.integrations.aiosell.schemas import (
    AiosellRestrictions,
    AiosellStandardResponse,
    InventoryRestrictionsPushRequest,
    InventoryRestrictionsUpdateBlock,
    RateRestrictionsPushRequest,
    RateRestrictionsUpdateBlock,
    RateRestrictionItem,
    RoomRestrictionItem,
)
from app.models.room_type_inventory import RoomTypeInventory

logger = logging.getLogger(__name__)


async def push_property_restrictions(
    db: AsyncSession,
    property_id: str,
    start_date: date,
    end_date: date,
    channels: Optional[List[str]] = None,
    room_type_ids: Optional[List[str]] = None,
) -> Optional[AiosellStandardResponse]:
    """
    Push room-level inventory restrictions (stop-sell, CTA, CTD, min/max stay) to Aiosell.
    Endpoint: POST /update/{pms}
    """
    client, config = await get_aiosell_client_for_property(db, property_id)
    if not config.sync_restrictions:
        logger.info(f"[Aiosell] Restrictions sync is disabled for property {property_id}")
        return None

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
        return None

    date_to_items: Dict[date, List[RoomRestrictionItem]] = defaultdict(list)
    for inv in records:
        try:
            room_code = await resolve_aiosell_room_code(db, property_id, inv.room_type_id)
            restr = AiosellRestrictions(
                stopSell=inv.stop_sell,
                closeOnArrival=inv.closed_to_arrival,
                closeOnDeparture=inv.closed_to_departure,
                minimumStay=inv.min_stay or 1,
                maximumStay=inv.max_stay,
            )
            date_to_items[inv.stay_date].append(
                RoomRestrictionItem(roomCode=room_code, restrictions=restr)
            )
        except Exception as e:
            logger.warning(f"[Aiosell] Skipping unmapped room_type {inv.room_type_id} for restrictions: {e}")

    if not date_to_items:
        return None

    updates: List[InventoryRestrictionsUpdateBlock] = []
    for stay_dt, room_items in sorted(date_to_items.items()):
        if room_items:
            dt_str = stay_dt.isoformat()
            updates.append(
                InventoryRestrictionsUpdateBlock(
                    startDate=dt_str,
                    endDate=dt_str,
                    rooms=room_items,
                )
            )

    payload = InventoryRestrictionsPushRequest(
        hotelCode=config.aiosell_hotel_code,
        toChannels=channels or [],
        updates=updates,
    )

    logger.info(
        f"[Aiosell] Pushing room restrictions to hotelCode {config.aiosell_hotel_code} ({len(updates)} blocks)"
    )
    return await client.push_inventory_restrictions(payload, pms_slug=config.pms_slug)


async def push_rate_plan_restrictions(
    db: AsyncSession,
    property_id: str,
    room_type_id: str,
    rate_plan_id: str,
    start_date: date,
    end_date: date,
    restrictions: AiosellRestrictions,
    channels: Optional[List[str]] = None,
) -> Optional[AiosellStandardResponse]:
    """
    Push rate-plan-level restrictions to Aiosell.
    Endpoint: POST /update-rates/{pms}
    """
    client, config = await get_aiosell_client_for_property(db, property_id)
    if not config.sync_restrictions:
        return None

    room_code = await resolve_aiosell_room_code(db, property_id, room_type_id)
    rateplan_code = await resolve_aiosell_rateplan_code(db, property_id, rate_plan_id)

    item = RateRestrictionItem(
        roomCode=room_code,
        rateplanCode=rateplan_code,
        restrictions=restrictions,
    )

    update_block = RateRestrictionsUpdateBlock(
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        rates=[item],
    )

    payload = RateRestrictionsPushRequest(
        hotelCode=config.aiosell_hotel_code,
        toChannels=channels or [],
        updates=[update_block],
    )

    return await client.push_rate_restrictions(payload, pms_slug=config.pms_slug)
