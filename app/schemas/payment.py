from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class PaymentCreateInput(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Payment amount in property currency")
    payment_method: str = Field(..., description="Payment method code or ID, e.g. CREDIT_CARD, UPI, CASH, BANK_TRANSFER")
    payment_type: Optional[str] = Field("SETTLEMENT", description="Type of payment e.g. SETTLEMENT, ADVANCE, DEPOSIT")
    status: Optional[str] = Field("COMPLETED", description="Payment status e.g. COMPLETED, CAPTURED")
    currency: Optional[str] = None
    gateway: Optional[str] = None
    gateway_reference: Optional[str] = None
    card_last4: Optional[str] = None
    notes: Optional[str] = None
    folio_id: Optional[str] = None
    reservation_id: Optional[str] = None


class PaymentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    folio_id: str
    reservation_id: Optional[str] = None
    payment_method_id: str
    payment_method_name: Optional[str] = None
    payment_method_code: Optional[str] = None
    payment_type: str
    status: str
    amount: Decimal
    currency: str
    gateway: Optional[str] = None
    gateway_reference: Optional[str] = None
    card_last4: Optional[str] = None
    notes: Optional[str] = None
    received_at: datetime
    received_by: Optional[str] = None

    # Context enrichment
    booking_number: Optional[str] = None
    folio_number: Optional[str] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    room_number: Optional[str] = None
