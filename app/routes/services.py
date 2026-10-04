from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthenticatedUser, get_current_user
from app.schemas.service import (
    ServiceCategoryCreate,
    ServiceCategoryResponse,
    ServiceCategoryUpdate,
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
)
from app.services.service_catalog_service import service_catalog_service

router = APIRouter(prefix="/properties/{property_id}/services", tags=["Property Services"])


# ─── Service Category Routes ──────────────────────────────────────────────────

@router.get("/categories", response_model=List[ServiceCategoryResponse])
async def list_property_service_categories(
    property_id: str,
    parent_id: Optional[str] = Query(None, description="Filter sub-categories by parent category ID"),
    only_roots: bool = Query(True, description="When true, returns only root categories with sub_categories nested"),
    active_only: bool = Query(False, description="Filter active categories only"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List hotel-configured service categories and sub-categories."""
    return await service_catalog_service.list_categories(
        db,
        property_id=property_id,
        parent_id=parent_id,
        only_roots=only_roots,
        active_only=active_only,
    )


@router.post("/categories", response_model=ServiceCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_property_service_category(
    property_id: str,
    cat_in: ServiceCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new service category or sub-category for the property."""
    return await service_catalog_service.create_category(
        db, property_id=property_id, cat_in=cat_in
    )


@router.post("/categories/seed-defaults", response_model=List[ServiceCategoryResponse])
async def seed_default_service_categories(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Bootstrap standard hotel categories (F&B, Laundry, Transport, Spa, Minibar, Front Desk) and sub-categories."""
    return await service_catalog_service.seed_default_categories(
        db, property_id=property_id
    )


@router.get("/categories/{category_id}", response_model=ServiceCategoryResponse)
async def get_property_service_category(
    property_id: str,
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve details for a specific service category."""
    return await service_catalog_service.get_category(
        db, property_id=property_id, category_id=category_id
    )


@router.put("/categories/{category_id}", response_model=ServiceCategoryResponse)
async def update_property_service_category(
    property_id: str,
    category_id: str,
    cat_in: ServiceCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a service category or sub-category."""
    return await service_catalog_service.update_category(
        db, property_id=property_id, category_id=category_id, cat_in=cat_in
    )


@router.delete("/categories/{category_id}", response_model=ServiceCategoryResponse)
async def delete_property_service_category(
    property_id: str,
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Deactivate a service category and its sub-categories."""
    return await service_catalog_service.deactivate_category(
        db, property_id=property_id, category_id=category_id
    )


# ─── Services Catalog Routes ──────────────────────────────────────────────────

@router.get("", response_model=List[ServiceResponse])
async def list_services(
    property_id: str,
    category: Optional[str] = Query(None, description="Filter by macro system category enum"),
    category_id: Optional[str] = Query(None, description="Filter by configured category/sub-category ID"),
    active_only: bool = Query(False, description="Filter active services only"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all configured services for a property."""
    return await service_catalog_service.list_services(
        db,
        property_id=property_id,
        category=category,
        category_id=category_id,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    property_id: str,
    service_in: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Add a new sellable/consumable service to the property catalog."""
    return await service_catalog_service.create_service(
        db, property_id=property_id, service_in=service_in
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    property_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve details for a specific property service."""
    return await service_catalog_service.get_service(
        db, property_id=property_id, service_id=service_id
    )


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
    property_id: str,
    service_id: str,
    service_in: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a property service definition (price, tax group, category, status)."""
    return await service_catalog_service.update_service(
        db,
        property_id=property_id,
        service_id=service_id,
        service_in=service_in,
    )


@router.delete("/{service_id}", response_model=ServiceResponse)
async def delete_service(
    property_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Deactivate a service from the property catalog."""
    return await service_catalog_service.deactivate_service(
        db, property_id=property_id, service_id=service_id
    )
