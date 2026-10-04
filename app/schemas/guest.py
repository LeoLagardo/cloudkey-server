from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GuestBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=150)
    last_name: Optional[str] = Field(None, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = Field(None, max_length=100)
    id_type: Optional[str] = Field(None, max_length=100)
    id_number: Optional[str] = Field(None, max_length=100)
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    gstin: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class GuestCreate(GuestBase):
    pass


class GuestUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=150)
    last_name: Optional[str] = Field(None, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = Field(None, max_length=100)
    id_type: Optional[str] = Field(None, max_length=100)
    id_number: Optional[str] = Field(None, max_length=100)
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    gstin: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class GuestReservationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_number: str
    status: str
    check_in_at: datetime
    check_out_at: datetime
    currency: str = "INR"
    total_amount: Optional[Decimal] = None
    total_tax_amount: Optional[Decimal] = None
    room_number: Optional[str] = None
    room_type_name: Optional[str] = None


class GuestResponse(GuestBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    total_stays: int = 0
    total_spent: Decimal = Decimal("0.00")
    last_stay_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GuestDetailResponse(GuestResponse):
    model_config = ConfigDict(from_attributes=True)

    reservations: List[GuestReservationSummary] = []
