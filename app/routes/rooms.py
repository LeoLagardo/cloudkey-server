from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.room import (
    RoomCreate,
    RoomUpdate,
    RoomResponse,
)
from app.services.room_service import room_service

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.get("", response_model=List[RoomResponse])
async def list_rooms(
    property_id: str = Query(..., description="Property ID to filter rooms"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List physical rooms for a property."""
    return await room_service.list_by_property(
        db, property_id=property_id, skip=skip, limit=limit
    )


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_in: RoomCreate,
    property_id: str = Query(..., description="Property ID to create room in"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new room in a property."""
    return await room_service.create_room(
        db, property_id=property_id, room_in=room_in
    )


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a room by ID."""
    return await room_service.get_by_id(db, room_id=room_id)


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    room_in: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a room."""
    return await room_service.update_room(db, room_id=room_id, room_in=room_in)


@router.delete("/{room_id}", response_model=RoomResponse)
async def delete_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a room."""
    return await room_service.delete_room(db, room_id=room_id)
