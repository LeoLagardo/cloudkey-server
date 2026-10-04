import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.folio import (
    Folio,
    Payment,
    FolioTransaction,
    PaymentMethod,
)
from app.models.reservation import Reservation, ReservationRoom
from app.models.guest import Guest
from app.models.property import Property
from app.models.operation import AuditLog
from app.utils.enums import (
    FolioEntryType,
    FolioTransactionType,
    FolioTransactionSource,
    FolioStatus,
    FolioType,
    PaymentStatus,
    PaymentType,
    PaymentMethodType,
)
from app.utils.exceptions import EntityNotFoundException, NotFoundException, ValidationException
from app.schemas.payment import PaymentCreateInput, PaymentDetailResponse


class PaymentService:
    async def get_or_create_payment_method(
        self,
        db: AsyncSession,
        property_id: str,
        method_identifier: str,
    ) -> PaymentMethod:
        """Find payment method by ID or code; auto-create if not found."""
        clean_code = (method_identifier or "CASH").strip().upper()

        stmt = select(PaymentMethod).where(
            PaymentMethod.property_id == property_id,
            or_(
                PaymentMethod.id == method_identifier,
                PaymentMethod.code == clean_code,
            ),
        )
        res = await db.execute(stmt)
        pm = res.scalar_one_or_none()

        if pm:
            return pm

        # Map known types
        type_mapping = {
            "CREDIT_CARD": PaymentMethodType.CARD.value,
            "CARD": PaymentMethodType.CARD.value,
            "DEBIT_CARD": PaymentMethodType.CARD.value,
            "UPI": PaymentMethodType.UPI.value,
            "CASH": PaymentMethodType.CASH.value,
            "BANK_TRANSFER": PaymentMethodType.BANK_TRANSFER.value,
            "NET_BANKING": PaymentMethodType.BANK_TRANSFER.value,
        }
        mapped_type = type_mapping.get(clean_code, PaymentMethodType.CASH.value)
        display_name = clean_code.replace("_", " ").title()

        new_pm = PaymentMethod(
            id=str(uuid.uuid4()),
            property_id=property_id,
            name=display_name,
            code=clean_code,
            method_type=mapped_type,
            status="ACTIVE",
        )
        db.add(new_pm)
        await db.flush()
        return new_pm

    async def record_payment(
        self,
        db: AsyncSession,
        property_id: str,
        payload: PaymentCreateInput,
        current_user_id: Optional[str] = None,
        reservation_id: Optional[str] = None,
    ) -> PaymentDetailResponse:
        """Record a folio payment against a reservation or master folio."""
        target_res_id = reservation_id or payload.reservation_id
        target_folio_id = payload.folio_id

        # 1. Look up property to ensure it exists
        prop_query = await db.execute(select(Property).where(Property.id == property_id))
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        # 2. Resolve reservation and/or folio
        reservation_obj: Optional[Reservation] = None
        folio_obj: Optional[Folio] = None

        if target_res_id:
            res_query = await db.execute(
                select(Reservation)
                .where(
                    or_(
                        Reservation.id == target_res_id,
                        Reservation.booking_number == target_res_id,
                    ),
                    Reservation.property_id == property_id,
                )
                .options(
                    selectinload(Reservation.guest),
                    selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                )
            )
            reservation_obj = res_query.scalar_one_or_none()
            if not reservation_obj:
                raise EntityNotFoundException("Reservation", target_res_id)

            # Look up existing folio
            folio_query = await db.execute(
                select(Folio)
                .where(Folio.reservation_id == reservation_obj.id)
                .order_by(Folio.created_at.asc())
            )
            folio_obj = folio_query.scalars().first()

            if not folio_obj:
                # Open Master Folio if missing
                folio_number = f"FOL-{reservation_obj.booking_number}"
                folio_obj = Folio(
                    property_id=property_id,
                    reservation_id=reservation_obj.id,
                    guest_id=reservation_obj.guest_id,
                    folio_number=folio_number,
                    folio_type=FolioType.GUEST.value,
                    status=FolioStatus.OPEN.value,
                    currency=reservation_obj.currency or property_obj.currency or "INR",
                    opened_at=datetime.now(timezone.utc),
                )
                db.add(folio_obj)
                await db.flush()

        elif target_folio_id:
            folio_query = await db.execute(
                select(Folio).where(
                    Folio.id == target_folio_id,
                    Folio.property_id == property_id,
                )
            )
            folio_obj = folio_query.scalar_one_or_none()
            if not folio_obj:
                raise EntityNotFoundException("Folio", target_folio_id)

            if folio_obj.reservation_id:
                res_query = await db.execute(
                    select(Reservation)
                    .where(Reservation.id == folio_obj.reservation_id)
                    .options(
                        selectinload(Reservation.guest),
                        selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                    )
                )
                reservation_obj = res_query.scalar_one_or_none()
        else:
            raise ValidationException("Either reservation_id or folio_id must be provided to record payment.")

        if not folio_obj:
            raise ValidationException("No valid folio found to post payment.")

        # 3. Resolve payment method
        pm_obj = await self.get_or_create_payment_method(
            db, property_id=property_id, method_identifier=payload.payment_method
        )

        currency = payload.currency or folio_obj.currency or (reservation_obj.currency if reservation_obj else None) or property_obj.currency or "INR"
        payment_type = payload.payment_type or PaymentType.SETTLEMENT.value
        status_val = payload.status or PaymentStatus.CAPTURED.value
        amount_val = Decimal(str(payload.amount))

        # 4. Create Payment row
        payment = Payment(
            property_id=property_id,
            folio_id=folio_obj.id,
            reservation_id=reservation_obj.id if reservation_obj else None,
            payment_method_id=pm_obj.id,
            payment_type=payment_type,
            status=status_val,
            amount=amount_val,
            currency=currency,
            gateway=payload.gateway,
            gateway_reference=payload.gateway_reference,
            card_last4=payload.card_last4,
            notes=payload.notes,
            received_by=current_user_id,
            received_at=datetime.now(timezone.utc),
        )
        db.add(payment)
        await db.flush()

        # 5. Create Folio Transaction CREDIT
        business_date = property_obj.business_date or datetime.now(timezone.utc).date()
        desc_notes = f" (Ref: {payload.gateway_reference})" if payload.gateway_reference else ""
        folio_txn = FolioTransaction(
            property_id=property_id,
            folio_id=folio_obj.id,
            business_date=business_date,
            entry_type=FolioEntryType.CREDIT.value,
            transaction_type=FolioTransactionType.PAYMENT.value,
            payment_id=payment.id,
            description=f"Payment received via {pm_obj.name}{desc_notes}",
            quantity=Decimal("1.00"),
            unit_price=amount_val,
            amount=amount_val,
            tax_amount=Decimal("0.00"),
            total_amount=amount_val,
            source=FolioTransactionSource.MANUAL.value,
            posted_by=current_user_id,
            posted_at=datetime.now(timezone.utc),
        )
        db.add(folio_txn)

        # 6. Audit Log
        audit = AuditLog(
            organization_id=property_obj.organization_id,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="payments",
            entity_id=payment.id,
            action="CREATE",
            old_values=None,
            new_values={
                "amount": str(amount_val),
                "currency": currency,
                "folio_id": folio_obj.id,
                "reservation_id": reservation_obj.id if reservation_obj else None,
                "payment_method": pm_obj.name,
                "reference": payload.gateway_reference,
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(payment)

        # Room number from reservation if assigned
        room_number = None
        if reservation_obj and reservation_obj.rooms:
            assigned_rooms = [r.room.room_number for r in reservation_obj.rooms if r.room and r.room.room_number]
            if assigned_rooms:
                room_number = assigned_rooms[0]

        guest_name = None
        guest_email = None
        guest_phone = None
        if reservation_obj and reservation_obj.guest:
            g = reservation_obj.guest
            guest_name = f"{g.first_name} {g.last_name or ''}".strip()
            guest_email = g.email
            guest_phone = g.phone

        return PaymentDetailResponse(
            id=payment.id,
            property_id=payment.property_id,
            folio_id=payment.folio_id,
            reservation_id=payment.reservation_id,
            payment_method_id=payment.payment_method_id,
            payment_method_name=pm_obj.name,
            payment_method_code=pm_obj.code,
            payment_type=payment.payment_type,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            gateway=payment.gateway,
            gateway_reference=payment.gateway_reference,
            card_last4=payment.card_last4,
            notes=payment.notes,
            received_at=payment.received_at,
            received_by=payment.received_by,
            booking_number=reservation_obj.booking_number if reservation_obj else None,
            folio_number=folio_obj.folio_number if folio_obj else None,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            room_number=room_number,
        )

    async def list_payments(
        self,
        db: AsyncSession,
        property_id: str,
        status: Optional[str] = None,
        payment_method: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PaymentDetailResponse]:
        """List all payments for a property with enriched booking and guest context."""
        query = (
            select(Payment)
            .where(Payment.property_id == property_id)
            .options(
                selectinload(Payment.folio),
                selectinload(Payment.payment_method),
                selectinload(Payment.reservation).selectinload(Reservation.guest),
                selectinload(Payment.reservation).selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
            )
            .order_by(Payment.received_at.desc())
        )

        if status and status != "ALL":
            query = query.where(Payment.status == status)

        query = query.offset(skip).limit(limit)
        res = await db.execute(query)
        payments = list(res.scalars().all())

        results: List[PaymentDetailResponse] = []
        for p in payments:
            pm = p.payment_method
            res_obj = p.reservation
            folio_obj = p.folio

            guest_name = None
            guest_email = None
            guest_phone = None
            room_number = None

            if res_obj and res_obj.guest:
                g = res_obj.guest
                guest_name = f"{g.first_name} {g.last_name or ''}".strip()
                guest_email = g.email
                guest_phone = g.phone

            if res_obj and res_obj.rooms:
                assigned = [r.room.room_number for r in res_obj.rooms if r.room and r.room.room_number]
                if assigned:
                    room_number = assigned[0]

            item = PaymentDetailResponse(
                id=p.id,
                property_id=p.property_id,
                folio_id=p.folio_id,
                reservation_id=p.reservation_id,
                payment_method_id=p.payment_method_id,
                payment_method_name=pm.name if pm else p.payment_method_id,
                payment_method_code=pm.code if pm else None,
                payment_type=p.payment_type,
                status=p.status,
                amount=p.amount,
                currency=p.currency,
                gateway=p.gateway,
                gateway_reference=p.gateway_reference,
                card_last4=p.card_last4,
                notes=p.notes,
                received_at=p.received_at,
                received_by=p.received_by,
                booking_number=res_obj.booking_number if res_obj else None,
                folio_number=folio_obj.folio_number if folio_obj else None,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                room_number=room_number,
            )

            # Apply in-memory search filter if search term provided
            if search:
                term = search.strip().lower()
                matches = (
                    term in (item.id or "").lower()
                    or term in (item.booking_number or "").lower()
                    or term in (item.folio_number or "").lower()
                    or term in (item.guest_name or "").lower()
                    or term in (item.guest_email or "").lower()
                    or term in (item.gateway_reference or "").lower()
                    or term in (item.payment_method_name or "").lower()
                )
                if not matches:
                    continue

            results.append(item)

        return results


payment_service = PaymentService()
