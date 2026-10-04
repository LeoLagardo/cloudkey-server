from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.guest import (
    GuestCreate,
    GuestUpdate,
    GuestResponse,
    GuestDetailResponse,
    GuestReservationSummary,
)
from app.services.guest_service import guest_service

router = APIRouter(prefix="/guests", tags=["Guests"])


@router.get("", response_model=List[GuestResponse])
async def list_guests(
    property_id: Optional[str] = Query(None, description="Property ID to filter guests by property organization"),
    organization_id: Optional[str] = Query(None, description="Organization ID"),
    search: Optional[str] = Query(None, description="Search term across name, phone, email, id_number, city"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    List and search guests belonging to the organization or property.
    Includes aggregated total stays, total spend, and last stay date.
    """
    resolved_org = organization_id or x_organization_id
    return await guest_service.list_guests(
        db,
        property_id=property_id,
        organization_id=resolved_org,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=GuestResponse, status_code=status.HTTP_201_CREATED)
async def create_guest(
    payload: GuestCreate,
    property_id: Optional[str] = Query(None, description="Property ID to associate guest with its organization"),
    organization_id: Optional[str] = Query(None, description="Organization ID"),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Create a new guest profile under the organization.
    """
    resolved_org = organization_id or x_organization_id
    return await guest_service.create_guest(
        db,
        guest_in=payload,
        property_id=property_id,
        organization_id=resolved_org,
    )


@router.get("/{guest_id}", response_model=GuestDetailResponse)
async def get_guest(
    guest_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieve full guest profile, stay stats, and reservation history.
    """
    return await guest_service.get_guest_by_id(db, guest_id=guest_id)


@router.put("/{guest_id}", response_model=GuestResponse)
async def update_guest(
    guest_id: str,
    payload: GuestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Update guest personal information, contact info, ID docs, or notes.
    """
    return await guest_service.update_guest(db, guest_id=guest_id, guest_in=payload)


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guest(
    guest_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete a guest profile. Fails if the guest has active reservations.
    """
    await guest_service.delete_guest(db, guest_id=guest_id)
    return None


@router.get("/{guest_id}/history", response_model=List[GuestReservationSummary])
async def get_guest_history(
    guest_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get reservation history for a specific guest.
    """
    guest_detail = await guest_service.get_guest_by_id(db, guest_id=guest_id)
    return guest_detail.reservations
