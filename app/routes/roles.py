from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.dependencies.tenant import get_current_organization_id
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    PermissionCreate,
    PermissionResponse,
)
from app.services.role_service import role_service

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


# Permissions endpoints
@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List system permissions."""
    return await role_service.list_permissions(db, skip=skip, limit=limit)


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_permission(
    perm_in: PermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a permission definition."""
    return await role_service.create_permission(db, perm_in=perm_in)


# Roles endpoints
@router.get("", response_model=List[RoleResponse])
async def list_roles(
    organization_id: Optional[str] = Depends(get_current_organization_id),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List roles (scoped to organization or global system roles)."""
    return await role_service.list_roles(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_in: RoleCreate,
    organization_id: Optional[str] = Depends(get_current_organization_id),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a role with assigned permissions."""
    return await role_service.create_role(
        db, role_in=role_in, organization_id=organization_id
    )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a role by ID with permissions."""
    return await role_service.get_by_id(db, role_id=role_id)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    role_in: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update role details and permissions."""
    return await role_service.update_role(db, role_id=role_id, role_in=role_in)


@router.delete("/{role_id}", response_model=RoleResponse)
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a custom role."""
    return await role_service.delete_role(db, role_id=role_id)
