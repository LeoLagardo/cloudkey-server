from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import DurationUnit


class RatePlanRateBase(BaseModel):
    duration: int = Field(..., ge=1, examples=[1])
    duration_unit: DurationUnit = Field(default=DurationUnit.NIGHT)
    price: Decimal = Field(..., ge=Decimal("0.0"), examples=[Decimal("2500.00")])
    min_occupancy: Optional[int] = Field(None, ge=1)
    max_occupancy: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None

    @model_validator(mode="after")
    def validate_dates_and_occupancy(self) -> "RatePlanRateBase":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be greater than or equal to valid_from.")
        if (
            self.min_occupancy is not None
            and self.max_occupancy is not None
            and self.max_occupancy < self.min_occupancy
        ):
            raise ValueError("max_occupancy must be greater than or equal to min_occupancy.")
        return self


class RatePlanRateCreate(RatePlanRateBase):
    rate_plan_id: Optional[str] = None


class RatePlanRateUpdate(BaseModel):
    duration: Optional[int] = Field(None, ge=1)
    duration_unit: Optional[DurationUnit] = None
    price: Optional[Decimal] = Field(None, ge=Decimal("0.0"))
    min_occupancy: Optional[int] = Field(None, ge=1)
    max_occupancy: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class RatePlanRateResponse(RatePlanRateBase):
    id: str
    rate_plan_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
