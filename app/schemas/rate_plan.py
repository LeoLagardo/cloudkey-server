from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import BookingType, EntityStatus
from app.schemas.rate_plan_rate import RatePlanRateCreate, RatePlanRateResponse
from app.schemas.room_type import RoomTypeResponse
from app.schemas.tax import TaxGroupSimpleResponse


class RatePlanBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Standard Nightly Rate"])
    code: str = Field(..., min_length=1, examples=["STD-NIGHT"])
    booking_type: BookingType = Field(default=BookingType.NIGHTLY)
    description: Optional[str] = None
    currency: str = Field(default="INR")
    status: EntityStatus = Field(default=EntityStatus.ACTIVE)
    meal_plan: str = Field(default="EP", examples=["EP", "CP", "MAP", "AP"])
    no_of_meals: int = Field(default=0, ge=0)
    color_code: str = Field(default="#4F46E5", examples=["#4F46E5"])
    extra_adult_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    extra_child_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    tax_group_id: Optional[str] = None
    is_tax_inclusive: bool = False


class RatePlanCreate(RatePlanBase):
    property_id: Optional[str] = None
    room_type_id: str
    base_rate: Optional[RatePlanRateCreate] = None


class RatePlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    code: Optional[str] = Field(None, min_length=1)
    booking_type: Optional[BookingType] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[EntityStatus] = None
    meal_plan: Optional[str] = None
    no_of_meals: Optional[int] = None
    color_code: Optional[str] = None
    extra_adult_rate: Optional[Decimal] = None
    extra_child_rate: Optional[Decimal] = None
    room_type_id: Optional[str] = None
    tax_group_id: Optional[str] = None
    is_tax_inclusive: Optional[bool] = None


class RatePlanResponse(RatePlanBase):
    id: str
    property_id: str
    room_type_id: str
    created_at: datetime
    updated_at: datetime
    rates: List[RatePlanRateResponse] = []
    room_type: Optional[RoomTypeResponse] = None
    tax_group: Optional[TaxGroupSimpleResponse] = None

    model_config = ConfigDict(from_attributes=True)

