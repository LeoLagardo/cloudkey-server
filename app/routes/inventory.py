from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.models.room_type import RoomType
from app.schemas.inventory import (
    InventoryItemResponse,
    InventoryControlsUpdate,
    InventorySyncResponse,
)
from app.crud.inventory import crud_inventory
from app.services.inventory_service import inventory_service
from app.utils.exceptions import ValidationException

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("", response_model=List[InventoryItemResponse])
async def get_inventory_grid(
    property_id: str = Query(..., description="Property ID"),
    start_date: date = Query(..., description="Start stay date"),
    end_date: date = Query(..., description="End stay date"),
    room_type_id: Optional[str] = Query(None, description="Optional room type filter"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get inventory grid with computed availability and channel controls for a property and date range.
    Lazily generates missing dates if necessary.
    """
    if start_date > end_date:
        raise ValidationException("start_date cannot be after end_date.")

    # Determine room types
    if room_type_id:
        room_type_ids = [room_type_id]
    else:
        rt_result = await db.execute(
            select(RoomType.id).where(RoomType.property_id == property_id)
        )
        room_type_ids = list(rt_result.scalars().all())

    # Ensure inventory exists for all room types in the range
    for rt_id in room_type_ids:
        await inventory_service.ensure_inventory_for_range(
            db,
            property_id=property_id,
            room_type_id=rt_id,
            start_date=start_date,
            end_date=end_date,
        )

    grid = await crud_inventory.get_grid(
        db,
        property_id=property_id,
        start_date=start_date,
        end_date=end_date,
        room_type_ids=room_type_ids,
    )
    return grid


@router.patch("/controls", status_code=status.HTTP_200_OK)
async def update_inventory_controls(
    payload: InventoryControlsUpdate,
    property_id: str = Query(..., description="Property ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Directly update restrictions (stop_sell, CTA, CTD, min_stay, max_stay, overbooking_limit)
    across a date range and list of room types.
    """
    if payload.start_date > payload.end_date:
        raise ValidationException("start_date cannot be after end_date.")

    updated_count = await inventory_service.update_controls(
        db,
        property_id=property_id,
        room_type_ids=payload.room_type_ids,
        start_date=payload.start_date,
        end_date=payload.end_date,
        stop_sell=payload.stop_sell,
        closed_to_arrival=payload.closed_to_arrival,
        closed_to_departure=payload.closed_to_departure,
        min_stay=payload.min_stay,
        max_stay=payload.max_stay,
        overbooking_limit=payload.overbooking_limit,
    )
    await db.commit()
    return {"message": "Inventory controls updated successfully.", "updated_records": updated_count}


@router.post("/sync", response_model=InventorySyncResponse)
async def sync_inventory_rolling_window(
    property_id: str = Query(..., description="Property ID"),
    days: int = Query(365, ge=1, le=730, description="Rolling window days to populate"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Populate or synchronize 365-day rolling inventory for all room types in this property.
    """
    rt_result = await db.execute(
        select(RoomType.id).where(RoomType.property_id == property_id)
    )
    room_type_ids = list(rt_result.scalars().all())

    total_synced = 0
    for rt_id in room_type_ids:
        synced = await inventory_service.generate_rolling_window(
            db, property_id=property_id, room_type_id=rt_id, days=days
        )
        total_synced += synced

    await db.commit()
    return InventorySyncResponse(
        property_id=property_id,
        synced_days=days,
        message=f"Successfully synchronized {days} rolling days of inventory across {len(room_type_ids)} room type(s).",
    )
