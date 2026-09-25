from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import BookingType, EntityStatus


class RatePlanBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Standard Nightly Rate"])
    code: str = Field(..., min_length=1, examples=["STD-NIGHT"])
    booking_type: BookingType = Field(default=BookingType.NIGHTLY)
    description: Optional[str] = None
    currency: str = Field(default="INR")
    status: EntityStatus = Field(default=EntityStatus.ACTIVE)


class RatePlanCreate(RatePlanBase):
    property_id: Optional[str] = None
    room_type_id: str


class RatePlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    code: Optional[str] = Field(None, min_length=1)
    booking_type: Optional[BookingType] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[EntityStatus] = None
    room_type_id: Optional[str] = None


class RatePlanResponse(RatePlanBase):
    id: str
    property_id: str
    room_type_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
