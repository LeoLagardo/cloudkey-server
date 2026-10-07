import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.folio import Folio, FolioTransaction, Payment
from app.models.guest import Guest
from app.models.invoice import Invoice, InvoiceLine
from app.models.operation import AuditLog
from app.models.property import Property
from app.models.rate_plan import RatePlan
from app.models.reservation import Reservation, ReservationRoom, ReservationRoomRate
from app.models.tax import Tax, TaxGroup, TaxRate
from app.schemas.invoice import (
    CreditNoteGenerateRequest,
    InvoiceCancelRequest,
    InvoiceDetailResponse,
    InvoiceGenerateRequest,
    InvoiceLineResponse,
    InvoicePaymentSummary,
    InvoicePropertyHeader,
    InvoiceSummaryResponse,
)
from app.services.folio_service import folio_service
from app.services.sequence_service import sequence_service
from app.utils.enums import (
    FolioEntryType,
    FolioTransactionType,
    InvoiceStatus,
    InvoiceType,
    PaymentStatus,
    TaxRateType,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException


class InvoiceService:
    async def generate_invoice(
        self,
        db: AsyncSession,
        property_id: str,
        payload: InvoiceGenerateRequest,
        current_user_id: Optional[str] = None,
    ) -> InvoiceDetailResponse:
        """
        Generate and issue a Tax Invoice or Proforma Invoice from a Folio's debit transactions.
        """
        # 1. Fetch Property
        prop_query = await db.execute(select(Property).where(Property.id == property_id))
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        # 2. Fetch Folio
        folio_query = await db.execute(
            select(Folio)
            .options(
                selectinload(Folio.reservation)
                .selectinload(Reservation.rooms)
                .selectinload(ReservationRoom.room_rates),
                selectinload(Folio.reservation)
                .selectinload(Reservation.rooms)
                .selectinload(ReservationRoom.room),
                selectinload(Folio.reservation)
                .selectinload(Reservation.rooms)
                .selectinload(ReservationRoom.room_type),
                selectinload(Folio.reservation)
                .selectinload(Reservation.rooms)
                .selectinload(ReservationRoom.rate_plan)
                .selectinload(RatePlan.tax_group)
                .selectinload(TaxGroup.items),
                selectinload(Folio.guest),
            )
            .where(
                Folio.id == payload.folio_id,
                Folio.property_id == property_id,
            )
        )
        folio = folio_query.scalar_one_or_none()
        if not folio:
            raise EntityNotFoundException("Folio", payload.folio_id)

        reservation = folio.reservation

        inv_type = payload.invoice_type.upper()
        if inv_type not in (InvoiceType.PROFORMA.value, InvoiceType.TAX_INVOICE.value):
            inv_type = InvoiceType.TAX_INVOICE.value

        # Enforce single Tax Invoice per folio (idempotent; prevents duplicate sequence numbers)
        if inv_type == InvoiceType.TAX_INVOICE.value:
            existing_tax_inv_q = await db.execute(
                select(Invoice).where(
                    Invoice.folio_id == folio.id,
                    Invoice.invoice_type == InvoiceType.TAX_INVOICE.value,
                    Invoice.status == InvoiceStatus.ISSUED.value,
                )
            )
            existing_tax_inv = existing_tax_inv_q.scalar_one_or_none()
            if existing_tax_inv:
                return await self.get_invoice_detail(db, property_id=property_id, invoice_id=existing_tax_inv.id)

        # Check for existing Proforma Draft on this folio to update in place
        existing_proforma: Optional[Invoice] = None
        if inv_type == InvoiceType.PROFORMA.value:
            existing_proforma_q = await db.execute(
                select(Invoice).where(
                    Invoice.folio_id == folio.id,
                    Invoice.invoice_type == InvoiceType.PROFORMA.value,
                    Invoice.status == InvoiceStatus.DRAFT.value,
                )
            )
            existing_proforma = existing_proforma_q.scalar_one_or_none()

        # For TAX_INVOICE, ensure all unposted stay nights are posted to ledger
        if inv_type == InvoiceType.TAX_INVOICE.value and not payload.transaction_ids and folio.reservation:
            for r_room in folio.reservation.rooms:
                for rr in r_room.room_rates:
                    if rr.folio_transaction_id is None:
                        await folio_service.post_room_rate_transaction(
                            db=db,
                            property_id=property_id,
                            folio_id=folio.id,
                            room_rate=rr,
                            reservation_room=r_room,
                            current_user_id=current_user_id,
                        )

        # 3. Resolve Bill-to details (Guest or Company)
        guest_obj: Optional[Guest] = None
        company_obj: Optional[Company] = None
        bill_to_name = payload.bill_to_name
        bill_to_gstin = payload.bill_to_gstin
        bill_to_address = payload.bill_to_address
        resolved_company_id = payload.company_id
        resolved_guest_id = payload.guest_id or folio.guest_id

        if payload.recipient_type.upper() == "COMPANY" or resolved_company_id:
            if resolved_company_id:
                comp_query = await db.execute(
                    select(Company).where(
                        Company.id == resolved_company_id,
                        Company.organization_id == property_obj.organization_id,
                    )
                )
                company_obj = comp_query.scalar_one_or_none()

            if company_obj:
                bill_to_name = bill_to_name or company_obj.name
                bill_to_gstin = bill_to_gstin or company_obj.gstin
                bill_to_address = bill_to_address or company_obj.billing_address
                resolved_company_id = company_obj.id

        if not bill_to_name:
            if resolved_guest_id:
                guest_query = await db.execute(
                    select(Guest).where(Guest.id == resolved_guest_id)
                )
                guest_obj = guest_query.scalar_one_or_none()
                if guest_obj:
                    bill_to_name = f"{guest_obj.first_name} {guest_obj.last_name or ''}".strip()
                    bill_to_gstin = bill_to_gstin or guest_obj.gstin
                    addr_parts = [
                        p
                        for p in [
                            guest_obj.address_line_1,
                            guest_obj.city,
                            guest_obj.state,
                            guest_obj.postal_code,
                        ]
                        if p
                    ]
                    bill_to_address = bill_to_address or (", ".join(addr_parts) if addr_parts else None)

        if not bill_to_name:
            bill_to_name = "Guest"

        # 4. Fetch billable Folio Transactions (Debits)
        txn_query = (
            select(FolioTransaction)
            .options(
                selectinload(FolioTransaction.taxes),
                selectinload(FolioTransaction.service),
            )
            .where(
                FolioTransaction.folio_id == folio.id,
                FolioTransaction.entry_type == FolioEntryType.DEBIT.value,
            )
            .order_by(FolioTransaction.business_date.asc(), FolioTransaction.posted_at.asc())
        )

        if payload.transaction_ids:
            txn_query = txn_query.where(FolioTransaction.id.in_(payload.transaction_ids))

        res_txns = await db.execute(txn_query)
        transactions = list(res_txns.scalars().all())

        # 5. Calculate Lines and Totals
        invoice_id = str(uuid.uuid4())
        lines: List[InvoiceLine] = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for txn in transactions:
            qty = txn.quantity or Decimal("1.00")
            unit_p = txn.unit_price or txn.amount
            taxable_amt = txn.amount
            tax_amt = txn.tax_amount or Decimal("0.00")
            total_amt = txn.total_amount

            # Resolve HSN/SAC code
            hsn_sac = txn.hsn_sac_code
            if not hsn_sac and txn.transaction_type == FolioTransactionType.ROOM_CHARGE.value:
                hsn_sac = "996311"

            # Snapshot tax breakdown
            tax_breakdown = [
                {
                    "tax_id": t.tax_id,
                    "tax_name": t.tax_name,
                    "rate": float(t.rate),
                    "taxable_amount": str(t.taxable_amount),
                    "tax_amount": str(t.tax_amount),
                }
                for t in txn.taxes
            ]

            line = InvoiceLine(
                id=str(uuid.uuid4()),
                invoice_id=invoice_id,
                folio_transaction_id=txn.id,
                description=txn.description,
                hsn_sac_code=hsn_sac,
                quantity=qty,
                unit_price=unit_p,
                taxable_amount=taxable_amt,
                tax_amount=tax_amt,
                total_amount=total_amt,
                tax_breakdown=tax_breakdown,
            )
            lines.append(line)

            subtotal += taxable_amt
            tax_total += tax_amt
            grand_total += total_amt

        # For PROFORMA, also append any unposted stay nights without modifying ledger
        if inv_type == InvoiceType.PROFORMA.value and not payload.transaction_ids and folio.reservation:
            for r_room in folio.reservation.rooms:
                for rr in r_room.room_rates:
                    if rr.folio_transaction_id is None:
                        room_num = r_room.room_number or (r_room.room.room_number if r_room.room else None)
                        room_type_name = r_room.room_type_name or (r_room.room_type.name if r_room.room_type else None)
                        room_part = f"Room {room_num}" if room_num else "Room"
                        type_part = f" ({room_type_name})" if room_type_name else ""
                        description = f"Room Night Charge - {room_part}{type_part} - {rr.stay_date}"

                        tax_breakdown = []
                        tax_amt = Decimal("0.00")
                        tax_group_id = r_room.rate_plan.tax_group_id if r_room.rate_plan else None
                        if tax_group_id:
                            tg_q = await db.execute(
                                select(TaxGroup).options(selectinload(TaxGroup.items)).where(TaxGroup.id == tax_group_id)
                            )
                            tg_obj = tg_q.scalar_one_or_none()
                            if tg_obj and tg_obj.items:
                                for item in tg_obj.items:
                                    rate_q = await db.execute(
                                        select(TaxRate)
                                        .where(
                                            TaxRate.tax_id == item.tax_id,
                                            TaxRate.valid_from <= rr.stay_date,
                                            or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= rr.stay_date),
                                        )
                                        .order_by(TaxRate.created_at.desc())
                                    )
                                    tax_rate_obj = rate_q.scalars().first()
                                    tax_q = await db.execute(select(Tax).where(Tax.id == item.tax_id))
                                    tax_ent = tax_q.scalar_one_or_none()
                                    if tax_rate_obj and tax_ent:
                                        tax_line_amt = (
                                            (rr.net_amount * tax_rate_obj.rate / Decimal("100")).quantize(Decimal("0.01"))
                                            if tax_rate_obj.rate_type == TaxRateType.PERCENTAGE.value
                                            else tax_rate_obj.rate.quantize(Decimal("0.01"))
                                        )
                                        tax_amt += tax_line_amt
                                        tax_breakdown.append({
                                            "tax_id": item.tax_id,
                                            "tax_name": tax_ent.name,
                                            "rate": float(tax_rate_obj.rate),
                                            "taxable_amount": str(rr.net_amount),
                                            "tax_amount": str(tax_line_amt),
                                        })
                        if not tax_breakdown and rr.tax_amount:
                            tax_amt = rr.tax_amount

                        tot_amt = rr.net_amount + tax_amt
                        line = InvoiceLine(
                            id=str(uuid.uuid4()),
                            invoice_id=invoice_id,
                            folio_transaction_id=None,
                            description=description,
                            hsn_sac_code="996311",
                            quantity=Decimal("1.00"),
                            unit_price=rr.net_amount,
                            taxable_amount=rr.net_amount,
                            tax_amount=tax_amt,
                            total_amount=tot_amt,
                            tax_breakdown=tax_breakdown,
                        )
                        lines.append(line)
                        subtotal += rr.net_amount
                        tax_total += tax_amt
                        grand_total += tot_amt

        if not lines:
            raise ValidationException("Folio has no billable debit charges or stay nights to generate an invoice.")

        now = datetime.now(timezone.utc)
        inv_date = property_obj.business_date or now.date()

        if existing_proforma:
            # Update existing Proforma Draft in place without burning sequence numbers
            invoice = existing_proforma
            invoice.guest_id = resolved_guest_id
            invoice.company_id = resolved_company_id
            invoice.bill_to_name = bill_to_name
            invoice.bill_to_gstin = bill_to_gstin
            invoice.bill_to_address = bill_to_address
            invoice.subtotal = subtotal.quantize(Decimal("0.01"))
            invoice.tax_total = tax_total.quantize(Decimal("0.01"))
            invoice.grand_total = grand_total.quantize(Decimal("0.01"))
            invoice.invoice_date = inv_date

            # Clear old lines and attach freshly computed lines
            await db.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
            for line in lines:
                line.invoice_id = invoice.id
                db.add(line)
            await db.flush()

            audit = AuditLog(
                organization_id=property_obj.organization_id,
                property_id=property_id,
                user_id=current_user_id,
                entity_type="invoices",
                entity_id=invoice.id,
                action="UPDATE",
                old_values=None,
                new_values={
                    "invoice_number": invoice.invoice_number,
                    "invoice_type": invoice.invoice_type,
                    "grand_total": str(invoice.grand_total),
                    "folio_id": folio.id,
                },
            )
            db.add(audit)
            await db.commit()

            return await self.get_invoice_detail(db, property_id=property_id, invoice_id=invoice.id)

        # 6. Generate Invoice Number & Status
        invoice_number = await sequence_service.generate_invoice_number(
            db, property_id=property_id, invoice_type=inv_type
        )

        invoice_status = (
            InvoiceStatus.DRAFT.value
            if inv_type == InvoiceType.PROFORMA.value
            else InvoiceStatus.ISSUED.value
        )

        invoice = Invoice(
            id=invoice_id,
            property_id=property_id,
            folio_id=folio.id,
            invoice_number=invoice_number,
            invoice_type=inv_type,
            invoice_date=inv_date,
            guest_id=resolved_guest_id,
            company_id=resolved_company_id,
            bill_to_name=bill_to_name,
            bill_to_gstin=bill_to_gstin,
            bill_to_address=bill_to_address,
            subtotal=subtotal.quantize(Decimal("0.01")),
            tax_total=tax_total.quantize(Decimal("0.01")),
            grand_total=grand_total.quantize(Decimal("0.01")),
            currency=folio.currency or property_obj.currency or "INR",
            status=invoice_status,
            issued_at=now if invoice_status == InvoiceStatus.ISSUED.value else None,
            created_at=now,
        )

        db.add(invoice)
        for line in lines:
            db.add(line)
        await db.flush()

        # 7. Audit Log
        audit = AuditLog(
            organization_id=property_obj.organization_id,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="invoices",
            entity_id=invoice.id,
            action="CREATE",
            old_values=None,
            new_values={
                "invoice_number": invoice.invoice_number,
                "invoice_type": invoice.invoice_type,
                "grand_total": str(invoice.grand_total),
                "folio_id": folio.id,
            },
        )
        db.add(audit)
        await db.commit()

        return await self.get_invoice_detail(db, property_id=property_id, invoice_id=invoice.id)

    async def issue_credit_note(
        self,
        db: AsyncSession,
        property_id: str,
        invoice_id: str,
        payload: CreditNoteGenerateRequest,
        current_user_id: Optional[str] = None,
    ) -> InvoiceDetailResponse:
        """
        Issue a Credit Note reversing all or specified lines of an issued Tax Invoice.
        """
        prop_query = await db.execute(select(Property).where(Property.id == property_id))
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        inv_query = await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.lines),
                selectinload(Invoice.folio),
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.property_id == property_id,
            )
        )
        original_invoice = inv_query.scalar_one_or_none()
        if not original_invoice:
            raise EntityNotFoundException("Invoice", invoice_id)

        if original_invoice.status != InvoiceStatus.ISSUED.value:
            raise ValidationException(
                f"Cannot credit invoice with status '{original_invoice.status}'. Only ISSUED invoices can be credited."
            )

        if original_invoice.invoice_type != InvoiceType.TAX_INVOICE.value:
            raise ValidationException("Credit notes can only be issued against TAX_INVOICE documents.")

        # Determine target lines to credit
        target_lines = original_invoice.lines
        if payload.line_ids:
            target_lines = [ln for ln in original_invoice.lines if ln.id in payload.line_ids]
            if not target_lines:
                raise ValidationException("None of the specified line IDs match lines on this invoice.")

        now = datetime.now(timezone.utc)
        inv_date = property_obj.business_date or now.date()

        cn_id = str(uuid.uuid4())
        cn_number = await sequence_service.generate_invoice_number(
            db, property_id=property_id, invoice_type=InvoiceType.CREDIT_NOTE.value
        )

        cn_lines: List[InvoiceLine] = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for orig_line in target_lines:
            rev_taxable = -abs(orig_line.taxable_amount)
            rev_tax = -abs(orig_line.tax_amount)
            rev_total = -abs(orig_line.total_amount)

            cn_line = InvoiceLine(
                id=str(uuid.uuid4()),
                invoice_id=cn_id,
                folio_transaction_id=orig_line.folio_transaction_id,
                description=f"Credit: {orig_line.description}",
                hsn_sac_code=orig_line.hsn_sac_code,
                quantity=orig_line.quantity,
                unit_price=orig_line.unit_price,
                taxable_amount=rev_taxable,
                tax_amount=rev_tax,
                total_amount=rev_total,
                tax_breakdown=orig_line.tax_breakdown,
            )
            cn_lines.append(cn_line)

            subtotal += rev_taxable
            tax_total += rev_tax
            grand_total += rev_total

        credit_note = Invoice(
            id=cn_id,
            property_id=property_id,
            folio_id=original_invoice.folio_id,
            invoice_number=cn_number,
            invoice_type=InvoiceType.CREDIT_NOTE.value,
            invoice_date=inv_date,
            guest_id=original_invoice.guest_id,
            company_id=original_invoice.company_id,
            bill_to_name=original_invoice.bill_to_name,
            bill_to_gstin=original_invoice.bill_to_gstin,
            bill_to_address=original_invoice.bill_to_address,
            subtotal=subtotal.quantize(Decimal("0.01")),
            tax_total=tax_total.quantize(Decimal("0.01")),
            grand_total=grand_total.quantize(Decimal("0.01")),
            currency=original_invoice.currency,
            status=InvoiceStatus.ISSUED.value,
            original_invoice_id=original_invoice.id,
            issued_at=now,
            created_at=now,
        )

        db.add(credit_note)
        for ln in cn_lines:
            db.add(ln)
        await db.flush()

        audit = AuditLog(
            organization_id=property_obj.organization_id,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="invoices",
            entity_id=credit_note.id,
            action="CREDIT_NOTE",
            old_values={"original_invoice_id": original_invoice.id},
            new_values={
                "credit_note_number": credit_note.invoice_number,
                "reason": payload.reason,
                "amount": str(credit_note.grand_total),
            },
        )
        db.add(audit)
        await db.commit()

        return await self.get_invoice_detail(db, property_id=property_id, invoice_id=credit_note.id)

    async def cancel_invoice(
        self,
        db: AsyncSession,
        property_id: str,
        invoice_id: str,
        payload: InvoiceCancelRequest,
        current_user_id: Optional[str] = None,
    ) -> InvoiceDetailResponse:
        """
        Cancel an invoice and record the reason in the audit trail.
        """
        inv_query = await db.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.property_id == property_id,
            )
        )
        invoice = inv_query.scalar_one_or_none()
        if not invoice:
            raise EntityNotFoundException("Invoice", invoice_id)

        if invoice.status == InvoiceStatus.CANCELLED.value:
            raise ValidationException("Invoice is already cancelled.")

        prop_query = await db.execute(select(Property).where(Property.id == property_id))
        property_obj = prop_query.scalar_one_or_none()

        old_status = invoice.status
        invoice.status = InvoiceStatus.CANCELLED.value

        audit = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="invoices",
            entity_id=invoice.id,
            action="CANCEL",
            old_values={"status": old_status},
            new_values={
                "status": InvoiceStatus.CANCELLED.value,
                "cancellation_reason": payload.reason,
            },
        )
        db.add(audit)
        await db.commit()

        return await self.get_invoice_detail(db, property_id=property_id, invoice_id=invoice.id)

    async def get_invoice_detail(
        self, db: AsyncSession, property_id: str, invoice_id: str
    ) -> InvoiceDetailResponse:
        """
        Retrieve full invoice representation with property header, lines, and folio payment summary.
        """
        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.lines),
                selectinload(Invoice.property),
                selectinload(Invoice.folio).selectinload(Folio.reservation),
                selectinload(Invoice.original_invoice),
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.property_id == property_id,
            )
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise EntityNotFoundException("Invoice", invoice_id)

        # Property Header
        prop_header = None
        if invoice.property:
            prop = invoice.property
            prop_header = InvoicePropertyHeader(
                name=prop.name,
                code=prop.code,
                address_line_1=prop.address_line_1,
                address_line_2=prop.address_line_2,
                city=prop.city,
                state=prop.state,
                country=prop.country,
                postal_code=prop.postal_code,
                gstin=prop.gstin,
            )

        # Line responses
        lines_resp = [
            InvoiceLineResponse(
                id=ln.id,
                invoice_id=ln.invoice_id,
                folio_transaction_id=ln.folio_transaction_id,
                description=ln.description,
                hsn_sac_code=ln.hsn_sac_code,
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                taxable_amount=ln.taxable_amount,
                tax_amount=ln.tax_amount,
                total_amount=ln.total_amount,
                tax_breakdown=ln.tax_breakdown,
            )
            for ln in invoice.lines
        ]

        # Fetch payments on the folio
        pmt_stmt = (
            select(Payment)
            .options(selectinload(Payment.payment_method))
            .where(
                Payment.folio_id == invoice.folio_id,
                Payment.status == PaymentStatus.CAPTURED.value,
            )
            .order_by(Payment.received_at.asc())
        )
        pmt_res = await db.execute(pmt_stmt)
        payments = list(pmt_res.scalars().all())

        payments_resp: List[InvoicePaymentSummary] = []
        total_paid = Decimal("0.00")
        for p in payments:
            method_name = p.payment_method.name if p.payment_method else p.payment_type
            payments_resp.append(
                InvoicePaymentSummary(
                    id=p.id,
                    payment_method=method_name,
                    amount=p.amount,
                    currency=p.currency,
                    status=p.status,
                    gateway_reference=p.gateway_reference,
                    received_at=p.received_at,
                )
            )
            total_paid += p.amount

        balance_due = (invoice.grand_total - total_paid).quantize(Decimal("0.01"))
        booking_no = (
            invoice.folio.reservation.booking_number
            if (invoice.folio and invoice.folio.reservation)
            else None
        )

        return InvoiceDetailResponse(
            id=invoice.id,
            property_id=invoice.property_id,
            folio_id=invoice.folio_id,
            invoice_number=invoice.invoice_number,
            invoice_type=invoice.invoice_type,
            invoice_date=invoice.invoice_date,
            guest_id=invoice.guest_id,
            company_id=invoice.company_id,
            bill_to_name=invoice.bill_to_name,
            bill_to_gstin=invoice.bill_to_gstin,
            bill_to_address=invoice.bill_to_address,
            subtotal=invoice.subtotal,
            tax_total=invoice.tax_total,
            grand_total=invoice.grand_total,
            currency=invoice.currency,
            status=invoice.status,
            original_invoice_id=invoice.original_invoice_id,
            original_invoice_number=invoice.original_invoice.invoice_number if invoice.original_invoice else None,
            issued_at=invoice.issued_at,
            created_at=invoice.created_at,
            booking_number=booking_no,
            property=prop_header,
            lines=lines_resp,
            payments=payments_resp,
            total_paid=total_paid.quantize(Decimal("0.01")),
            balance_due=balance_due,
        )

    async def list_invoices(
        self,
        db: AsyncSession,
        property_id: str,
        invoice_type: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        guest_id: Optional[str] = None,
        company_id: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[InvoiceSummaryResponse]:
        """
        List invoices with multi-field search and flexible filtering.
        """
        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.folio).selectinload(Folio.reservation),
            )
            .where(Invoice.property_id == property_id)
        )

        if invoice_type:
            stmt = stmt.where(Invoice.invoice_type == invoice_type.upper())
        if status:
            stmt = stmt.where(Invoice.status == status.upper())
        if date_from:
            stmt = stmt.where(Invoice.invoice_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.invoice_date <= date_to)
        if guest_id:
            stmt = stmt.where(Invoice.guest_id == guest_id)
        if company_id:
            stmt = stmt.where(Invoice.company_id == company_id)

        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Invoice.invoice_number.ilike(term),
                    Invoice.bill_to_name.ilike(term),
                    Invoice.bill_to_gstin.ilike(term),
                )
            )

        stmt = stmt.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        invoices = list(result.scalars().all())

        summaries: List[InvoiceSummaryResponse] = []
        for inv in invoices:
            booking_no = (
                inv.folio.reservation.booking_number
                if (inv.folio and inv.folio.reservation)
                else None
            )
            summaries.append(
                InvoiceSummaryResponse(
                    id=inv.id,
                    property_id=inv.property_id,
                    folio_id=inv.folio_id,
                    invoice_number=inv.invoice_number,
                    invoice_type=inv.invoice_type,
                    invoice_date=inv.invoice_date,
                    guest_id=inv.guest_id,
                    company_id=inv.company_id,
                    bill_to_name=inv.bill_to_name,
                    bill_to_gstin=inv.bill_to_gstin,
                    subtotal=inv.subtotal,
                    tax_total=inv.tax_total,
                    grand_total=inv.grand_total,
                    currency=inv.currency,
                    status=inv.status,
                    original_invoice_id=inv.original_invoice_id,
                    issued_at=inv.issued_at,
                    created_at=inv.created_at,
                    booking_number=booking_no,
                )
            )
        return summaries

    async def list_folio_invoices(
        self, db: AsyncSession, property_id: str, folio_id: str
    ) -> List[InvoiceSummaryResponse]:
        """
        List all invoices linked to a specific folio.
        """
        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.folio).selectinload(Folio.reservation),
            )
            .where(
                Invoice.property_id == property_id,
                Invoice.folio_id == folio_id,
            )
            .order_by(Invoice.created_at.desc())
        )
        result = await db.execute(stmt)
        invoices = list(result.scalars().all())

        return [
            InvoiceSummaryResponse(
                id=inv.id,
                property_id=inv.property_id,
                folio_id=inv.folio_id,
                invoice_number=inv.invoice_number,
                invoice_type=inv.invoice_type,
                invoice_date=inv.invoice_date,
                guest_id=inv.guest_id,
                company_id=inv.company_id,
                bill_to_name=inv.bill_to_name,
                bill_to_gstin=inv.bill_to_gstin,
                subtotal=inv.subtotal,
                tax_total=inv.tax_total,
                grand_total=inv.grand_total,
                currency=inv.currency,
                status=inv.status,
                original_invoice_id=inv.original_invoice_id,
                issued_at=inv.issued_at,
                created_at=inv.created_at,
                booking_number=inv.folio.reservation.booking_number
                if (inv.folio and inv.folio.reservation)
                else None,
            )
            for inv in invoices
        ]


invoice_service = InvoiceService()
