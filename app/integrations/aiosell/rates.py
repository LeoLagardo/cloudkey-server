from datetime import date
from typing import Any, Dict, List, Optional
import logging
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.aiosell.client import AiosellClient
from app.integrations.aiosell.mappings import (
    get_aiosell_client_for_property,
    resolve_aiosell_rateplan_code,
    resolve_aiosell_room_code,
)
from app.integrations.aiosell.schemas import (
    AiosellDataFetchRequest,
    AiosellStandardResponse,
    RateItem,
    RatePushRequest,
    RateUpdateBlock,
)
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate

logger = logging.getLogger(__name__)


async def push_property_rates(
    db: AsyncSession,
    property_id: str,
    start_date: date,
    end_date: date,
    rate_plan_ids: Optional[List[str]] = None,
) -> Optional[AiosellStandardResponse]:
    """
    Push nightly rates from CloudKey PMS to Aiosell for a given date range.
    """
    client, config = await get_aiosell_client_for_property(db, property_id)
    if not config.sync_rates:
        logger.info(f"[Aiosell] Rate sync is disabled for property {property_id}")
        return None

    # Query active rate plans and their rates
    stmt = (
        select(RatePlan)
        .options(selectinload(RatePlan.rates))
        .where(
            RatePlan.property_id == property_id,
            RatePlan.status == "ACTIVE",
            RatePlan.booking_type == "NIGHTLY",
        )
    )
    if rate_plan_ids:
        stmt = stmt.where(RatePlan.id.in_(rate_plan_ids))

    result = await db.execute(stmt)
    rate_plans = result.scalars().all()

    if not rate_plans:
        logger.warning(f"[Aiosell] No active nightly rate plans found for property {property_id}")
        return None

    rate_items: List[RateItem] = []
    for rp in rate_plans:
        try:
            room_code = await resolve_aiosell_room_code(db, property_id, rp.room_type_id)
            rateplan_code = await resolve_aiosell_rateplan_code(db, property_id, rp.id)

            # Find matching nightly rate
            nightly_rate = next(
                (r for r in rp.rates if r.duration_unit == "NIGHT"),
                None
            )
            if nightly_rate and nightly_rate.price is not None:
                rate_items.append(
                    RateItem(
                        roomCode=room_code,
                        rateplanCode=rateplan_code,
                        rate=float(nightly_rate.price),
                    )
                )
        except Exception as e:
            logger.warning(f"[Aiosell] Skipping unmapped rate_plan {rp.id} ({rp.code}): {e}")

    if not rate_items:
        logger.warning(f"[Aiosell] No valid mapped rates found to push for property {property_id}")
        return None

    # Group into an update block spanning the requested window
    updates = [
        RateUpdateBlock(
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            rates=rate_items,
        )
    ]

    payload = RatePushRequest(
        hotelCode=config.aiosell_hotel_code,
        updates=updates,
    )

    logger.info(
        f"[Aiosell] Pushing rates for {len(rate_items)} rate plans to hotelCode {config.aiosell_hotel_code} ({start_date} to {end_date})"
    )
    return await client.push_rates(payload, pms_slug=config.pms_slug)


async def fetch_remote_rates(
    db: AsyncSession,
    property_id: str,
    start_date: date,
    end_date: date,
) -> Any:
    """Fetch current rates from Aiosell Channel Manager."""
    client, config = await get_aiosell_client_for_property(db, property_id)
    payload = AiosellDataFetchRequest(
        type="rates",
        hotelCode=config.aiosell_hotel_code,
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
    )
    return await client.fetch_data(payload, pms_slug=config.pms_slug)
