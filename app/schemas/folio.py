from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PostServiceChargeRequest(BaseModel):
    service_id: str
    quantity: Decimal = Field(default=Decimal("1.00"), gt=Decimal("0.00"))
    unit_price: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    custom_description: Optional[str] = Field(default=None, max_length=255)
    reservation_room_id: Optional[str] = None
    business_date: Optional[date] = None


class FolioTransactionTaxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tax_id: str
    tax_rate_id: Optional[str] = None
    tax_name: str
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


class FolioTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    folio_id: str
    business_date: date
    entry_type: str
    transaction_type: str
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    service_category: Optional[str] = None
    payment_id: Optional[str] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_group_id: Optional[str] = None
    is_tax_inclusive: bool = False
    hsn_sac_code: Optional[str] = None
    source: str
    posted_by: Optional[str] = None
    posted_at: datetime
    taxes: List[FolioTransactionTaxResponse] = []


class FolioDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    reservation_id: Optional[str] = None
    folio_number: str
    folio_type: str
    status: str
    currency: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    total_charges: Decimal = Decimal("0.00")
    total_payments: Decimal = Decimal("0.00")
    balance_due: Decimal = Decimal("0.00")
    transactions: List[FolioTransactionResponse] = []
