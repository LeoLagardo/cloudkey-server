from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.tax import Tax, TaxGroup, TaxGroupItem, TaxRate
from app.schemas.tax import (
    TaxCreate,
    TaxGroupCreate,
    TaxGroupItemCreate,
    TaxGroupUpdate,
    TaxRateCreate,
    TaxUpdate,
)
from app.utils.enums import EntityStatus


class CRUDTax(CRUDBase[Tax, TaxCreate, TaxUpdate]):
    async def get(self, db: AsyncSession, id: str) -> Optional[Tax]:
        result = await db.execute(
            select(Tax)
            .options(selectinload(Tax.rates))
            .where(Tax.id == id)
        )
        return result.scalars().first()

    async def get_by_organization(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
    ) -> List[Tax]:
        stmt = (
            select(Tax)
            .options(selectinload(Tax.rates))
            .where(Tax.organization_id == organization_id)
        )
        if active_only:
            stmt = stmt.where(Tax.status == EntityStatus.ACTIVE.value)
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, organization_id: str, code: str
    ) -> Optional[Tax]:
        result = await db.execute(
            select(Tax)
            .options(selectinload(Tax.rates))
            .where(
                Tax.organization_id == organization_id,
                Tax.code == code,
            )
        )
        return result.scalars().first()


class CRUDTaxRate(CRUDBase[TaxRate, TaxRateCreate, TaxRateCreate]):
    async def get_by_tax(
        self, db: AsyncSession, *, tax_id: str
    ) -> List[TaxRate]:
        result = await db.execute(
            select(TaxRate)
            .where(TaxRate.tax_id == tax_id)
            .order_by(TaxRate.valid_from.desc())
        )
        return list(result.scalars().all())


class CRUDTaxGroup(CRUDBase[TaxGroup, TaxGroupCreate, TaxGroupUpdate]):
    async def get(self, db: AsyncSession, id: str) -> Optional[TaxGroup]:
        result = await db.execute(
            select(TaxGroup)
            .options(
                selectinload(TaxGroup.items).selectinload(TaxGroupItem.tax).selectinload(Tax.rates)
            )
            .where(TaxGroup.id == id)
        )
        return result.scalars().first()

    async def get_by_organization(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
    ) -> List[TaxGroup]:
        stmt = (
            select(TaxGroup)
            .options(
                selectinload(TaxGroup.items).selectinload(TaxGroupItem.tax).selectinload(Tax.rates)
            )
            .where(TaxGroup.organization_id == organization_id)
        )
        if active_only:
            stmt = stmt.where(TaxGroup.status == EntityStatus.ACTIVE.value)
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, organization_id: str, code: str
    ) -> Optional[TaxGroup]:
        result = await db.execute(
            select(TaxGroup)
            .options(
                selectinload(TaxGroup.items).selectinload(TaxGroupItem.tax).selectinload(Tax.rates)
            )
            .where(
                TaxGroup.organization_id == organization_id,
                TaxGroup.code == code,
            )
        )
        return result.scalars().first()



class CRUDTaxGroupItem(CRUDBase[TaxGroupItem, TaxGroupItemCreate, TaxGroupItemCreate]):
    async def get_by_group(
        self, db: AsyncSession, *, tax_group_id: str
    ) -> List[TaxGroupItem]:
        result = await db.execute(
            select(TaxGroupItem)
            .where(TaxGroupItem.tax_group_id == tax_group_id)
            .order_by(TaxGroupItem.sequence)
        )
        return list(result.scalars().all())


crud_tax = CRUDTax(Tax)
crud_tax_rate = CRUDTaxRate(TaxRate)
crud_tax_group = CRUDTaxGroup(TaxGroup)
crud_tax_group_item = CRUDTaxGroupItem(TaxGroupItem)
