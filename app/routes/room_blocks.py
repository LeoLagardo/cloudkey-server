from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.room_block import RoomBlockCreate, RoomBlockUpdate, RoomBlockResponse
from app.services.room_block_service import room_block_service

router = APIRouter(prefix="/room-blocks", tags=["Room Blocks"])


@router.post("", response_model=RoomBlockResponse, status_code=status.HTTP_201_CREATED)
async def create_room_block(
    payload: RoomBlockCreate,
    property_id: str = Query(..., description="Property ID to create room block for"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new room block (OOO/maintenance/hold) and recomputes blocked inventory."""
    return await room_block_service.create_room_block(
        db,
        property_id=property_id,
        block_in=payload,
        current_user_id=current_user.id,
    )


@router.get("", response_model=List[RoomBlockResponse])
async def list_room_blocks(
    property_id: str = Query(..., description="Property ID"),
    room_id: Optional[str] = Query(None, description="Optional room filter"),
    from_date: Optional[datetime] = Query(None, description="Filter blocks starting after"),
    to_date: Optional[datetime] = Query(None, description="Filter blocks ending before"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List active room blocks for a property."""
    return await room_block_service.list_by_property(
        db,
        property_id=property_id,
        room_id=room_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.put("/{block_id}", response_model=RoomBlockResponse)
async def update_room_block(
    block_id: str,
    payload: RoomBlockUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a room block and synchronize blocked inventory."""
    return await room_block_service.update_room_block(
        db,
        block_id=block_id,
        block_in=payload,
    )


@router.delete("/{block_id}", response_model=RoomBlockResponse)
async def delete_room_block(
    block_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Remove a room block and release blocked inventory."""
    return await room_block_service.delete_room_block(
        db,
        block_id=block_id,
    )
