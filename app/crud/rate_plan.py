from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.rate_plan import RatePlan
from app.schemas.rate_plan import RatePlanCreate, RatePlanUpdate


class CRUDRatePlan(CRUDBase[RatePlan, RatePlanCreate, RatePlanUpdate]):
    async def get_by_property(
        self, db: AsyncSession, *, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[RatePlan]:
        result = await db.execute(
            select(RatePlan)
            .where(RatePlan.property_id == property_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, property_id: str, code: str
    ) -> Optional[RatePlan]:
        result = await db.execute(
            select(RatePlan).where(
                RatePlan.property_id == property_id,
                RatePlan.code == code,
            )
        )
        return result.scalars().first()


crud_rate_plan = CRUDRatePlan(RatePlan)
