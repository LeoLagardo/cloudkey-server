from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.dependencies.tenant import require_organization_id
from app.schemas.property import (
    PropertyCreate,
    PropertyUpdate,
    PropertyResponse,
)
from app.services.property_service import property_service

router = APIRouter(prefix="/properties", tags=["Properties"])


@router.get("", response_model=List[PropertyResponse])
async def list_properties(
    skip: int = 0,
    limit: int = 100,
    organization_id: str = Depends(require_organization_id),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List properties for the specified organization."""
    return await property_service.list_by_organization(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    prop_in: PropertyCreate,
    organization_id: str = Depends(require_organization_id),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new property under the specified organization."""
    return await property_service.create_property(
        db, organization_id=organization_id, prop_in=prop_in
    )


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a property by ID."""
    return await property_service.get_by_id(db, property_id=property_id)


@router.put("/{property_id}", response_model=PropertyResponse)
@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: str,
    prop_in: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a property."""
    return await property_service.update_property(
        db, property_id=property_id, prop_in=prop_in
    )


@router.delete("/{property_id}", response_model=PropertyResponse)
async def delete_property(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a property."""
    return await property_service.delete_property(db, property_id=property_id)
