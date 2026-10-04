import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.utils.enums import (
    BookingType,
    ReservationSource,
    ReservationStatus,
    PaymentType,
    PaymentStatus,
    FolioStatus,
    FolioType,
)


# ─── Guest / Booker Sub-Schemas ───────────────────────────────────────────────

class BookerInfoInput(BaseModel):
    guest_id: Optional[str] = None
    first_name: str = Field(..., min_length=1)
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    nationality: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    gstin: Optional[str] = None


class RoomGuestInput(BaseModel):
    guest_id: Optional[str] = None
    first_name: str = Field(..., min_length=1)
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    is_primary: bool = False


# ─── Room & Advance Payment Sub-Schemas ───────────────────────────────────────

class ReservationRoomInput(BaseModel):
    room_type_id: str
    rate_plan_id: str
    room_id: Optional[str] = None  # None until assigned/check-in
    check_in_at: datetime
    check_out_at: datetime
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    guests: List[RoomGuestInput] = []


class AdvancePaymentInput(BaseModel):
    payment_method_id: str
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    gateway: Optional[str] = None
    gateway_reference: Optional[str] = None
    card_last4: Optional[str] = None
    notes: Optional[str] = None


# ─── Main Reservation Create Schema ──────────────────────────────────────────

class ReservationCreate(BaseModel):
    booking_type: BookingType = BookingType.NIGHTLY
    source: ReservationSource = ReservationSource.DIRECT
    channel_name: Optional[str] = None
    channel_booking_ref: Optional[str] = None
    company_id: Optional[str] = None
    special_requests: Optional[str] = None
    currency: str = "INR"
    booker: BookerInfoInput
    rooms: List[ReservationRoomInput] = Field(..., min_length=1)
    advance_payment: Optional[AdvancePaymentInput] = None


# ─── Response Schemas ────────────────────────────────────────────────────────

class GuestSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    nationality: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    gstin: Optional[str] = None
    notes: Optional[str] = None


class ReservationRoomRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stay_date: date
    rate_plan_rate_id: Optional[str] = None
    base_amount: Decimal
    extra_person_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None


class ReservationGuestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    guest_id: str
    is_primary: bool
    guest: Optional[GuestSummaryResponse] = None


class ReservationRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reservation_id: str
    room_type_id: str
    room_id: Optional[str] = None
    rate_plan_id: str
    status: str
    check_in_at: datetime
    check_out_at: datetime
    actual_check_in_at: Optional[datetime] = None
    actual_check_out_at: Optional[datetime] = None
    adults: int
    children: int
    room_number: Optional[str] = None
    room_type_name: Optional[str] = None
    rate_plan_name: Optional[str] = None
    guests: List[ReservationGuestResponse] = []
    room_rates: List[ReservationRoomRateResponse] = []


class FolioSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    reservation_id: Optional[str] = None
    folio_number: str
    folio_type: str
    status: str
    currency: str
    opened_at: datetime


class PaymentSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    folio_id: str
    payment_method_id: str
    payment_type: str
    status: str
    amount: Decimal
    currency: str
    received_at: datetime


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    booking_number: str
    guest_id: str
    company_id: Optional[str] = None
    booking_type: str
    source: str
    channel_name: Optional[str] = None
    channel_booking_ref: Optional[str] = None
    status: str
    check_in_at: datetime
    check_out_at: datetime
    currency: str
    total_amount: Optional[Decimal] = None
    total_tax_amount: Optional[Decimal] = None
    special_requests: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    booker: Optional[GuestSummaryResponse] = None
    rooms: List[ReservationRoomResponse] = []
    folio: Optional[FolioSummaryResponse] = None
    payments: List[PaymentSummaryResponse] = []
