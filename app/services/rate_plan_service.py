from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.room_type import crud_room_type
from app.crud.rate_plan import crud_rate_plan
from app.crud.rate_plan_rate import crud_rate_plan_rate
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate
from app.schemas.rate_plan import RatePlanCreate, RatePlanUpdate
from app.schemas.rate_plan_rate import RatePlanRateCreate, RatePlanRateUpdate
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)


class RatePlanService:
    async def get_by_id(self, db: AsyncSession, rate_plan_id: str) -> RatePlan:
        plan = await crud_rate_plan.get(db, rate_plan_id)
        if not plan:
            raise EntityNotFoundException("RatePlan", rate_plan_id)
        return plan

    async def list_by_property(
        self, db: AsyncSession, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[RatePlan]:
        return await crud_rate_plan.get_by_property(
            db, property_id=property_id, skip=skip, limit=limit
        )

    async def create_rate_plan(
        self, db: AsyncSession, property_id: str, plan_in: RatePlanCreate
    ) -> RatePlan:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        # Validate room_type exists and belongs to property
        room_type = await crud_room_type.get(db, plan_in.room_type_id)
        if not room_type or room_type.property_id != property_id:
            raise ValidationException("Room type does not belong to the property.")

        existing = await crud_rate_plan.get_by_code(
            db, property_id=property_id, code=plan_in.code
        )
        if existing:
            raise DuplicateEntityException("RatePlan", "code", plan_in.code)

        base_rate_in = plan_in.base_rate
        data = plan_in.model_dump(exclude_unset=True, exclude={"base_rate"})
        data["property_id"] = property_id
        plan = await crud_rate_plan.create(db, obj_in=data)

        if base_rate_in:
            r_data = base_rate_in.model_dump(exclude_unset=True)
            r_data["rate_plan_id"] = plan.id
            await crud_rate_plan_rate.create(db, obj_in=r_data)

        return await self.get_by_id(db, plan.id)

    async def update_rate_plan(
        self, db: AsyncSession, rate_plan_id: str, plan_in: RatePlanUpdate
    ) -> RatePlan:
        plan = await self.get_by_id(db, rate_plan_id)

        if plan_in.room_type_id:
            room_type = await crud_room_type.get(db, plan_in.room_type_id)
            if not room_type or room_type.property_id != plan.property_id:
                raise ValidationException("Room type does not belong to the property.")

        if plan_in.code and plan_in.code != plan.code:
            existing = await crud_rate_plan.get_by_code(
                db, property_id=plan.property_id, code=plan_in.code
            )
            if existing:
                raise DuplicateEntityException("RatePlan", "code", plan_in.code)

        data = plan_in.model_dump(exclude_unset=True)
        await crud_rate_plan.update(db, db_obj=plan, obj_in=data)
        return await self.get_by_id(db, rate_plan_id)

    async def delete_rate_plan(self, db: AsyncSession, rate_plan_id: str) -> RatePlan:
        plan = await self.get_by_id(db, rate_plan_id)
        await crud_rate_plan.remove(db, id=rate_plan_id)
        return plan

    # Rate Plan Rates
    async def list_rates(
        self, db: AsyncSession, rate_plan_id: str, skip: int = 0, limit: int = 100
    ) -> List[RatePlanRate]:
        await self.get_by_id(db, rate_plan_id)
        return await crud_rate_plan_rate.get_by_rate_plan(
            db, rate_plan_id=rate_plan_id, skip=skip, limit=limit
        )

    async def add_rate(
        self, db: AsyncSession, rate_plan_id: str, rate_in: RatePlanRateCreate
    ) -> RatePlanRate:
        await self.get_by_id(db, rate_plan_id)
        data = rate_in.model_dump(exclude_unset=True)
        data["rate_plan_id"] = rate_plan_id
        return await crud_rate_plan_rate.create(db, obj_in=data)

    async def delete_rate(
        self, db: AsyncSession, rate_id: str
    ) -> RatePlanRate:
        rate = await crud_rate_plan_rate.get(db, rate_id)
        if not rate:
            raise EntityNotFoundException("RatePlanRate", rate_id)
        await crud_rate_plan_rate.remove(db, id=rate_id)
        return rate


rate_plan_service = RatePlanService()
