from datetime import date
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import delete
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
from app.models.tax import TaxGroupItem
from app.schemas.tax import (
    TaxCreate,
    TaxUpdate,
    TaxGroupCreate,
    TaxGroupUpdate,
    TaxGroupResponse,
    TaxResponse,
)
from app.utils.enums import EntityStatus
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
                "valid_from": date.today(),
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


@router.get("/taxes/{tax_id}", response_model=TaxResponse)
async def get_tax(
    property_id: str,
    tax_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a tax by ID."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    tax = await crud_tax.get(db, tax_id)
    if not tax or tax.organization_id != prop.organization_id:
        raise EntityNotFoundException("Tax", tax_id)
    return tax


@router.put("/taxes/{tax_id}", response_model=TaxResponse)
async def update_tax(
    property_id: str,
    tax_id: str,
    tax_in: TaxUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a tax and optionally its rate."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    tax = await crud_tax.get(db, tax_id)
    if not tax or tax.organization_id != prop.organization_id:
        raise EntityNotFoundException("Tax", tax_id)

    if tax_in.code and tax_in.code != tax.code:
        existing = await crud_tax.get_by_code(
            db, organization_id=prop.organization_id, code=tax_in.code
        )
        if existing and existing.id != tax_id:
            raise DuplicateEntityException("Tax", "code", tax_in.code)

    tax_data = tax_in.model_dump(
        exclude_unset=True, exclude={"rate", "rate_type", "min_amount", "max_amount"}
    )
    if tax_data:
        tax = await crud_tax.update(db, db_obj=tax, obj_in=tax_data)

    if tax_in.rate is not None:
        rates = await crud_tax_rate.get_by_tax(db, tax_id=tax.id)
        rate_type_val = (
            tax_in.rate_type.value
            if hasattr(tax_in.rate_type, "value")
            else tax_in.rate_type
        )
        if rates:
            latest_rate = rates[0]
            await crud_tax_rate.update(
                db,
                db_obj=latest_rate,
                obj_in={
                    "rate": tax_in.rate,
                    "rate_type": rate_type_val or latest_rate.rate_type,
                    "min_amount": tax_in.min_amount,
                    "max_amount": tax_in.max_amount,
                },
            )
        else:
            await crud_tax_rate.create(
                db,
                obj_in={
                    "tax_id": tax.id,
                    "rate": tax_in.rate,
                    "rate_type": rate_type_val or "PERCENTAGE",
                    "min_amount": tax_in.min_amount,
                    "max_amount": tax_in.max_amount,
                    "valid_from": date.today(),
                },
            )

    return await crud_tax.get(db, tax_id)


@router.delete("/taxes/{tax_id}", response_model=TaxResponse)
async def delete_tax(
    property_id: str,
    tax_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Deactivate a tax."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    tax = await crud_tax.get(db, tax_id)
    if not tax or tax.organization_id != prop.organization_id:
        raise EntityNotFoundException("Tax", tax_id)

    return await crud_tax.update(
        db, db_obj=tax, obj_in={"status": EntityStatus.INACTIVE.value}
    )


@router.get("/tax-groups/{tax_group_id}", response_model=TaxGroupResponse)
async def get_tax_group(
    property_id: str,
    tax_group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a tax group by ID."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    group = await crud_tax_group.get(db, tax_group_id)
    if not group or group.organization_id != prop.organization_id:
        raise EntityNotFoundException("TaxGroup", tax_group_id)
    return group


@router.put("/tax-groups/{tax_group_id}", response_model=TaxGroupResponse)
async def update_tax_group(
    property_id: str,
    tax_group_id: str,
    group_in: TaxGroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update a tax group and optionally its items."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    group = await crud_tax_group.get(db, tax_group_id)
    if not group or group.organization_id != prop.organization_id:
        raise EntityNotFoundException("TaxGroup", tax_group_id)

    if group_in.code and group_in.code != group.code:
        existing = await crud_tax_group.get_by_code(
            db, organization_id=prop.organization_id, code=group_in.code
        )
        if existing and existing.id != tax_group_id:
            raise DuplicateEntityException("TaxGroup", "code", group_in.code)

    group_data = group_in.model_dump(exclude_unset=True, exclude={"items"})
    if group_data:
        group = await crud_tax_group.update(db, db_obj=group, obj_in=group_data)

    if group_in.items is not None:
        await db.execute(
            delete(TaxGroupItem).where(TaxGroupItem.tax_group_id == group.id)
        )
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

    return await crud_tax_group.get(db, tax_group_id)


@router.delete("/tax-groups/{tax_group_id}", response_model=TaxGroupResponse)
async def delete_tax_group(
    property_id: str,
    tax_group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Deactivate a tax group."""
    prop = await crud_property.get(db, property_id)
    if not prop:
        raise EntityNotFoundException("Property", property_id)
    group = await crud_tax_group.get(db, tax_group_id)
    if not group or group.organization_id != prop.organization_id:
        raise EntityNotFoundException("TaxGroup", tax_group_id)

    return await crud_tax_group.update(
        db, db_obj=group, obj_in={"status": EntityStatus.INACTIVE.value}
    )

