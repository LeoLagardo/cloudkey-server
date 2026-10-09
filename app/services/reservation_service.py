import secrets
import string
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import select, and_, or_, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.guest import crud_guest
from app.crud.reservation import crud_reservation
from app.models.folio import Folio, FolioTransaction, Payment, PaymentMethod
from app.models.operation import AuditLog
from app.models.property import Property
from app.models.property_settings import PropertySettings
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate
from app.models.reservation import (
    Reservation,
    ReservationGuest,
    ReservationRoom,
    ReservationRoomRate,
    RoomBlock,
)
from app.models.room import Room
from app.models.room_type import RoomType
from app.models.tax import TaxGroup, TaxGroupItem, TaxRate
from app.schemas.reservation import (
    ReservationCreate,
    ReservationResponse,
    FolioSummaryResponse,
    PaymentSummaryResponse,
    GuestSummaryResponse,
    ReservationCheckInRequest,
    ReservationCheckOutRequest,
)
from app.utils.enums import (
    BookingType,
    EntityStatus,
    FolioEntryType,
    FolioStatus,
    FolioTransactionSource,
    FolioTransactionType,
    FolioType,
    HousekeepingStatus,
    OccupancyStatus,
    PaymentStatus,
    PaymentType,
    ReservationStatus,
    RoomStatus,
    TaxRateType,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException


class ReservationService:
    @staticmethod
    def _generate_random_code(length: int = 6) -> str:
        """Generate uppercase alphanumeric random string omitting ambiguous characters."""
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def generate_booking_number(self, db: AsyncSession, property_code: str) -> str:
        """
        Generate collision-free booking number with hotel code prefix:
        Format: {HOTEL_CODE}-{YYMM}-{6_CHAR_RANDOM}
        """
        clean_prefix = (property_code or "BK").upper().strip().replace(" ", "")[:6]
        period = datetime.now(timezone.utc).strftime("%y%m")

        for _ in range(10):
            random_part = self._generate_random_code(6)
            candidate = f"{clean_prefix}-{period}-{random_part}"

            # Check uniqueness against DB
            exists = await crud_reservation.get_by_booking_number(
                db, property_id="", booking_number=candidate
            )
            # If property_id check in get_by_booking_number is property-scoped, also verify globally
            result = await db.execute(
                select(Reservation.id).where(Reservation.booking_number == candidate)
            )
            if not result.scalar_one_or_none():
                return candidate

        # Fallback with timestamp microsecond suffix
        return f"{clean_prefix}-{period}-{secrets.token_hex(4).upper()}"

    def generate_folio_number(self, property_code: str) -> str:
        """Generate unique folio number with hotel code prefix."""
        clean_prefix = (property_code or "PROP").upper().strip().replace(" ", "")[:6]
        period = datetime.now(timezone.utc).strftime("%y%m")
        random_part = self._generate_random_code(6)
        return f"FOL-{clean_prefix}-{period}-{random_part}"

    async def _calculate_taxes_for_rate(
        self,
        db: AsyncSession,
        tax_group_id: Optional[str],
        base_amount: Decimal,
        stay_date: date,
    ) -> Decimal:
        """Calculate total tax amount based on RatePlan's TaxGroup and active TaxRates."""
        if not tax_group_id:
            return Decimal("0.00")

        # Load tax group with items
        result = await db.execute(
            select(TaxGroup)
            .where(TaxGroup.id == tax_group_id, TaxGroup.status == EntityStatus.ACTIVE.value)
            .options(selectinload(TaxGroup.items))
        )
        tax_group = result.scalar_one_or_none()
        if not tax_group or not tax_group.items:
            return Decimal("0.00")

        total_tax = Decimal("0.00")
        for item in tax_group.items:
            # Query active rate for this tax
            rate_query = await db.execute(
                select(TaxRate)
                .where(
                    TaxRate.tax_id == item.tax_id,
                    TaxRate.valid_from <= stay_date,
                    or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= stay_date),
                    or_(TaxRate.min_amount.is_(None), TaxRate.min_amount <= base_amount),
                    or_(TaxRate.max_amount.is_(None), TaxRate.max_amount >= base_amount),
                )
                .order_by(TaxRate.created_at.desc())
            )
            tax_rate = rate_query.scalars().first()
            if tax_rate:
                if tax_rate.rate_type == TaxRateType.PERCENTAGE.value:
                    tax_for_item = (base_amount * tax_rate.rate) / Decimal("100")
                else:
                    tax_for_item = tax_rate.rate
                total_tax += tax_for_item

        return total_tax.quantize(Decimal("0.01"))

    async def create_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        res_in: ReservationCreate,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Executes atomic multi-table reservation creation:
        1. Validates property, room types, rate plans, and optional advance payment method.
        2. Generates hotel-code-prefixed booking number and folio number.
        3. Finds or creates the booker in the `guests` table.
        4. Snapshots daily or hourly rates from `rate_plan_rates` into `reservation_room_rates`.
        5. Inserts `reservations` (status=CONFIRMED) and `reservation_rooms`.
        6. Links occupants via `reservation_guests`.
        7. Creates 1 OPEN `folios` record.
        8. If advance payment provided: inserts `payments` and `folio_transactions` (CREDIT, PAYMENT).
        9. Inserts 1 row in `audit_logs`.
        """
        # 1. Fetch & Validate Property
        property_obj = await db.get(Property, property_id)
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        # 2. Validate Payment Method if advance payment is provided
        payment_method = None
        if res_in.advance_payment:
            pm_result = await db.execute(
                select(PaymentMethod).where(
                    PaymentMethod.id == res_in.advance_payment.payment_method_id,
                    PaymentMethod.property_id == property_id,
                    PaymentMethod.status == EntityStatus.ACTIVE.value,
                )
            )
            payment_method = pm_result.scalar_one_or_none()
            if not payment_method:
                raise ValidationException("Specified payment method not found or inactive for this property.")

        # 3. Validate Room Types & Rate Plans
        for room_in in res_in.rooms:
            rt = await db.get(RoomType, room_in.room_type_id)
            if not rt or rt.property_id != property_id:
                raise ValidationException(f"Room type '{room_in.room_type_id}' is invalid for this property.")

            rp = await db.get(RatePlan, room_in.rate_plan_id)
            if not rp or rp.property_id != property_id or rp.room_type_id != room_in.room_type_id:
                raise ValidationException(f"Rate plan '{room_in.rate_plan_id}' does not match room type.")

            if room_in.check_in_at >= room_in.check_out_at:
                raise ValidationException("Check-in time must be before check-out time.")

            if room_in.room_id:
                room_obj = await db.get(Room, room_in.room_id)
                if not room_obj or room_obj.property_id != property_id or room_obj.room_type_id != room_in.room_type_id:
                    raise ValidationException(f"Room '{room_in.room_id}' is invalid or does not match room type.")

        # 4. Hot-Path Inventory Allocation & Lock
        room_demands: Dict[str, List[date]] = {}
        for room_in in res_in.rooms:
            start_d = room_in.check_in_at.date()
            end_d = room_in.check_out_at.date()
            num_nights = max(1, (end_d - start_d).days)
            stay_dates = [start_d + timedelta(days=i) for i in range(num_nights)]

            if room_in.room_type_id not in room_demands:
                room_demands[room_in.room_type_id] = []
            room_demands[room_in.room_type_id].extend(stay_dates)

            # Slower fallback/audit check on physical room overlap if room_id is specified
            if room_in.room_id:
                overlap_res = await db.execute(
                    select(ReservationRoom.id).where(
                        ReservationRoom.room_id == room_in.room_id,
                        ReservationRoom.status.in_([
                            ReservationStatus.CONFIRMED.value,
                            ReservationStatus.CHECKED_IN.value,
                        ]),
                        ReservationRoom.check_in_at < room_in.check_out_at,
                        ReservationRoom.check_out_at > room_in.check_in_at,
                    )
                )
                if overlap_res.scalar_one_or_none():
                    raise ValidationException(
                        f"Room '{room_in.room_id}' has an existing overlapping reservation."
                    )

                block_res = await db.execute(
                    select(RoomBlock).where(
                        RoomBlock.room_id == room_in.room_id,
                        RoomBlock.start_at < room_in.check_out_at,
                        RoomBlock.end_at > room_in.check_in_at,
                    )
                )
                active_blk = block_res.scalars().first()
                if active_blk:
                    raise ValidationException(
                        f"Room '{room_in.room_id}' is blocked ({active_blk.block_type}) between {active_blk.start_at.strftime('%Y-%m-%d')} and {active_blk.end_at.strftime('%Y-%m-%d')}."
                    )

        from app.services.inventory_service import inventory_service
        await inventory_service.lock_and_reserve(
            db, property_id=property_id, room_demands=room_demands
        )

        # 5. Generate Unique Booking Number with Hotel Code Prefix
        booking_number = await self.generate_booking_number(db, property_code=property_obj.code)

        # 6. Find or Create Booker in `guests` (scoped to organization)
        booker = await crud_guest.find_or_create(
            db,
            organization_id=property_obj.organization_id,
            guest_data=res_in.booker,
        )

        # Determine overall reservation check-in and check-out
        res_check_in = min(r.check_in_at for r in res_in.rooms)
        res_check_out = max(r.check_out_at for r in res_in.rooms)

        # 7. Initialize Reservation Model
        reservation = Reservation(
            property_id=property_id,
            booking_number=booking_number,
            guest_id=booker.id,
            company_id=res_in.company_id,
            booking_type=res_in.booking_type.value,
            source=res_in.source.value,
            channel_name=res_in.channel_name,
            channel_booking_ref=res_in.channel_booking_ref,
            status=ReservationStatus.CONFIRMED.value,
            check_in_at=res_check_in,
            check_out_at=res_check_out,
            currency=res_in.currency or property_obj.currency or "INR",
            special_requests=res_in.special_requests,
            created_by=current_user_id,
        )
        db.add(reservation)
        await db.flush()

        res_total_amount = Decimal("0.00")
        res_total_tax = Decimal("0.00")

        # 7. Process Rooms, Occupants & Rate Snapshots
        for room_in in res_in.rooms:
            res_room = ReservationRoom(
                reservation_id=reservation.id,
                room_type_id=room_in.room_type_id,
                room_id=room_in.room_id,  # Can remain NULL until check-in
                rate_plan_id=room_in.rate_plan_id,
                status=ReservationStatus.CONFIRMED.value,
                check_in_at=room_in.check_in_at,
                check_out_at=room_in.check_out_at,
                adults=room_in.adults,
                children=room_in.children,
            )
            db.add(res_room)
            await db.flush()

            # Room Occupants (reservation_guests)
            if room_in.guests:
                for guest_in in room_in.guests:
                    occ_guest = await crud_guest.find_or_create(
                        db,
                        organization_id=property_obj.organization_id,
                        guest_data=guest_in,
                    )
                    res_guest = ReservationGuest(
                        reservation_room_id=res_room.id,
                        guest_id=occ_guest.id,
                        is_primary=guest_in.is_primary,
                    )
                    db.add(res_guest)
            else:
                # Default primary occupant is the booker
                res_guest = ReservationGuest(
                    reservation_room_id=res_room.id,
                    guest_id=booker.id,
                    is_primary=True,
                )
                db.add(res_guest)

            # Rate Snapshotting (reservation_room_rates)
            rate_plan = await db.get(RatePlan, room_in.rate_plan_id)
            start_date = room_in.check_in_at.date()
            end_date = room_in.check_out_at.date()

            # Calculate nights or 1 night min if same-day
            num_nights = max(1, (end_date - start_date).days)
            for night_idx in range(num_nights):
                stay_date = start_date + timedelta(days=night_idx)

                # Query active RatePlanRate matching stay_date
                rate_query = await db.execute(
                    select(RatePlanRate).where(
                        RatePlanRate.rate_plan_id == room_in.rate_plan_id,
                        or_(RatePlanRate.valid_from.is_(None), RatePlanRate.valid_from <= stay_date),
                        or_(RatePlanRate.valid_to.is_(None), RatePlanRate.valid_to >= stay_date),
                    ).order_by(RatePlanRate.created_at.desc())
                )
                matched_rate = rate_query.scalars().first()

                if not matched_rate:
                    # Fallback to any active rate under this rate plan
                    fallback_query = await db.execute(
                        select(RatePlanRate).where(
                            RatePlanRate.rate_plan_id == room_in.rate_plan_id
                        ).order_by(RatePlanRate.created_at.desc())
                    )
                    matched_rate = fallback_query.scalars().first()

                if not matched_rate:
                    raise ValidationException(
                        f"No rate configured for rate plan '{rate_plan.name if rate_plan else room_in.rate_plan_id}' on {stay_date}."
                    )

                base_price = matched_rate.price
                extra_person = Decimal("0.00")
                discount = Decimal("0.00")
                net_price = base_price + extra_person - discount

                tax_price = await self._calculate_taxes_for_rate(
                    db,
                    tax_group_id=rate_plan.tax_group_id if rate_plan else None,
                    base_amount=net_price,
                    stay_date=stay_date,
                )
                total_night = net_price + tax_price

                res_room_rate = ReservationRoomRate(
                    reservation_room_id=res_room.id,
                    stay_date=stay_date,
                    rate_plan_rate_id=matched_rate.id,
                    base_amount=base_price,
                    extra_person_amount=extra_person,
                    discount_amount=discount,
                    net_amount=net_price,
                    tax_amount=tax_price,
                    total_amount=total_night,
                )
                db.add(res_room_rate)

                res_total_amount += total_night
                res_total_tax += tax_price

        # Update reservation grand totals
        reservation.total_amount = res_total_amount
        reservation.total_tax_amount = res_total_tax
        await db.flush()

        # 8. Create 1 OPEN Master Folio
        folio_number = self.generate_folio_number(property_code=property_obj.code)
        folio = Folio(
            property_id=property_id,
            reservation_id=reservation.id,
            guest_id=booker.id,
            folio_number=folio_number,
            folio_type=FolioType.GUEST.value,
            status=FolioStatus.OPEN.value,
            currency=reservation.currency,
            opened_at=datetime.now(timezone.utc),
        )
        db.add(folio)
        await db.flush()

        # 9. Handle Optional Advance Payment & Folio Transaction
        payment_record = None
        if res_in.advance_payment:
            adv = res_in.advance_payment
            payment_record = Payment(
                property_id=property_id,
                folio_id=folio.id,
                reservation_id=reservation.id,
                payment_method_id=adv.payment_method_id,
                payment_type=PaymentType.ADVANCE.value,
                status=PaymentStatus.CAPTURED.value,
                amount=adv.amount,
                currency=reservation.currency,
                gateway=adv.gateway,
                gateway_reference=adv.gateway_reference,
                card_last4=adv.card_last4,
                notes=adv.notes,
                received_by=current_user_id,
                received_at=datetime.now(timezone.utc),
            )
            db.add(payment_record)
            await db.flush()

            # Record Ledger Credit row in folio_transactions
            business_date = property_obj.business_date or datetime.now(timezone.utc).date()
            folio_txn = FolioTransaction(
                property_id=property_id,
                folio_id=folio.id,
                business_date=business_date,
                entry_type=FolioEntryType.CREDIT.value,
                transaction_type=FolioTransactionType.PAYMENT.value,
                payment_id=payment_record.id,
                description=f"Advance payment received via {payment_method.name if payment_method else 'payment method'}",
                quantity=Decimal("1.00"),
                unit_price=adv.amount,
                amount=adv.amount,
                tax_amount=Decimal("0.00"),
                total_amount=adv.amount,
                source=FolioTransactionSource.MANUAL.value,
                posted_by=current_user_id,
                posted_at=datetime.now(timezone.utc),
            )
            db.add(folio_txn)
            await db.flush()

        # 10. Record Audit Log
        audit_log = AuditLog(
            organization_id=property_obj.organization_id,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="CREATE",
            old_values=None,
            new_values={
                "booking_number": reservation.booking_number,
                "guest_id": booker.id,
                "status": reservation.status,
                "rooms_count": len(res_in.rooms),
                "total_amount": str(reservation.total_amount),
                "total_tax_amount": str(reservation.total_tax_amount),
                "advance_payment": str(res_in.advance_payment.amount) if res_in.advance_payment else "0.00",
                "folio_number": folio.folio_number,
            },
        )
        db.add(audit_log)

        # Commit Entire Atomic Transaction
        await db.commit()

        # 11. Return Hydrated Response
        fresh_res = await crud_reservation.get_by_id(db, reservation_id=reservation.id)
        if not fresh_res:
            raise ValidationException("Failed to reload created reservation.")

        payments_list = [payment_record] if payment_record else []
        return ReservationResponse(
            id=fresh_res.id,
            property_id=fresh_res.property_id,
            booking_number=fresh_res.booking_number,
            guest_id=fresh_res.guest_id,
            company_id=fresh_res.company_id,
            booking_type=fresh_res.booking_type,
            source=fresh_res.source,
            channel_name=fresh_res.channel_name,
            channel_booking_ref=fresh_res.channel_booking_ref,
            status=fresh_res.status,
            check_in_at=fresh_res.check_in_at,
            check_out_at=fresh_res.check_out_at,
            currency=fresh_res.currency,
            total_amount=fresh_res.total_amount,
            total_tax_amount=fresh_res.total_tax_amount,
            special_requests=fresh_res.special_requests,
            created_at=fresh_res.created_at,
            updated_at=fresh_res.updated_at,
            booker=GuestSummaryResponse.model_validate(fresh_res.guest) if fresh_res.guest else None,
            rooms=fresh_res.rooms,
            folio=FolioSummaryResponse.model_validate(folio) if folio else None,
            payments=[PaymentSummaryResponse.model_validate(p) for p in payments_list],
        )

    async def get_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
    ) -> ReservationResponse:
        """Retrieve a reservation with its rooms, folio, and payments."""
        reservation = await crud_reservation.get_by_id(
            db, reservation_id=reservation_id, property_id=property_id
        )
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        folio = await crud_reservation.get_reservation_folio(db, reservation_id=reservation.id)
        payments = await crud_reservation.get_reservation_payments(db, reservation_id=reservation.id)

        return ReservationResponse(
            id=reservation.id,
            property_id=reservation.property_id,
            booking_number=reservation.booking_number,
            guest_id=reservation.guest_id,
            company_id=reservation.company_id,
            booking_type=reservation.booking_type,
            source=reservation.source,
            channel_name=reservation.channel_name,
            channel_booking_ref=reservation.channel_booking_ref,
            status=reservation.status,
            check_in_at=reservation.check_in_at,
            check_out_at=reservation.check_out_at,
            currency=reservation.currency,
            total_amount=reservation.total_amount,
            total_tax_amount=reservation.total_tax_amount,
            special_requests=reservation.special_requests,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
            cancelled_at=reservation.cancelled_at,
            cancellation_reason=reservation.cancellation_reason,
            booker=GuestSummaryResponse.model_validate(reservation.guest) if reservation.guest else None,
            rooms=reservation.rooms,
            folio=FolioSummaryResponse.model_validate(folio) if folio else None,
            payments=[PaymentSummaryResponse.model_validate(p) for p in payments],
        )

    async def assign_room(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        reservation_room_id: str,
        room_id: str,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """Assign or reassign a physical room to a reservation room."""
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        target_room = None
        for r in reservation.rooms:
            if r.id == reservation_room_id:
                target_room = r
                break
        if not target_room:
            raise EntityNotFoundException("ReservationRoom", reservation_room_id)

        room = await db.get(Room, room_id)
        if not room or room.property_id != property_id:
            raise EntityNotFoundException("Room", room_id)

        # Check for active blocks on this room for the reservation stay dates
        block_res = await db.execute(
            select(RoomBlock).where(
                RoomBlock.room_id == room.id,
                RoomBlock.start_at < target_room.check_out_at,
                RoomBlock.end_at > target_room.check_in_at,
            )
        )
        active_blk = block_res.scalars().first()
        if active_blk:
            raise ValidationException(
                f"Room {room.room_number} is blocked ({active_blk.block_type}) from {active_blk.start_at.strftime('%Y-%m-%d')} to {active_blk.end_at.strftime('%Y-%m-%d')}: {active_blk.reason or 'Scheduled block'}."
            )

        old_room_id = target_room.room_id
        target_room.room_id = room.id

        # If reservation is already in-house (CHECKED_IN), update physical room occupancy
        if reservation.status == ReservationStatus.CHECKED_IN.value:
            if old_room_id:
                old_room = await db.get(Room, old_room_id)
                if old_room:
                    old_room.occupancy_status = OccupancyStatus.VACANT.value
                    old_room.housekeeping_status = HousekeepingStatus.DIRTY.value
            room.occupancy_status = OccupancyStatus.OCCUPIED.value

        property_obj = await db.get(Property, property_id)
        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="ROOM_ASSIGNMENT",
            old_values={"room_id": old_room_id},
            new_values={"room_id": room.id, "room_number": room.room_number},
        )
        db.add(audit_log)
        await db.commit()

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)

    async def cancel_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        reason: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Cancel reservation:
        1. Set status to CANCELLED and stamp cancelled_at / reason.
        2. Release inventory: decrement sold_rooms for remaining future nights.
        3. Log audit event.
        """
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        if reservation.status == ReservationStatus.CANCELLED.value:
            raise ValidationException("Reservation is already cancelled.")
        if reservation.status == ReservationStatus.CHECKED_OUT.value:
            raise ValidationException("Checked-out reservation cannot be cancelled.")

        property_obj = await db.get(Property, property_id)
        from app.services.inventory_service import inventory_service
        business_date = inventory_service.get_business_date(property_obj)

        reservation.status = ReservationStatus.CANCELLED.value
        reservation.cancelled_at = datetime.now(timezone.utc)
        reservation.cancellation_reason = reason

        room_releases: Dict[str, List[date]] = {}
        for r_room in reservation.rooms:
            r_room.status = ReservationStatus.CANCELLED.value
            start_d = r_room.check_in_at.date()
            end_d = r_room.check_out_at.date()
            num_nights = max(1, (end_d - start_d).days)
            stay_dates = [start_d + timedelta(days=i) for i in range(num_nights)]

            if r_room.room_type_id not in room_releases:
                room_releases[r_room.room_type_id] = []
            room_releases[r_room.room_type_id].extend(stay_dates)

        # Decrement sold_rooms for remaining future nights
        await inventory_service.release_inventory(
            db, property_id=property_id, room_releases=room_releases, from_date=business_date
        )

        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="CANCEL",
            old_values={"status": reservation.status},
            new_values={
                "status": ReservationStatus.CANCELLED.value,
                "cancellation_reason": reason,
                "cancelled_at": reservation.cancelled_at.isoformat(),
            },
        )
        db.add(audit_log)
        await db.commit()

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)

    async def no_show_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        reason: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Mark reservation as NO_SHOW:
        1. Set status to NO_SHOW.
        2. Decrement sold_rooms for remaining future nights.
        3. Log audit event.
        """
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CONFIRMED.value:
            raise ValidationException(f"Only CONFIRMED reservations can be marked NO_SHOW (current: {reservation.status}).")

        property_obj = await db.get(Property, property_id)
        from app.services.inventory_service import inventory_service
        business_date = inventory_service.get_business_date(property_obj)

        reservation.status = ReservationStatus.NO_SHOW.value

        room_releases: Dict[str, List[date]] = {}
        for r_room in reservation.rooms:
            r_room.status = ReservationStatus.NO_SHOW.value
            start_d = r_room.check_in_at.date()
            end_d = r_room.check_out_at.date()
            num_nights = max(1, (end_d - start_d).days)
            stay_dates = [start_d + timedelta(days=i) for i in range(num_nights)]

            if r_room.room_type_id not in room_releases:
                room_releases[r_room.room_type_id] = []
            room_releases[r_room.room_type_id].extend(stay_dates)

        # Decrement sold_rooms for remaining future nights
        await inventory_service.release_inventory(
            db, property_id=property_id, room_releases=room_releases, from_date=business_date
        )

        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="NO_SHOW",
            old_values={"status": ReservationStatus.CONFIRMED.value},
            new_values={"status": ReservationStatus.NO_SHOW.value, "reason": reason},
        )
        db.add(audit_log)
        await db.commit()

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)

    async def check_in_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        payload: Optional[ReservationCheckInRequest] = None,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Check-in reservation:
        1. Validate reservation status is CONFIRMED.
        2. Assign physical room if unassigned (via payload or auto-assign vacant clean room).
        3. Validate assigned room is not occupied and verify housekeeping status (or allow override).
        4. Update reservation & room statuses to CHECKED_IN, stamp actual_check_in_at.
        5. Update physical room occupancy to OCCUPIED.
        6. Log audit trail.
        """
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CONFIRMED.value:
            raise ValidationException(f"Only CONFIRMED reservations can be checked in (current: {reservation.status}).")

        now = datetime.now(timezone.utc)
        property_obj = await db.get(Property, property_id)
        from app.services.inventory_service import inventory_service
        business_date = inventory_service.get_business_date(property_obj)

        # 0. Business date vs check-in date verification
        for r_room in reservation.rooms:
            res_in_date = r_room.check_in_at.date()
            if res_in_date > business_date and (payload and not payload.allow_early_checkin):
                raise ValidationException(
                    f"Early arrival: reservation is scheduled for {res_in_date}, but hotel business date is {business_date}. "
                    "Please confirm early check-in to proceed."
                )

        # 1. Validate / Assign physical rooms
        for r_room in reservation.rooms:
            target_room_id = None
            if payload and payload.room_assignments and r_room.id in payload.room_assignments:
                target_room_id = payload.room_assignments[r_room.id]
            elif payload and payload.room_id and len(reservation.rooms) == 1:
                target_room_id = payload.room_id
            elif r_room.room_id:
                target_room_id = r_room.room_id

            if not target_room_id:
                # Attempt auto-assign a clean vacant room of the booked room type
                stmt_candidate = (
                    select(Room)
                    .where(
                        Room.property_id == property_id,
                        Room.room_type_id == r_room.room_type_id,
                        Room.occupancy_status == OccupancyStatus.VACANT.value,
                        Room.status == RoomStatus.AVAILABLE.value,
                    )
                    .order_by(
                        case(
                            (Room.housekeeping_status == HousekeepingStatus.INSPECTED.value, 1),
                            (Room.housekeeping_status == HousekeepingStatus.CLEAN.value, 2),
                            else_=3,
                        ),
                        Room.room_number.asc(),
                    )
                )
                res_candidate = await db.execute(stmt_candidate)
                candidate_room = res_candidate.scalars().first()
                if candidate_room:
                    target_room_id = candidate_room.id
                else:
                    # Check if property has any physical rooms configured for this room type
                    stmt_any = select(func.count(Room.id)).where(
                        Room.property_id == property_id,
                        Room.room_type_id == r_room.room_type_id,
                    )
                    total_type_rooms = (await db.execute(stmt_any)).scalar() or 0
                    if total_type_rooms > 0:
                        raise ValidationException(
                            "Cannot check in: all rooms of this type are currently occupied or unavailable. Please assign a room manually."
                        )

            if target_room_id:
                room_obj = await db.get(Room, target_room_id)
                if not room_obj or room_obj.property_id != property_id:
                    raise ValidationException(f"Invalid room '{target_room_id}' for property.")
                if room_obj.occupancy_status == OccupancyStatus.OCCUPIED.value and r_room.room_id != target_room_id:
                    raise ValidationException(f"Room {room_obj.room_number} is already occupied.")

                # Check for active blocks on this room
                block_res = await db.execute(
                    select(RoomBlock).where(
                        RoomBlock.room_id == target_room_id,
                        RoomBlock.start_at < r_room.check_out_at,
                        RoomBlock.end_at > r_room.check_in_at,
                    )
                )
                active_blk = block_res.scalars().first()
                if active_blk:
                    raise ValidationException(
                        f"Cannot check in: Room {room_obj.room_number} is blocked ({active_blk.block_type}) until {active_blk.end_at.strftime('%Y-%m-%d')}."
                    )

                # Housekeeping dirty override check
                if (
                    room_obj.housekeeping_status == HousekeepingStatus.DIRTY.value
                    and not (payload and payload.allow_dirty_override)
                ):
                    raise ValidationException(
                        f"Room {room_obj.room_number} is currently {room_obj.housekeeping_status}. Clean room required or enable override."
                    )

                r_room.room_id = target_room_id
                room_obj.occupancy_status = OccupancyStatus.OCCUPIED.value

        # 2. Update statuses & timestamps
        reservation.status = ReservationStatus.CHECKED_IN.value
        for r_room in reservation.rooms:
            r_room.status = ReservationStatus.CHECKED_IN.value
            r_room.actual_check_in_at = now
            if r_room.room_id:
                room_obj = await db.get(Room, r_room.room_id)
                if room_obj:
                    room_obj.occupancy_status = OccupancyStatus.OCCUPIED.value

        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="CHECK_IN",
            old_values={"status": ReservationStatus.CONFIRMED.value},
            new_values={
                "status": ReservationStatus.CHECKED_IN.value,
                "keycards_issued": payload.keycards_issued if payload else 1,
                "notes": payload.notes if payload else None,
            },
        )
        db.add(audit_log)
        await db.commit()

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)

    async def undo_check_in_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Undo Check-in:
        1. Validate reservation status is CHECKED_IN.
        2. Revert reservation status to CONFIRMED.
        3. Revert reservation_rooms status to CONFIRMED and clear actual_check_in_at.
        4. Revert physical room occupancy_status from OCCUPIED to VACANT.
        5. Log audit trail.
        """
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CHECKED_IN.value:
            raise ValidationException(f"Only CHECKED_IN reservations can have check-in undone (current: {reservation.status}).")

        property_obj = await db.get(Property, property_id)

        reservation.status = ReservationStatus.CONFIRMED.value
        for r_room in reservation.rooms:
            r_room.status = ReservationStatus.CONFIRMED.value
            r_room.actual_check_in_at = None
            if r_room.room_id:
                room_obj = await db.get(Room, r_room.room_id)
                if room_obj:
                    room_obj.occupancy_status = OccupancyStatus.VACANT.value

        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="UNDO_CHECK_IN",
            old_values={"status": ReservationStatus.CHECKED_IN.value},
            new_values={"status": ReservationStatus.CONFIRMED.value},
        )
        db.add(audit_log)
        await db.commit()

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)

    async def check_out_reservation(
        self,
        db: AsyncSession,
        property_id: str,
        reservation_id: str,
        payload: Optional[ReservationCheckOutRequest] = None,
        current_user_id: Optional[str] = None,
    ) -> ReservationResponse:
        """
        Check-out reservation:
        1. Validate reservation status is CHECKED_IN.
        2. Handle same-day checkout & room rate posting based on PropertySettings.same_day_checkout_rule.
        3. Handle settlement payment (if supplied) and verify folio balance.
        4. Release inventory for remaining future unstayed nights (early departure / same-day).
        5. Mark physical room VACANT & DIRTY (triggering housekeeping turnover).
        6. Close master Folio.
        7. Update reservation status to CHECKED_OUT and record AuditLog.
        """
        reservation = await crud_reservation.get_by_id(db, reservation_id=reservation_id, property_id=property_id)
        if not reservation:
            raise EntityNotFoundException("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CHECKED_IN.value:
            raise ValidationException(f"Only CHECKED_IN reservations can be checked out (current: {reservation.status}).")

        now = datetime.now(timezone.utc)
        property_obj = await db.get(Property, property_id)
        from app.services.inventory_service import inventory_service
        business_date = inventory_service.get_business_date(property_obj)

        stmt_settings = select(PropertySettings).where(PropertySettings.property_id == property_id)
        settings_res = await db.execute(stmt_settings)
        prop_settings = settings_res.scalar_one_or_none()

        # 1. Fetch Folio and check if stay charges / room rate need posting
        stmt_folio = select(Folio).where(Folio.reservation_id == reservation.id)
        res_folio = await db.execute(stmt_folio)
        folio = res_folio.scalar_one_or_none()

        if folio:
            stmt_txns = select(FolioTransaction).where(FolioTransaction.folio_id == folio.id)
            existing_txns = list((await db.execute(stmt_txns)).scalars().all())
            has_room_charge = any(t.transaction_type == FolioTransactionType.ROOM_CHARGE.value for t in existing_txns)

            # Same-day stay detection
            is_same_day = False
            for r_room in reservation.rooms:
                in_date = (r_room.actual_check_in_at.date() if r_room.actual_check_in_at else r_room.check_in_at.date())
                if in_date == now.date():
                    is_same_day = True
                    break

            charge_rule = (
                payload.same_day_charge_type
                if payload and payload.same_day_charge_type
                else (prop_settings.same_day_checkout_rule if (prop_settings and is_same_day) else "FULL_NIGHT")
            )

            # Find all unposted room rates across reservation rooms
            from app.services.folio_service import folio_service
            unposted_rates = [
                (r_room, rr)
                for r_room in reservation.rooms
                for rr in r_room.room_rates
                if rr.folio_transaction_id is None
            ]

            if unposted_rates:
                if charge_rule != "WAIVED":
                    discount_factor = Decimal("0.50") if charge_rule in ("DAY_USE", "PARTIAL") else Decimal("1.00")
                    for r_room, rr in unposted_rates:
                        await folio_service.post_room_rate_transaction(
                            db=db,
                            property_id=property_id,
                            folio_id=folio.id,
                            room_rate=rr,
                            reservation_room=r_room,
                            current_user_id=current_user_id,
                            discount_factor=discount_factor,
                        )
            elif not has_room_charge:
                # Fallback for reservations created without room_rate snapshots
                charge_amount = Decimal("0.00")
                total_stay = reservation.total_amount or Decimal("0.00")
                if charge_rule == "WAIVED":
                    charge_amount = Decimal("0.00")
                elif charge_rule in ("DAY_USE", "PARTIAL"):
                    charge_amount = (total_stay * Decimal("0.50")).quantize(Decimal("0.01"))
                else:  # FULL_NIGHT
                    charge_amount = total_stay

                if charge_amount > Decimal("0.00"):
                    room_charge_txn = FolioTransaction(
                        property_id=property_id,
                        folio_id=folio.id,
                        business_date=business_date,
                        entry_type=FolioEntryType.DEBIT.value,
                        transaction_type=FolioTransactionType.ROOM_CHARGE.value,
                        description=f"Stay room charge ({charge_rule})",
                        quantity=Decimal("1.00"),
                        unit_price=charge_amount,
                        amount=charge_amount,
                        tax_amount=Decimal("0.00"),
                        total_amount=charge_amount,
                        source=FolioTransactionSource.SYSTEM.value,
                        posted_by=current_user_id,
                        posted_at=now,
                    )
                    db.add(room_charge_txn)
                    await db.flush()

            # 2. Process Settlement Payment if provided
            if payload and payload.settlement_payment and payload.settlement_payment.amount > Decimal("0.00"):
                from app.services.payment_service import payment_service
                from app.schemas.payment import PaymentCreateInput

                p_in = PaymentCreateInput(
                    amount=payload.settlement_payment.amount,
                    payment_method=payload.settlement_payment.payment_method or "CASH",
                    payment_type="SETTLEMENT",
                    status="COMPLETED",
                    currency=reservation.currency,
                    gateway_reference=payload.settlement_payment.reference,
                    notes=payload.settlement_payment.notes,
                    reservation_id=reservation.id,
                )
                await payment_service.record_payment(
                    db,
                    property_id=property_id,
                    payload=p_in,
                    current_user_id=current_user_id,
                    reservation_id=reservation.id,
                )

            # 3. Calculate Folio Balance
            stmt_txns_after = select(FolioTransaction).where(FolioTransaction.folio_id == folio.id)
            updated_txns = list((await db.execute(stmt_txns_after)).scalars().all())
            debits = sum((t.total_amount for t in updated_txns if t.entry_type == FolioEntryType.DEBIT.value), Decimal("0.00"))
            credits = sum((t.total_amount for t in updated_txns if t.entry_type == FolioEntryType.CREDIT.value), Decimal("0.00"))
            if debits == Decimal("0.00") and reservation.total_amount:
                debits = reservation.total_amount
            balance_due = max(Decimal("0.00"), debits - credits)

            if balance_due > Decimal("0.00") and not (payload and payload.allow_unpaid_override):
                raise ValidationException(
                    f"Cannot complete check-out: outstanding balance of {reservation.currency} {balance_due:.2f} remains on folio. "
                    "Please settle payment or enable manager override."
                )

        # 4. Release inventory for remaining future unstayed nights (early departure / same-day)
        room_releases: Dict[str, List[date]] = {}
        for r_room in reservation.rooms:
            booked_end_d = r_room.check_out_at.date()
            from_release_date = max(business_date, now.date())
            stay_dates = []
            d = from_release_date
            while d < booked_end_d:
                stay_dates.append(d)
                d += timedelta(days=1)

            if stay_dates:
                if r_room.room_type_id not in room_releases:
                    room_releases[r_room.room_type_id] = []
                room_releases[r_room.room_type_id].extend(stay_dates)

        if room_releases:
            await inventory_service.release_inventory(
                db, property_id=property_id, room_releases=room_releases, from_date=business_date
            )

        # 5. Transition Physical Room & Reservation State
        for r_room in reservation.rooms:
            r_room.status = ReservationStatus.CHECKED_OUT.value
            r_room.actual_check_out_at = now
            if r_room.room_id:
                room_obj = await db.get(Room, r_room.room_id)
                if room_obj:
                    room_obj.occupancy_status = OccupancyStatus.VACANT.value
                    room_obj.housekeeping_status = HousekeepingStatus.DIRTY.value

        reservation.status = ReservationStatus.CHECKED_OUT.value
        if folio:
            folio.status = FolioStatus.CLOSED.value
            folio.closed_at = now

        # 6. Audit Trail
        audit_log = AuditLog(
            organization_id=property_obj.organization_id if property_obj else None,
            property_id=property_id,
            user_id=current_user_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="CHECK_OUT",
            old_values={"status": ReservationStatus.CHECKED_IN.value},
            new_values={
                "status": ReservationStatus.CHECKED_OUT.value,
                "override_reason": payload.override_reason if payload else None,
            },
        )
        db.add(audit_log)
        await db.commit()

        # 7. Optional Tax Invoice generation on checkout
        if payload and payload.generate_tax_invoice and folio:
            from app.schemas.invoice import InvoiceGenerateRequest
            from app.services.invoice_service import invoice_service
            from app.utils.enums import InvoiceType

            inv_payload = InvoiceGenerateRequest(
                folio_id=folio.id,
                invoice_type=InvoiceType.TAX_INVOICE.value,
                recipient_type=payload.recipient_type or "GUEST",
                company_id=payload.company_id or reservation.company_id,
            )
            try:
                await invoice_service.generate_invoice(
                    db,
                    property_id=property_id,
                    payload=inv_payload,
                    current_user_id=current_user_id,
                )
            except Exception:
                # Folio may have no billable debit charges or already invoiced
                pass

        return await self.get_reservation(db, property_id=property_id, reservation_id=reservation_id)


reservation_service = ReservationService()

