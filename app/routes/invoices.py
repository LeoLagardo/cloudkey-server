from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthenticatedUser, get_current_user
from app.schemas.invoice import (
    CreditNoteGenerateRequest,
    InvoiceCancelRequest,
    InvoiceDetailResponse,
    InvoiceGenerateRequest,
    InvoiceSummaryResponse,
)
from app.services.invoice_service import invoice_service

router = APIRouter(tags=["Invoices"])


@router.post(
    "/properties/{property_id}/invoices",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_invoice(
    property_id: str,
    payload: InvoiceGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Generate and issue a Tax Invoice or Proforma Invoice from a Folio's debit transactions:
    - Verifies property and folio
    - Resolves Guest or Corporate Bill-to party (with GSTIN & address)
    - Itemizes debit transactions with tax splits (CGST/SGST/IGST) and HSN/SAC codes
    - Acquires sequential invoice number
    - Records audit log entry
    """
    return await invoice_service.generate_invoice(
        db,
        property_id=property_id,
        payload=payload,
        current_user_id=current_user.id,
    )


@router.get(
    "/properties/{property_id}/invoices",
    response_model=List[InvoiceSummaryResponse],
)
async def list_invoices(
    property_id: str,
    invoice_type: Optional[str] = Query(None, description="Filter by invoice type: TAX_INVOICE, PROFORMA, CREDIT_NOTE"),
    status: Optional[str] = Query(None, description="Filter by status: DRAFT, ISSUED, CANCELLED"),
    date_from: Optional[date] = Query(None, description="Start date (inclusive)"),
    date_to: Optional[date] = Query(None, description="End date (inclusive)"),
    guest_id: Optional[str] = Query(None, description="Filter by guest ID"),
    company_id: Optional[str] = Query(None, description="Filter by company ID"),
    search: Optional[str] = Query(None, description="Search by invoice number, bill-to name, or GSTIN"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List invoices with filtering, multi-field search, and pagination."""
    return await invoice_service.list_invoices(
        db,
        property_id=property_id,
        invoice_type=invoice_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        guest_id=guest_id,
        company_id=company_id,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/properties/{property_id}/invoices/{invoice_id}",
    response_model=InvoiceDetailResponse,
)
async def get_invoice(
    property_id: str,
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve full details of an invoice, including line items, tax splits, and payment receipt breakdown."""
    return await invoice_service.get_invoice_detail(
        db,
        property_id=property_id,
        invoice_id=invoice_id,
    )


@router.post(
    "/properties/{property_id}/invoices/{invoice_id}/credit-note",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_credit_note(
    property_id: str,
    invoice_id: str,
    payload: CreditNoteGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Issue a Credit Note against an existing issued Tax Invoice:
    - References original invoice ID
    - Supports full invoice credit or partial line item selection
    - Reverses taxable amount and taxes with negative ledger entries
    - Allocates sequential Credit Note number (CN-...)
    - Creates audit log trail
    """
    return await invoice_service.issue_credit_note(
        db,
        property_id=property_id,
        invoice_id=invoice_id,
        payload=payload,
        current_user_id=current_user.id,
    )


@router.post(
    "/properties/{property_id}/invoices/{invoice_id}/cancel",
    response_model=InvoiceDetailResponse,
)
async def cancel_invoice(
    property_id: str,
    invoice_id: str,
    payload: InvoiceCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Mark an invoice as CANCELLED with reason tracking in the audit log."""
    return await invoice_service.cancel_invoice(
        db,
        property_id=property_id,
        invoice_id=invoice_id,
        payload=payload,
        current_user_id=current_user.id,
    )


@router.get(
    "/properties/{property_id}/folios/{folio_id}/invoices",
    response_model=List[InvoiceSummaryResponse],
)
async def list_folio_invoices(
    property_id: str,
    folio_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all invoices issued for a specific reservation folio."""
    return await invoice_service.list_folio_invoices(
        db,
        property_id=property_id,
        folio_id=folio_id,
    )
