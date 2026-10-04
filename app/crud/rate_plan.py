from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.rate_plan import RatePlan
from app.schemas.rate_plan import RatePlanCreate, RatePlanUpdate


class CRUDRatePlan(CRUDBase[RatePlan, RatePlanCreate, RatePlanUpdate]):
    async def get(self, db: AsyncSession, id: str) -> Optional[RatePlan]:
        result = await db.execute(
            select(RatePlan)
            .options(
                selectinload(RatePlan.rates),
                selectinload(RatePlan.room_type),
                selectinload(RatePlan.tax_group),
            )
            .where(RatePlan.id == id)
        )
        return result.scalars().first()

    async def get_by_property(
        self, db: AsyncSession, *, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[RatePlan]:
        result = await db.execute(
            select(RatePlan)
            .options(
                selectinload(RatePlan.rates),
                selectinload(RatePlan.room_type),
                selectinload(RatePlan.tax_group),
            )
            .where(RatePlan.property_id == property_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, property_id: str, code: str
    ) -> Optional[RatePlan]:
        result = await db.execute(
            select(RatePlan)
            .options(
                selectinload(RatePlan.rates),
                selectinload(RatePlan.room_type),
                selectinload(RatePlan.tax_group),
            )
            .where(
                RatePlan.property_id == property_id,
                RatePlan.code == code,
            )
        )
        return result.scalars().first()


crud_rate_plan = CRUDRatePlan(RatePlan)

