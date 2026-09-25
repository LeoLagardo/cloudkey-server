from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.organization_user import (
    OrganizationUserCreate,
    OrganizationUserUpdate,
    OrganizationUserResponse,
)
from app.services.user_access_service import user_access_service

router = APIRouter(prefix="/organization-users", tags=["Organization Users"])


@router.get("/{organization_id}", response_model=List[OrganizationUserResponse])
async def list_organization_users(
    organization_id: str,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List users assigned to an organization."""
    return await user_access_service.list_organization_users(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.post(
    "/{organization_id}",
    response_model=OrganizationUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_to_organization(
    organization_id: str,
    user_in: OrganizationUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Assign a user and role to an organization."""
    return await user_access_service.assign_organization_user(
        db, organization_id=organization_id, obj_in=user_in
    )


@router.put("/{org_user_id}", response_model=OrganizationUserResponse)
async def update_organization_user(
    org_user_id: str,
    user_in: OrganizationUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update role or status for an organization user."""
    return await user_access_service.update_organization_user(
        db, org_user_id=org_user_id, obj_in=user_in
    )


@router.delete("/{org_user_id}", response_model=OrganizationUserResponse)
async def remove_organization_user(
    org_user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Remove user membership from an organization."""
    return await user_access_service.remove_organization_user(
        db, org_user_id=org_user_id
    )
