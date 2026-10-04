import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folio import (
    Folio,
    FolioTransaction,
    FolioTransactionTax,
)
from app.models.operation import AuditLog
from app.models.property import Property
from app.models.reservation import Reservation, ReservationRoom
from app.models.service import Service
from app.models.tax import Tax, TaxGroup, TaxGroupItem, TaxRate
from app.schemas.folio import (
    FolioDetailResponse,
    FolioTransactionResponse,
    FolioTransactionTaxResponse,
    PostServiceChargeRequest,
)
from app.utils.enums import (
    EntityStatus,
    FolioEntryType,
    FolioStatus,
    FolioTransactionSource,
    FolioTransactionType,
    FolioType,
    TaxRateType,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException


class FolioService:
    async def get_or_create_master_folio(
        self,
        db: AsyncSession,
        property_id: str,
        reservation: Reservation,
        currency: Optional[str] = None,
    ) -> Folio:
        query = await db.execute(
            select(Folio)
            .where(Folio.reservation_id == reservation.id)
            .order_by(Folio.created_at.asc())
        )
        folio = query.scalars().first()
        if not folio:
            folio_number = f"FOL-{reservation.booking_number}"
            folio = Folio(
                property_id=property_id,
                reservation_id=reservation.id,
                guest_id=reservation.guest_id,
                folio_number=folio_number,
                folio_type=FolioType.GUEST.value,
                status=FolioStatus.OPEN.value,
                currency=currency or reservation.currency or "INR",
                opened_at=datetime.now(timezone.utc),
            )
            db.add(folio)
            await db.flush()
        return folio

    async def post_service_charge(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        payload: PostServiceChargeRequest,
        current_user_id: Optional[str] = None,
    ) -> FolioTransactionResponse:
        # 1. Verify property
        prop_query = await db.execute(select(Property).where(Property.id == property_id))
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        # 2. Verify reservation
        res_query = await db.execute(
            select(Reservation)
            .where(
                or_(
                    Reservation.id == reservation_id,
                    Reservation.booking_number == reservation_id,
                ),
                Reservation.property_id == property_id,
            )
        )
        reservation = res_query.scalar_one_or_none()
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        # 3. Resolve Folio
        folio = await self.get_or_create_master_folio(
            db, property_id, reservation, property_obj.currency
        )

        # 4. Resolve Service
        srv_query = await db.execute(
            select(Service)
            .options(selectinload(Service.tax_group))
            .where(
                Service.id == payload.service_id,
                Service.property_id == property_id,
            )
        )
        service = srv_query.scalar_one_or_none()
        if not service:
            raise EntityNotFoundException("Service", payload.service_id)

        if service.status != EntityStatus.ACTIVE.value:
            raise ValidationException(f"Service '{service.name}' is inactive and cannot be consumed.")

        # 5. Determine unit price & quantity
        if payload.unit_price is not None:
            unit_price = Decimal(str(payload.unit_price))
        elif service.default_price is not None:
            unit_price = Decimal(str(service.default_price))
        else:
            raise ValidationException(
                f"Service '{service.name}' has OPEN pricing; please provide a unit_price."
            )

        quantity = Decimal(str(payload.quantity))
        line_total = (unit_price * quantity).quantize(Decimal("0.01"))

        business_date = (
            payload.business_date
            or property_obj.business_date
            or datetime.now(timezone.utc).date()
        )

        # 6. Calculate Taxes
        tax_components = []
        total_tax = Decimal("0.00")
        taxable_amount = line_total

        if service.tax_group_id:
            tg_query = await db.execute(
                select(TaxGroup)
                .options(selectinload(TaxGroup.items))
                .where(
                    TaxGroup.id == service.tax_group_id,
                    TaxGroup.status == EntityStatus.ACTIVE.value,
                )
            )
            tax_group = tg_query.scalar_one_or_none()

            if tax_group and tax_group.items:
                rates_data = []
                total_percentage = Decimal("0.00")

                for item in tax_group.items:
                    # Query active rate
                    rate_q = await db.execute(
                        select(TaxRate)
                        .where(
                            TaxRate.tax_id == item.tax_id,
                            TaxRate.valid_from <= business_date,
                            or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= business_date),
                            or_(TaxRate.min_amount.is_(None), TaxRate.min_amount <= line_total),
                            or_(TaxRate.max_amount.is_(None), TaxRate.max_amount >= line_total),
                        )
                        .order_by(TaxRate.created_at.desc())
                    )
                    tax_rate = rate_q.scalars().first()

                    # Query tax name
                    tax_q = await db.execute(select(Tax).where(Tax.id == item.tax_id))
                    tax_entity = tax_q.scalar_one_or_none()
                    tax_name = tax_entity.name if tax_entity else "Tax"

                    if tax_rate:
                        rates_data.append({
                            "tax_id": item.tax_id,
                            "tax_rate_id": tax_rate.id,
                            "tax_name": tax_name,
                            "rate_type": tax_rate.rate_type,
                            "rate": tax_rate.rate,
                        })
                        if tax_rate.rate_type == TaxRateType.PERCENTAGE.value:
                            total_percentage += tax_rate.rate

                if service.is_tax_inclusive and total_percentage > 0:
                    # Tax inclusive: Base = line_total / (1 + sum_rate/100)
                    taxable_amount = (line_total / (Decimal("1.00") + (total_percentage / Decimal("100")))).quantize(Decimal("0.01"))
                    total_tax = line_total - taxable_amount
                    for r in rates_data:
                        if r["rate_type"] == TaxRateType.PERCENTAGE.value:
                            comp_tax = (taxable_amount * r["rate"] / Decimal("100")).quantize(Decimal("0.01"))
                        else:
                            comp_tax = r["rate"].quantize(Decimal("0.01"))
                        tax_components.append({
                            "tax_id": r["tax_id"],
                            "tax_rate_id": r["tax_rate_id"],
                            "tax_name": r["tax_name"],
                            "rate": r["rate"],
                            "taxable_amount": taxable_amount,
                            "tax_amount": comp_tax,
                        })
                else:
                    # Tax exclusive: Tax = Base * rate / 100
                    taxable_amount = line_total
                    for r in rates_data:
                        if r["rate_type"] == TaxRateType.PERCENTAGE.value:
                            comp_tax = (taxable_amount * r["rate"] / Decimal("100")).quantize(Decimal("0.01"))
                        else:
                            comp_tax = r["rate"].quantize(Decimal("0.01"))
                        total_tax += comp_tax
                        tax_components.append({
                            "tax_id": r["tax_id"],
                            "tax_rate_id": r["tax_rate_id"],
                            "tax_name": r["tax_name"],
                            "rate": r["rate"],
                            "taxable_amount": taxable_amount,
                            "tax_amount": comp_tax,
                        })

        if service.is_tax_inclusive:
            charge_total = line_total
            base_amount = taxable_amount
        else:
            base_amount = line_total
            charge_total = line_total + total_tax

        # 7. Create FolioTransaction
        description = payload.custom_description or f"{service.name} x {quantity}"
        folio_txn = FolioTransaction(
            property_id=property_id,
            folio_id=folio.id,
            business_date=business_date,
            entry_type=FolioEntryType.DEBIT.value,
            transaction_type=FolioTransactionType.SERVICE_CHARGE.value,
            service_id=service.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            amount=base_amount,
            tax_amount=total_tax,
            total_amount=charge_total,
            tax_group_id=service.tax_group_id,
            is_tax_inclusive=service.is_tax_inclusive,
            hsn_sac_code=service.hsn_sac_code,
            source=FolioTransactionSource.MANUAL.value,
            posted_by=current_user_id,
            posted_at=datetime.now(timezone.utc),
        )
        db.add(folio_txn)
        await db.flush()

        # 8. Create FolioTransactionTax records
        tax_responses = []
        for comp in tax_components:
            txn_tax = FolioTransactionTax(
                id=str(uuid.uuid4()),
                folio_transaction_id=folio_txn.id,
                tax_id=comp["tax_id"],
                tax_rate_id=comp["tax_rate_id"],
                tax_name=comp["tax_name"],
                rate=comp["rate"],
                taxable_amount=comp["taxable_amount"],
                tax_amount=comp["tax_amount"],
            )
            db.add(txn_tax)
            tax_responses.append(
                FolioTransactionTaxResponse(
                    id=txn_tax.id,
                    tax_id=txn_tax.tax_id,
                    tax_rate_id=txn_tax.tax_rate_id,
                    tax_name=txn_tax.tax_name,
                    rate=txn_tax.rate,
                    taxable_amount=txn_tax.taxable_amount,
                    tax_amount=txn_tax.tax_amount,
                )
            )
        await db.flush()

        # 9. Audit log
        audit = AuditLog(
            organization_id=property_obj.organization_id,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="folio_transactions",
            entity_id=folio_txn.id,
            action="CREATE",
            old_values=None,
            new_values={
                "transaction_type": folio_txn.transaction_type,
                "service_id": service.id,
                "service_name": service.name,
                "total_amount": str(charge_total),
            },
        )
        db.add(audit)
        await db.flush()
        await db.refresh(folio_txn)

        return FolioTransactionResponse(
            id=folio_txn.id,
            property_id=folio_txn.property_id,
            folio_id=folio_txn.folio_id,
            business_date=folio_txn.business_date,
            entry_type=folio_txn.entry_type,
            transaction_type=folio_txn.transaction_type,
            service_id=service.id,
            service_name=service.name,
            service_category=service.category,
            payment_id=None,
            description=folio_txn.description,
            quantity=folio_txn.quantity,
            unit_price=folio_txn.unit_price,
            amount=folio_txn.amount,
            tax_amount=folio_txn.tax_amount,
            total_amount=folio_txn.total_amount,
            tax_group_id=folio_txn.tax_group_id,
            is_tax_inclusive=folio_txn.is_tax_inclusive,
            hsn_sac_code=folio_txn.hsn_sac_code,
            source=folio_txn.source,
            posted_by=folio_txn.posted_by,
            posted_at=folio_txn.posted_at,
            taxes=tax_responses,
        )

    async def get_reservation_folio_details(
        self, db: AsyncSession, property_id: str, reservation_id: str
    ) -> FolioDetailResponse:
        # Find reservation
        res_query = await db.execute(
            select(Reservation).where(
                or_(
                    Reservation.id == reservation_id,
                    Reservation.booking_number == reservation_id,
                ),
                Reservation.property_id == property_id,
            )
        )
        reservation = res_query.scalar_one_or_none()
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        folio = await self.get_or_create_master_folio(
            db, property_id, reservation
        )

        # Load folio transactions with taxes and service
        txn_query = await db.execute(
            select(FolioTransaction)
            .options(
                selectinload(FolioTransaction.taxes),
                selectinload(FolioTransaction.service),
            )
            .where(FolioTransaction.folio_id == folio.id)
            .order_by(FolioTransaction.posted_at.asc())
        )
        transactions = list(txn_query.scalars().all())

        total_charges = Decimal("0.00")
        total_payments = Decimal("0.00")
        tx_responses: List[FolioTransactionResponse] = []

        for txn in transactions:
            if txn.entry_type == FolioEntryType.DEBIT.value:
                total_charges += txn.total_amount
            elif txn.entry_type == FolioEntryType.CREDIT.value:
                total_payments += txn.total_amount

            taxes_resp = [
                FolioTransactionTaxResponse(
                    id=t.id,
                    tax_id=t.tax_id,
                    tax_rate_id=t.tax_rate_id,
                    tax_name=t.tax_name,
                    rate=t.rate,
                    taxable_amount=t.taxable_amount,
                    tax_amount=t.tax_amount,
                )
                for t in txn.taxes
            ]

            tx_responses.append(
                FolioTransactionResponse(
                    id=txn.id,
                    property_id=txn.property_id,
                    folio_id=txn.folio_id,
                    business_date=txn.business_date,
                    entry_type=txn.entry_type,
                    transaction_type=txn.transaction_type,
                    service_id=txn.service_id,
                    service_name=txn.service.name if txn.service else None,
                    service_category=txn.service.category if txn.service else None,
                    payment_id=txn.payment_id,
                    description=txn.description,
                    quantity=txn.quantity,
                    unit_price=txn.unit_price,
                    amount=txn.amount,
                    tax_amount=txn.tax_amount,
                    total_amount=txn.total_amount,
                    tax_group_id=txn.tax_group_id,
                    is_tax_inclusive=txn.is_tax_inclusive,
                    hsn_sac_code=txn.hsn_sac_code,
                    source=txn.source,
                    posted_by=txn.posted_by,
                    posted_at=txn.posted_at,
                    taxes=taxes_resp,
                )
            )

        balance_due = (total_charges - total_payments).quantize(Decimal("0.01"))

        return FolioDetailResponse(
            id=folio.id,
            property_id=folio.property_id,
            reservation_id=folio.reservation_id,
            folio_number=folio.folio_number,
            folio_type=folio.folio_type,
            status=folio.status,
            currency=folio.currency,
            opened_at=folio.opened_at,
            closed_at=folio.closed_at,
            total_charges=total_charges.quantize(Decimal("0.01")),
            total_payments=total_payments.quantize(Decimal("0.01")),
            balance_due=balance_due,
            transactions=tx_responses,
        )


folio_service = FolioService()
