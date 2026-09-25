from typing import List, Optional
from datetime import date
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.rate_plan_rate import RatePlanRate
from app.schemas.rate_plan_rate import RatePlanRateCreate, RatePlanRateUpdate


class CRUDRatePlanRate(CRUDBase[RatePlanRate, RatePlanRateCreate, RatePlanRateUpdate]):
    async def get_by_rate_plan(
        self, db: AsyncSession, *, rate_plan_id: str, skip: int = 0, limit: int = 100
    ) -> List[RatePlanRate]:
        result = await db.execute(
            select(RatePlanRate)
            .where(RatePlanRate.rate_plan_id == rate_plan_id)
            .order_by(RatePlanRate.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_rates_for_date_range(
        self, db: AsyncSession, *, rate_plan_id: str, start_date: date, end_date: date
    ) -> List[RatePlanRate]:
        result = await db.execute(
            select(RatePlanRate).where(
                RatePlanRate.rate_plan_id == rate_plan_id,
                or_(
                    RatePlanRate.valid_from.is_(None),
                    RatePlanRate.valid_from <= end_date,
                ),
                or_(
                    RatePlanRate.valid_to.is_(None),
                    RatePlanRate.valid_to >= start_date,
                ),
            )
        )
        return list(result.scalars().all())


crud_rate_plan_rate = CRUDRatePlanRate(RatePlanRate)
