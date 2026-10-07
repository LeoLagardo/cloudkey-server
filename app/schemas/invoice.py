from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import InvoiceStatus, InvoiceType


class InvoiceGenerateRequest(BaseModel):
    folio_id: str
    invoice_type: str = Field(
        default=InvoiceType.TAX_INVOICE.value,
        description="PROFORMA, TAX_INVOICE, or CREDIT_NOTE",
    )
    recipient_type: str = Field(
        default="GUEST",
        description="'GUEST' or 'COMPANY'",
    )
    company_id: Optional[str] = None
    guest_id: Optional[str] = None
    bill_to_name: Optional[str] = None
    bill_to_gstin: Optional[str] = None
    bill_to_address: Optional[str] = None
    transaction_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of folio transaction IDs to bill. If omitted, all eligible debit transactions are billed.",
    )
    notes: Optional[str] = None


class CreditNoteGenerateRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Reason for issuing credit note")
    line_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of invoice line IDs to credit. If omitted, the entire invoice is credited.",
    )
    notes: Optional[str] = None


class InvoiceCancelRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Reason for invoice cancellation")


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_id: str
    folio_transaction_id: Optional[str] = None
    description: str
    hsn_sac_code: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_breakdown: Optional[Any] = None


class InvoicePropertyHeader(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    code: str
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    gstin: Optional[str] = None


class InvoicePaymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_method: str
    amount: Decimal
    currency: str
    status: str
    gateway_reference: Optional[str] = None
    received_at: datetime


class InvoiceSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    folio_id: str
    invoice_number: str
    invoice_type: str
    invoice_date: date
    guest_id: Optional[str] = None
    company_id: Optional[str] = None
    bill_to_name: str
    bill_to_gstin: Optional[str] = None
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    currency: str
    status: str
    original_invoice_id: Optional[str] = None
    issued_at: Optional[datetime] = None
    created_at: datetime
    booking_number: Optional[str] = None


class InvoiceDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    folio_id: str
    invoice_number: str
    invoice_type: str
    invoice_date: date
    guest_id: Optional[str] = None
    company_id: Optional[str] = None
    bill_to_name: str
    bill_to_gstin: Optional[str] = None
    bill_to_address: Optional[str] = None
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    currency: str
    status: str
    original_invoice_id: Optional[str] = None
    original_invoice_number: Optional[str] = None
    issued_at: Optional[datetime] = None
    created_at: datetime
    booking_number: Optional[str] = None
    property: Optional[InvoicePropertyHeader] = None
    lines: List[InvoiceLineResponse] = []
    payments: List[InvoicePaymentSummary] = []
    total_paid: Decimal = Decimal("0.00")
    balance_due: Decimal = Decimal("0.00")
