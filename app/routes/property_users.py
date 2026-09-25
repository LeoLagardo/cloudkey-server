from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.property_user import (
    PropertyUserCreate,
    PropertyUserUpdate,
    PropertyUserResponse,
)
from app.services.user_access_service import user_access_service

router = APIRouter(prefix="/property-users", tags=["Property Users"])


@router.get("/{property_id}", response_model=List[PropertyUserResponse])
async def list_property_users(
    property_id: str,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List users assigned to a property."""
    return await user_access_service.list_property_users(
        db, property_id=property_id, skip=skip, limit=limit
    )


@router.post(
    "/{property_id}",
    response_model=PropertyUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_to_property(
    property_id: str,
    user_in: PropertyUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Assign a user and role to a property."""
    return await user_access_service.assign_property_user(
        db, property_id=property_id, obj_in=user_in
    )


@router.put("/{prop_user_id}", response_model=PropertyUserResponse)
async def update_property_user(
    prop_user_id: str,
    user_in: PropertyUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update role or status for a property user."""
    return await user_access_service.update_property_user(
        db, prop_user_id=prop_user_id, obj_in=user_in
    )


@router.delete("/{prop_user_id}", response_model=PropertyUserResponse)
async def remove_property_user(
    prop_user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Remove user access from a property."""
    return await user_access_service.remove_property_user(
        db, prop_user_id=prop_user_id
    )
