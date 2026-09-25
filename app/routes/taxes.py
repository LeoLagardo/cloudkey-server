from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthenticatedUser, get_current_user
from app.crud.property import crud_property
from app.crud.tax import (
    crud_tax,
    crud_tax_group,
    crud_tax_group_item,
    crud_tax_rate,
)
from app.schemas.tax import (
    TaxCreate,
    TaxGroupCreate,
    TaxGroupResponse,
    TaxResponse,
)
from app.utils.exceptions import EntityNotFoundException, DuplicateEntityException

router = APIRouter(prefix="/properties/{property_id}", tags=["Taxes"])


@router.get("/taxes", response_model=List[TaxResponse])
async def list_taxes(
    property_id: str,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all taxes for the property's organization."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)

    return await crud_tax.get_by_organization(
        db,
        organization_id=prop.organization_id,
        skip=skip,
        limit=limit,
        active_only=active_only,
    )


@router.post("/taxes", response_model=TaxResponse, status_code=status.HTTP_201_CREATED)
async def create_tax(
    property_id: str,
    tax_in: TaxCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new tax and its initial rate."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)

    existing = await crud_tax.get_by_code(
        db, organization_id=prop.organization_id, code=tax_in.code
    )
    if existing:
        raise DuplicateEntityException("Tax", "code", tax_in.code)

    tax_data = tax_in.model_dump(exclude={"rate", "rate_type", "min_amount", "max_amount"})
    tax_data["organization_id"] = prop.organization_id

    tax = await crud_tax.create(db, obj_in=tax_data)

    if tax_in.rate is not None:
        await crud_tax_rate.create(
            db,
            obj_in={
                "tax_id": tax.id,
                "rate": tax_in.rate,
                "rate_type": tax_in.rate_type.value if hasattr(tax_in.rate_type, "value") else tax_in.rate_type,
                "min_amount": tax_in.min_amount,
                "max_amount": tax_in.max_amount,
            },
        )

    # Reload with rates
    return await crud_tax.get_by_code(
        db, organization_id=prop.organization_id, code=tax.code
    )


@router.get("/tax-groups", response_model=List[TaxGroupResponse])
async def list_tax_groups(
    property_id: str,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all tax groups for the property's organization."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)

    return await crud_tax_group.get_by_organization(
        db,
        organization_id=prop.organization_id,
        skip=skip,
        limit=limit,
        active_only=active_only,
    )


@router.post("/tax-groups", response_model=TaxGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_group(
    property_id: str,
    group_in: TaxGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new tax group and map taxes into it."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)

    existing = await crud_tax_group.get_by_code(
        db, organization_id=prop.organization_id, code=group_in.code
    )
    if existing:
        raise DuplicateEntityException("TaxGroup", "code", group_in.code)

    group_data = group_in.model_dump(exclude={"items"})
    group_data["organization_id"] = prop.organization_id

    group = await crud_tax_group.create(db, obj_in=group_data)

    for item in group_in.items:
        await crud_tax_group_item.create(
            db,
            obj_in={
                "tax_group_id": group.id,
                "tax_id": item.tax_id,
                "sequence": item.sequence,
                "is_compound": item.is_compound,
            },
        )

    return await crud_tax_group.get_by_code(
        db, organization_id=prop.organization_id, code=group.code
    )
