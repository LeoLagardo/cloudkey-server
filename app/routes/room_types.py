from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.room_type import (
    RoomTypeCreate,
    RoomTypeUpdate,
    RoomTypeResponse,
)
from app.services.room_type_service import room_type_service

router = APIRouter(prefix="/room-types", tags=["Room Types"])


@router.get("", response_model=List[RoomTypeResponse])
async def list_room_types(
    property_id: str = Query(..., description="Property ID to filter room types"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List room types for a property."""
    return await room_type_service.list_by_property(
        db, property_id=property_id, skip=skip, limit=limit
    )


@router.post("", response_model=RoomTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_room_type(
    rt_in: RoomTypeCreate,
    property_id: str = Query(..., description="Property ID to assign room type to"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new room type."""
    return await room_type_service.create_room_type(
        db, property_id=property_id, rt_in=rt_in
    )


@router.get("/{room_type_id}", response_model=RoomTypeResponse)
async def get_room_type(
    room_type_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a room type by ID."""
    return await room_type_service.get_by_id(db, room_type_id=room_type_id)


@router.put("/{room_type_id}", response_model=RoomTypeResponse)
async def update_room_type(
    room_type_id: str,
    rt_in: RoomTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a room type."""
    return await room_type_service.update_room_type(
        db, room_type_id=room_type_id, rt_in=rt_in
    )


@router.delete("/{room_type_id}", response_model=RoomTypeResponse)
async def delete_room_type(
    room_type_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a room type."""
    return await room_type_service.delete_room_type(db, room_type_id=room_type_id)
