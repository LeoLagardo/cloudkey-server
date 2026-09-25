from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.rate_plan import (
    RatePlanCreate,
    RatePlanUpdate,
    RatePlanResponse,
)
from app.schemas.rate_plan_rate import (
    RatePlanRateCreate,
    RatePlanRateResponse,
)
from app.services.rate_plan_service import rate_plan_service

router = APIRouter(prefix="/rate-plans", tags=["Rate Plans"])


@router.get("", response_model=List[RatePlanResponse])
async def list_rate_plans(
    property_id: str = Query(..., description="Property ID to filter rate plans"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List rate plans for a property."""
    return await rate_plan_service.list_by_property(
        db, property_id=property_id, skip=skip, limit=limit
    )


@router.post("", response_model=RatePlanResponse, status_code=status.HTTP_201_CREATED)
async def create_rate_plan(
    plan_in: RatePlanCreate,
    property_id: str = Query(..., description="Property ID to attach rate plan to"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new rate plan for a property."""
    return await rate_plan_service.create_rate_plan(
        db, property_id=property_id, plan_in=plan_in
    )


@router.get("/{rate_plan_id}", response_model=RatePlanResponse)
async def get_rate_plan(
    rate_plan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a rate plan by ID."""
    return await rate_plan_service.get_by_id(db, rate_plan_id=rate_plan_id)


@router.put("/{rate_plan_id}", response_model=RatePlanResponse)
async def update_rate_plan(
    rate_plan_id: str,
    plan_in: RatePlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a rate plan."""
    return await rate_plan_service.update_rate_plan(
        db, rate_plan_id=rate_plan_id, plan_in=plan_in
    )


@router.delete("/{rate_plan_id}", response_model=RatePlanResponse)
async def delete_rate_plan(
    rate_plan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a rate plan."""
    return await rate_plan_service.delete_rate_plan(db, rate_plan_id=rate_plan_id)


# Rate Plan Rates sub-routes
@router.get("/{rate_plan_id}/rates", response_model=List[RatePlanRateResponse])
async def list_rates_for_plan(
    rate_plan_id: str,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List scheduled rates for a rate plan."""
    return await rate_plan_service.list_rates(
        db, rate_plan_id=rate_plan_id, skip=skip, limit=limit
    )


@router.post(
    "/{rate_plan_id}/rates",
    response_model=RatePlanRateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_rate_to_plan(
    rate_plan_id: str,
    rate_in: RatePlanRateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Add a scheduled rate to a rate plan."""
    return await rate_plan_service.add_rate(
        db, rate_plan_id=rate_plan_id, rate_in=rate_in
    )


@router.delete("/{rate_plan_id}/rates/{rate_id}", response_model=RatePlanRateResponse)
async def delete_rate_from_plan(
    rate_plan_id: str,
    rate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a scheduled rate from a rate plan."""
    return await rate_plan_service.delete_rate(db, rate_id=rate_id)
