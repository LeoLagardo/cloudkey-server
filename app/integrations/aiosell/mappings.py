from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.aiosell.client import AiosellClient
from app.integrations.aiosell.exceptions import AiosellConfigError, AiosellMappingError
from app.models.channel_manager import (
    AiosellPropertyConfig,
    AiosellRatePlanMapping,
    AiosellRoomTypeMapping,
)
from app.models.room_type import RoomType
from app.models.rate_plan import RatePlan


async def get_property_config(
    db: AsyncSession,
    property_id: str,
) -> Optional[AiosellPropertyConfig]:
    """Retrieve Aiosell configuration for a CloudKey property."""
    stmt = select(AiosellPropertyConfig).where(
        AiosellPropertyConfig.property_id == property_id,
        AiosellPropertyConfig.is_active == True,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_property_config_by_hotel_code(
    db: AsyncSession,
    hotel_code: str,
) -> Optional[AiosellPropertyConfig]:
    """Retrieve Aiosell configuration by Aiosell hotelCode."""
    stmt = select(AiosellPropertyConfig).where(
        AiosellPropertyConfig.aiosell_hotel_code == hotel_code,
        AiosellPropertyConfig.is_active == True,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_aiosell_client_for_property(
    db: AsyncSession,
    property_id: str,
) -> Tuple[AiosellClient, AiosellPropertyConfig]:
    """Build an authenticated AiosellClient using the property's stored credentials."""
    config = await get_property_config(db, property_id)
    if not config:
        raise AiosellConfigError(f"No active Aiosell configuration found for property {property_id}")

    client = AiosellClient(
        pms_slug=config.pms_slug,
    )
    return client, config


async def resolve_aiosell_room_code(
    db: AsyncSession,
    property_id: str,
    room_type_id: str,
) -> str:
    """Map CloudKey room_type_id to Aiosell roomCode."""
    stmt = select(AiosellRoomTypeMapping.aiosell_room_code).where(
        AiosellRoomTypeMapping.property_id == property_id,
        AiosellRoomTypeMapping.room_type_id == room_type_id,
    )
    result = await db.execute(stmt)
    code = result.scalar_one_or_none()
    if not code:
        raise AiosellMappingError(
            f"No Aiosell room code mapped for CloudKey room_type {room_type_id} at property {property_id}"
        )
    return code


async def resolve_cloudkey_room_type_id(
    db: AsyncSession,
    property_id: str,
    aiosell_room_code: str,
) -> Optional[str]:
    """Map Aiosell roomCode to CloudKey room_type_id."""
    stmt = select(AiosellRoomTypeMapping.room_type_id).where(
        AiosellRoomTypeMapping.property_id == property_id,
        AiosellRoomTypeMapping.aiosell_room_code == aiosell_room_code,
    )
    result = await db.execute(stmt)
    room_type_id = result.scalar_one_or_none()

    if not room_type_id:
        # Fallback heuristic: check if room_types.code matches directly
        stmt_fallback = select(RoomType.id).where(
            RoomType.property_id == property_id,
            RoomType.code == aiosell_room_code,
        )
        res_fb = await db.execute(stmt_fallback)
        room_type_id = res_fb.scalar_one_or_none()

    return room_type_id


async def resolve_aiosell_rateplan_code(
    db: AsyncSession,
    property_id: str,
    rate_plan_id: str,
) -> str:
    """Map CloudKey rate_plan_id to Aiosell rateplanCode."""
    stmt = select(AiosellRatePlanMapping.aiosell_rateplan_code).where(
        AiosellRatePlanMapping.property_id == property_id,
        AiosellRatePlanMapping.rate_plan_id == rate_plan_id,
    )
    result = await db.execute(stmt)
    code = result.scalar_one_or_none()
    if not code:
        raise AiosellMappingError(
            f"No Aiosell rateplan code mapped for CloudKey rate_plan {rate_plan_id} at property {property_id}"
        )
    return code


async def resolve_cloudkey_rate_plan_id(
    db: AsyncSession,
    property_id: str,
    aiosell_rateplan_code: str,
) -> Optional[str]:
    """Map Aiosell rateplanCode to CloudKey rate_plan_id."""
    stmt = select(AiosellRatePlanMapping.rate_plan_id).where(
        AiosellRatePlanMapping.property_id == property_id,
        AiosellRatePlanMapping.aiosell_rateplan_code == aiosell_rateplan_code,
    )
    result = await db.execute(stmt)
    rate_plan_id = result.scalar_one_or_none()

    if not rate_plan_id:
        # Fallback heuristic: check if rate_plans.code matches directly
        stmt_fallback = select(RatePlan.id).where(
            RatePlan.property_id == property_id,
            RatePlan.code == aiosell_rateplan_code,
        )
        res_fb = await db.execute(stmt_fallback)
        rate_plan_id = res_fb.scalar_one_or_none()

    return rate_plan_id


async def set_room_type_mapping(
    db: AsyncSession,
    property_id: str,
    room_type_id: str,
    aiosell_room_code: str,
) -> AiosellRoomTypeMapping:
    """Upsert room type mapping."""
    stmt = select(AiosellRoomTypeMapping).where(
        AiosellRoomTypeMapping.property_id == property_id,
        AiosellRoomTypeMapping.room_type_id == room_type_id,
    )
    result = await db.execute(stmt)
    mapping = result.scalar_one_or_none()
    if mapping:
        mapping.aiosell_room_code = aiosell_room_code
    else:
        mapping = AiosellRoomTypeMapping(
            property_id=property_id,
            room_type_id=room_type_id,
            aiosell_room_code=aiosell_room_code,
        )
        db.add(mapping)
    await db.flush()
    return mapping


async def set_rate_plan_mapping(
    db: AsyncSession,
    property_id: str,
    rate_plan_id: str,
    aiosell_rateplan_code: str,
) -> AiosellRatePlanMapping:
    """Upsert rate plan mapping."""
    stmt = select(AiosellRatePlanMapping).where(
        AiosellRatePlanMapping.property_id == property_id,
        AiosellRatePlanMapping.rate_plan_id == rate_plan_id,
    )
    result = await db.execute(stmt)
    mapping = result.scalar_one_or_none()
    if mapping:
        mapping.aiosell_rateplan_code = aiosell_rateplan_code
    else:
        mapping = AiosellRatePlanMapping(
            property_id=property_id,
            rate_plan_id=rate_plan_id,
            aiosell_rateplan_code=aiosell_rateplan_code,
        )
        db.add(mapping)
    await db.flush()
    return mapping
