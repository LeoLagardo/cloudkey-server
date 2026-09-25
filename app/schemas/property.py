from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import EntityStatus


class PropertyBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Sunset Bay Resort"])
    code: str = Field(..., min_length=1, examples=["SBR-01"])
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    timezone: str = Field(default="Asia/Kolkata")
    currency: str = Field(default="INR")
    status: EntityStatus = Field(default=EntityStatus.ACTIVE)
    is_setup_completed: bool = False
    setup_step: str = "ROOM_TYPES"
    business_date: Optional[date] = Field(None, description="The current 'hotel day'; advanced only by night audit")
    gstin: Optional[str] = Field(None, description="Goods and Services Tax Identification Number")
    classification: Optional[str] = Field(default="HOTEL", description="Property classification type (e.g. HOTEL, RESORT, HOSTEL, BNB, HOMESTAY, BOUTIQUE, VILLA)")


class PropertyCreate(PropertyBase):
    organization_id: Optional[str] = None


class PropertyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    code: Optional[str] = Field(None, min_length=1)
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[EntityStatus] = None
    is_setup_completed: Optional[bool] = None
    setup_step: Optional[str] = None
    business_date: Optional[date] = None
    gstin: Optional[str] = None
    classification: Optional[str] = None


class PropertyResponse(PropertyBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
