import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import case, func, or_, select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folio import (
    Folio,
    FolioTransaction,
    FolioTransactionTax,
    Payment,
)
from app.models.guest import Guest
from app.models.operation import AuditLog, NightAudit
from app.models.property import Property
from app.models.property_settings import PropertySettings
from app.models.rate_plan import RatePlan
from app.models.reservation import (
    Reservation,
    ReservationRoom,
    ReservationRoomRate,
)
from app.models.room import Room
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.models.tax import Tax, TaxGroup, TaxRate
from app.schemas.night_audit import (
    NightAuditResponse,
    NightAuditRunRequest,
    NightAuditStatusResponse,
    PreAuditArrivalItem,
    PreAuditCheckResponse,
    PreAuditDepartureItem,
    PreAuditRoomPostingItem,
)
from app.services.inventory_service import inventory_service
from app.services.folio_service import folio_service
from app.utils.enums import (
    EntityStatus,
    FolioEntryType,
    FolioStatus,
    FolioTransactionSource,
    FolioTransactionType,
    HousekeepingStatus,
    NightAuditStatus,
    OccupancyStatus,
    PaymentStatus,
    ReservationStatus,
    RoomStatus,
    TaxRateType,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException

logger = logging.getLogger("cloudkey.night_audit")


class NightAuditService:
    async def get_pre_audit_status(
        self, db: AsyncSession, property_id: str
    ) -> PreAuditCheckResponse:
        """
        Inspects the pre-flight conditions for the current business date:
        1. Pending arrivals (CONFIRMED reservations arriving on or before business date).
        2. Pending departures (CHECKED_IN reservations departing on or before business date).
        3. In-house rooms ready for nightly charge posting.
        """
        prop_query = await db.execute(
            select(Property)
            .options(selectinload(Property.settings))
            .where(Property.id == property_id)
        )
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        settings_obj = property_obj.settings
        business_date = inventory_service.get_business_date(property_obj)
        next_business_date = business_date + timedelta(days=1)
        scheduled_time = (
            settings_obj.night_audit_time.strftime("%H:%M:%S")
            if settings_obj and settings_obj.night_audit_time
            else "02:00:00"
        )
        audit_mode = settings_obj.night_audit_mode if settings_obj else "MANUAL"

        warnings: List[str] = []

        # 1. Pending Arrivals: CONFIRMED reservations with check_in_at date <= business_date
        stmt_arrivals = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
            )
            .where(
                Reservation.property_id == property_id,
                Reservation.status == ReservationStatus.CONFIRMED.value,
                func.date(Reservation.check_in_at) <= business_date,
            )
            .order_by(Reservation.check_in_at.asc())
        )
        res_arrivals = await db.execute(stmt_arrivals)
        arrival_rows = res_arrivals.scalars().all()

        pending_arrivals: List[PreAuditArrivalItem] = []
        for arr in arrival_rows:
            primary_room = arr.rooms[0] if arr.rooms else None
            guest_name = (
                f"{arr.guest.first_name} {arr.guest.last_name}".strip()
                if arr.guest
                else "Unknown Guest"
            )
            pending_arrivals.append(
                PreAuditArrivalItem(
                    reservation_id=arr.id,
                    booking_number=arr.booking_number,
                    guest_name=guest_name,
                    check_in_at=arr.check_in_at,
                    check_out_at=arr.check_out_at,
                    room_type_name=primary_room.room_type_name if primary_room else None,
                    room_number=primary_room.room_number if primary_room else None,
                )
            )

        if pending_arrivals:
            warnings.append(
                f"{len(pending_arrivals)} arrival(s) have not checked in yet. "
                "They will be marked as NO_SHOW if auto-no-show is enabled."
            )

        # 2. Pending Departures: CHECKED_IN reservations with check_out_at date <= business_date
        stmt_departures = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
            )
            .where(
                Reservation.property_id == property_id,
                Reservation.status == ReservationStatus.CHECKED_IN.value,
                func.date(Reservation.check_out_at) <= business_date,
            )
            .order_by(Reservation.check_out_at.asc())
        )
        res_departures = await db.execute(stmt_departures)
        departure_rows = res_departures.scalars().all()

        pending_departures: List[PreAuditDepartureItem] = []
        for dep in departure_rows:
            primary_room = dep.rooms[0] if dep.rooms else None
            guest_name = (
                f"{dep.guest.first_name} {dep.guest.last_name}".strip()
                if dep.guest
                else "Unknown Guest"
            )

            # Calculate open folio balance if master folio exists
            stmt_folio = select(Folio).where(Folio.reservation_id == dep.id)
            folio_obj = (await db.execute(stmt_folio)).scalars().first()
            balance_due = Decimal("0.00")
            if folio_obj:
                stmt_txns = select(FolioTransaction).where(FolioTransaction.folio_id == folio_obj.id)
                txns = (await db.execute(stmt_txns)).scalars().all()
                debits = sum(
                    (t.total_amount for t in txns if t.entry_type == FolioEntryType.DEBIT.value),
                    Decimal("0.00"),
                )
                credits = sum(
                    (t.total_amount for t in txns if t.entry_type == FolioEntryType.CREDIT.value),
                    Decimal("0.00"),
                )
                balance_due = max(Decimal("0.00"), debits - credits)

            pending_departures.append(
                PreAuditDepartureItem(
                    reservation_id=dep.id,
                    booking_number=dep.booking_number,
                    guest_name=guest_name,
                    check_in_at=dep.check_in_at,
                    check_out_at=dep.check_out_at,
                    room_number=primary_room.room_number if primary_room else None,
                    balance_due=balance_due,
                )
            )

        if pending_departures:
            warnings.append(
                f"{len(pending_departures)} guest(s) were scheduled to check out on or before today. "
                "Please check them out or extend their stay before running night audit."
            )

        # 3. Rooms to Post: Active CHECKED_IN reservation rooms with unposted room rates for business_date
        stmt_rooms_to_post = (
            select(ReservationRoomRate, ReservationRoom, Reservation, Guest)
            .join(ReservationRoom, ReservationRoomRate.reservation_room_id == ReservationRoom.id)
            .join(Reservation, ReservationRoom.reservation_id == Reservation.id)
            .join(Guest, Reservation.guest_id == Guest.id)
            .options(
                selectinload(ReservationRoom.room),
                selectinload(ReservationRoom.rate_plan),
            )
            .where(
                Reservation.property_id == property_id,
                ReservationRoom.status == ReservationStatus.CHECKED_IN.value,
                ReservationRoomRate.stay_date == business_date,
                ReservationRoomRate.folio_transaction_id.is_(None),
            )
        )
        res_postings = await db.execute(stmt_rooms_to_post)
        posting_rows = res_postings.all()

        rooms_to_post: List[PreAuditRoomPostingItem] = []
        total_projected_room_revenue = Decimal("0.00")
        total_projected_tax = Decimal("0.00")

        for r_rate, r_room, r_res, r_guest in posting_rows:
            net = r_rate.net_amount or Decimal("0.00")
            tax = r_rate.tax_amount or Decimal("0.00")
            tot = r_rate.total_amount or (net + tax)
            total_projected_room_revenue += net
            total_projected_tax += tax

            guest_name = f"{r_guest.first_name} {r_guest.last_name}".strip()
            rooms_to_post.append(
                PreAuditRoomPostingItem(
                    reservation_id=r_res.id,
                    reservation_room_id=r_room.id,
                    room_number=r_room.room_number,
                    guest_name=guest_name,
                    rate_plan_name=r_room.rate_plan_name,
                    net_amount=net,
                    tax_amount=tax,
                    total_amount=tot,
                )
            )

        # Check if audit already running or completed for today
        stmt_curr_audit = select(NightAudit).where(
            NightAudit.property_id == property_id,
            NightAudit.business_date == business_date,
        )
        curr_audit = (await db.execute(stmt_curr_audit)).scalar_one_or_none()
        can_run = True
        if curr_audit:
            if curr_audit.status == NightAuditStatus.COMPLETED.value:
                can_run = False
                warnings.append(
                    f"Night audit has already been completed for business date {business_date}."
                )
            elif curr_audit.status == NightAuditStatus.RUNNING.value:
                can_run = False
                warnings.append("Night audit is currently running.")

        return PreAuditCheckResponse(
            property_id=property_id,
            business_date=business_date,
            next_business_date=next_business_date,
            scheduled_time=scheduled_time,
            night_audit_mode=audit_mode,
            pending_arrivals=pending_arrivals,
            pending_departures=pending_departures,
            rooms_to_post=rooms_to_post,
            total_projected_room_revenue=total_projected_room_revenue,
            total_projected_tax=total_projected_tax,
            can_run=can_run,
            warnings=warnings,
        )

    async def get_audit_status(
        self, db: AsyncSession, property_id: str
    ) -> NightAuditStatusResponse:
        """Returns the high-level audit readiness status for the property."""
        prop_query = await db.execute(
            select(Property)
            .options(selectinload(Property.settings))
            .where(Property.id == property_id)
        )
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        settings_obj = property_obj.settings
        business_date = inventory_service.get_business_date(property_obj)
        audit_mode = settings_obj.night_audit_mode if settings_obj else "MANUAL"
        audit_time_str = (
            settings_obj.night_audit_time.strftime("%H:%M:%S")
            if settings_obj and settings_obj.night_audit_time
            else "02:00:00"
        )
        tz_name = property_obj.timezone or "Asia/Kolkata"

        # Check last audit
        stmt_last = (
            select(NightAudit)
            .where(NightAudit.property_id == property_id)
            .order_by(NightAudit.started_at.desc())
        )
        last_audit_obj = (await db.execute(stmt_last)).scalars().first()

        is_running = bool(
            last_audit_obj
            and last_audit_obj.business_date == business_date
            and last_audit_obj.status == NightAuditStatus.RUNNING.value
        )
        already_completed = bool(
            last_audit_obj
            and last_audit_obj.business_date == business_date
            and last_audit_obj.status == NightAuditStatus.COMPLETED.value
        )

        can_run = not is_running and not already_completed

        # Calculate next scheduled run string if AUTO
        next_scheduled = None
        if audit_mode == "AUTO" and settings_obj:
            try:
                tz = ZoneInfo(tz_name)
                now_local = datetime.now(tz)
                target_dt = datetime.combine(now_local.date(), settings_obj.night_audit_time, tzinfo=tz)
                if now_local >= target_dt:
                    target_dt += timedelta(days=1)
                next_scheduled = target_dt.isoformat()
            except Exception:
                next_scheduled = f"Daily at {audit_time_str}"

        last_audit_resp = (
            NightAuditResponse.model_validate(last_audit_obj) if last_audit_obj else None
        )

        return NightAuditStatusResponse(
            property_id=property_id,
            business_date=business_date,
            night_audit_mode=audit_mode,
            night_audit_time=audit_time_str,
            timezone=tz_name,
            is_audit_running=is_running,
            last_audit=last_audit_resp,
            can_run_audit=can_run,
            next_scheduled_run=next_scheduled,
        )

    async def execute_night_audit(
        self,
        db: AsyncSession,
        property_id: str,
        run_by: Optional[str] = None,
        trigger_type: str = "MANUAL",
        auto_no_show: Optional[bool] = None,
        allow_pending_departure_rollover: bool = False,
        notes: Optional[str] = None,
    ) -> NightAuditResponse:
        """
        Executes the transactional Night Audit procedure:
        1. Acquires row lock on Property to prevent race conditions.
        2. Validates idempotency (never double-runs on the same business date).
        3. Auto-processes No-Shows and releases future inventory.
        4. Posts room charges & taxes for in-house rooms to their respective master folios.
        5. Sets in-house room housekeeping status to DIRTY (morning turnover).
        6. Generates daily financial trial balance snapshot (JSON).
        7. Advances property.business_date by +1 day.
        8. Stamps NightAudit record as COMPLETED and records AuditLog.
        """
        # 1. Acquire pessimistic row-level lock on Property
        prop_query = await db.execute(
            select(Property)
            .options(selectinload(Property.settings))
            .where(Property.id == property_id)
            .with_for_update()
        )
        property_obj = prop_query.scalar_one_or_none()
        if not property_obj:
            raise EntityNotFoundException("Property", property_id)

        settings_obj = property_obj.settings
        business_date = inventory_service.get_business_date(property_obj)

        config = (settings_obj.night_audit_config or {}) if settings_obj else {}
        if auto_no_show is None:
            auto_no_show = config.get("auto_no_show", True)

        # 2. Check if already completed
        stmt_audit_check = select(NightAudit).where(
            NightAudit.property_id == property_id,
            NightAudit.business_date == business_date,
        )
        existing_audit = (await db.execute(stmt_audit_check)).scalar_one_or_none()
        if existing_audit and existing_audit.status == NightAuditStatus.COMPLETED.value:
            raise ValidationException(
                f"Night audit for business date {business_date} has already been completed."
            )

        # 3. Create or update running audit record
        if existing_audit:
            audit_record = existing_audit
            audit_record.status = NightAuditStatus.RUNNING.value
            audit_record.trigger_type = trigger_type
            audit_record.run_by = run_by
            audit_record.started_at = datetime.now(timezone.utc)
            audit_record.error_message = None
        else:
            audit_record = NightAudit(
                property_id=property_id,
                business_date=business_date,
                status=NightAuditStatus.RUNNING.value,
                trigger_type=trigger_type,
                run_by=run_by,
                started_at=datetime.now(timezone.utc),
            )
            db.add(audit_record)
        await db.flush()

        try:
            # 4. Process No-Shows
            no_shows_marked = 0
            if auto_no_show:
                no_shows_marked = await self._process_no_shows(
                    db, property_id, business_date, run_by
                )

            # 5. Post Room Charges & Taxes to Folios
            rooms_posted, total_room_rev, total_tax = await self._post_nightly_room_charges(
                db, property_id, property_obj, business_date, run_by
            )

            # 6. Housekeeping Turnover: Set in-house rooms to DIRTY
            await self._update_housekeeping_turnover(db, property_id)

            # 7. Generate Daily Financial Summary Snapshot
            summary_snapshot = await self._generate_daily_snapshot(
                db, property_id, property_obj, business_date, total_room_rev, total_tax, rooms_posted
            )
            if notes:
                summary_snapshot["audit_notes"] = notes

            # 8. Advance the Hotel Business Date
            next_business_date = business_date + timedelta(days=1)
            property_obj.business_date = next_business_date

            # 9. Mark Audit Record COMPLETED
            audit_record.status = NightAuditStatus.COMPLETED.value
            audit_record.completed_at = datetime.now(timezone.utc)
            audit_record.rooms_posted = rooms_posted
            audit_record.no_shows_marked = no_shows_marked
            audit_record.summary_data = summary_snapshot

            # 10. Audit Log
            audit_log = AuditLog(
                organization_id=property_obj.organization_id,
                property_id=property_id,
                user_id=run_by,
                entity_type="night_audits",
                entity_id=audit_record.id,
                action="NIGHT_AUDIT_COMPLETED",
                old_values={"business_date": str(business_date)},
                new_values={
                    "business_date": str(next_business_date),
                    "rooms_posted": rooms_posted,
                    "no_shows_marked": no_shows_marked,
                    "trigger_type": trigger_type,
                },
            )
            db.add(audit_log)
            await db.commit()

            logger.info(
                f"[NightAudit] Successfully completed audit for property {property_id} "
                f"({business_date} -> {next_business_date}). Rooms posted: {rooms_posted}, No-shows: {no_shows_marked}"
            )
            return NightAuditResponse.model_validate(audit_record)

        except Exception as exc:
            await db.rollback()
            logger.error(
                f"[NightAudit] Failed audit for property {property_id} on {business_date}: {exc}",
                exc_info=True,
            )
            # Record failure in separate transaction
            try:
                async with db.begin():
                    audit_fail = await db.get(NightAudit, audit_record.id)
                    if audit_fail:
                        audit_fail.status = NightAuditStatus.FAILED.value
                        audit_fail.error_message = str(exc)
                        audit_fail.completed_at = datetime.now(timezone.utc)
            except Exception as rec_err:
                logger.error(f"[NightAudit] Could not record failure state: {rec_err}")
            raise

    async def _process_no_shows(
        self,
        db: AsyncSession,
        property_id: str,
        business_date: date,
        current_user_id: Optional[str],
    ) -> int:
        """Finds CONFIRMED reservations due on or before business_date and marks NO_SHOW."""
        stmt = (
            select(Reservation)
            .options(selectinload(Reservation.rooms))
            .where(
                Reservation.property_id == property_id,
                Reservation.status == ReservationStatus.CONFIRMED.value,
                func.date(Reservation.check_in_at) <= business_date,
            )
        )
        res = await db.execute(stmt)
        no_shows = list(res.scalars().all())

        count = 0
        room_releases: Dict[str, List[date]] = {}

        for reservation in no_shows:
            reservation.status = ReservationStatus.NO_SHOW.value
            for r_room in reservation.rooms:
                r_room.status = ReservationStatus.NO_SHOW.value
                start_d = r_room.check_in_at.date()
                end_d = r_room.check_out_at.date()
                num_nights = max(1, (end_d - start_d).days)
                stay_dates = [start_d + timedelta(days=i) for i in range(num_nights)]

                if r_room.room_type_id not in room_releases:
                    room_releases[r_room.room_type_id] = []
                room_releases[r_room.room_type_id].extend(stay_dates)

            count += 1

        if room_releases:
            await inventory_service.release_inventory(
                db,
                property_id=property_id,
                room_releases=room_releases,
                from_date=business_date,
            )

        return count

    async def _post_nightly_room_charges(
        self,
        db: AsyncSession,
        property_id: str,
        property_obj: Property,
        business_date: date,
        current_user_id: Optional[str],
    ) -> tuple[int, Decimal, Decimal]:
        """
        Posts room charges and linked taxes to open guest folios for all in-house rooms.
        Returns: (rooms_posted_count, total_room_revenue, total_tax_collected)
        """
        stmt = (
            select(ReservationRoomRate, ReservationRoom, Reservation)
            .join(ReservationRoom, ReservationRoomRate.reservation_room_id == ReservationRoom.id)
            .join(Reservation, ReservationRoom.reservation_id == Reservation.id)
            .options(
                selectinload(ReservationRoom.room),
                selectinload(ReservationRoom.rate_plan).selectinload(RatePlan.tax_group).selectinload(TaxGroup.items),
            )
            .where(
                Reservation.property_id == property_id,
                ReservationRoom.status == ReservationStatus.CHECKED_IN.value,
                ReservationRoomRate.stay_date == business_date,
                ReservationRoomRate.folio_transaction_id.is_(None),
            )
        )
        res = await db.execute(stmt)
        rate_rows = res.all()

        rooms_posted = 0
        total_room_rev = Decimal("0.00")
        total_tax = Decimal("0.00")
        now_utc = datetime.now(timezone.utc)

        for room_rate, r_room, reservation in rate_rows:
            net_amt = room_rate.net_amount or Decimal("0.00")
            tax_amt = room_rate.tax_amount or Decimal("0.00")
            tot_amt = room_rate.total_amount or (net_amt + tax_amt)

            # 1. Resolve master folio
            folio = await folio_service.get_or_create_master_folio(
                db, property_id, reservation, property_obj.currency
            )

            # 2. Determine tax group if any
            tax_group_id = (
                r_room.rate_plan.tax_group_id if (r_room.rate_plan and r_room.rate_plan.tax_group_id) else None
            )

            # 3. Create FolioTransaction
            room_desc = (
                f"Nightly Room Charge - Room {r_room.room_number} ({business_date})"
                if r_room.room_number
                else f"Nightly Room Charge ({business_date})"
            )
            folio_txn = FolioTransaction(
                property_id=property_id,
                folio_id=folio.id,
                business_date=business_date,
                entry_type=FolioEntryType.DEBIT.value,
                transaction_type=FolioTransactionType.ROOM_CHARGE.value,
                description=room_desc,
                quantity=Decimal("1.00"),
                unit_price=net_amt,
                amount=net_amt,
                tax_amount=tax_amt,
                total_amount=tot_amt,
                tax_group_id=tax_group_id,
                is_tax_inclusive=False,
                source=FolioTransactionSource.NIGHT_AUDIT.value,
                posted_by=current_user_id,
                posted_at=now_utc,
            )
            db.add(folio_txn)
            await db.flush()

            # 4. Link FolioTransaction Taxes if rate plan has taxes
            if r_room.rate_plan and r_room.rate_plan.tax_group and r_room.rate_plan.tax_group.items:
                for item in r_room.rate_plan.tax_group.items:
                    rate_q = await db.execute(
                        select(TaxRate)
                        .where(
                            TaxRate.tax_id == item.tax_id,
                            TaxRate.valid_from <= business_date,
                            or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= business_date),
                        )
                        .order_by(TaxRate.created_at.desc())
                    )
                    tax_rate_obj = rate_q.scalars().first()
                    tax_q = await db.execute(select(Tax).where(Tax.id == item.tax_id))
                    tax_ent = tax_q.scalar_one_or_none()

                    if tax_rate_obj and tax_ent:
                        tax_line_amt = (
                            (net_amt * tax_rate_obj.rate / Decimal("100")).quantize(Decimal("0.01"))
                            if tax_rate_obj.rate_type == TaxRateType.PERCENTAGE.value
                            else tax_rate_obj.rate.quantize(Decimal("0.01"))
                        )
                        txn_tax = FolioTransactionTax(
                            folio_transaction_id=folio_txn.id,
                            tax_id=item.tax_id,
                            tax_rate_id=tax_rate_obj.id,
                            tax_name=tax_ent.name,
                            rate=tax_rate_obj.rate,
                            taxable_amount=net_amt,
                            tax_amount=tax_line_amt,
                        )
                        db.add(txn_tax)

            # 5. Link folio_transaction_id on reservation_room_rates
            room_rate.folio_transaction_id = folio_txn.id

            rooms_posted += 1
            total_room_rev += net_amt
            total_tax += tax_amt

        return rooms_posted, total_room_rev, total_tax

    async def _update_housekeeping_turnover(
        self, db: AsyncSession, property_id: str
    ) -> None:
        """Sets housekeeping_status of occupied physical rooms to DIRTY for morning service."""
        stmt = (
            select(Room)
            .where(
                Room.property_id == property_id,
                Room.occupancy_status == OccupancyStatus.OCCUPIED.value,
                Room.status == RoomStatus.AVAILABLE.value,
            )
        )
        res = await db.execute(stmt)
        rooms = list(res.scalars().all())
        for room in rooms:
            room.housekeeping_status = HousekeepingStatus.DIRTY.value

    async def _generate_daily_snapshot(
        self,
        db: AsyncSession,
        property_id: str,
        property_obj: Property,
        business_date: date,
        room_revenue: Decimal,
        tax_revenue: Decimal,
        rooms_sold: int,
    ) -> Dict[str, Any]:
        """Calculates comprehensive Daily Manager Trial Balance statistics."""
        # 1. Physical room counts
        total_rooms_q = await db.execute(
            select(func.count(Room.id)).where(
                Room.property_id == property_id,
                Room.status != RoomStatus.INACTIVE.value,
            )
        )
        total_rooms = total_rooms_q.scalar() or 0

        ooo_q = await db.execute(
            select(func.count(Room.id)).where(
                Room.property_id == property_id,
                Room.status.in_([RoomStatus.OUT_OF_SERVICE.value, RoomStatus.MAINTENANCE.value]),
            )
        )
        rooms_ooo = ooo_q.scalar() or 0

        available_rooms = max(0, total_rooms - rooms_ooo)
        occupancy_rate = (
            round((rooms_sold / available_rooms) * 100, 2)
            if available_rooms > 0
            else 0.0
        )
        adr = (
            round(float(room_revenue) / rooms_sold, 2)
            if rooms_sold > 0
            else 0.0
        )
        revpar = (
            round(float(room_revenue) / available_rooms, 2)
            if available_rooms > 0
            else 0.0
        )

        # 2. Service charges posted on this business date
        service_rev_q = await db.execute(
            select(func.coalesce(func.sum(FolioTransaction.amount), 0)).where(
                FolioTransaction.property_id == property_id,
                FolioTransaction.business_date == business_date,
                FolioTransaction.transaction_type == FolioTransactionType.SERVICE_CHARGE.value,
                FolioTransaction.entry_type == FolioEntryType.DEBIT.value,
            )
        )
        service_revenue = Decimal(str(service_rev_q.scalar() or "0.00"))

        # 3. Payments collected on this business date
        payments_stmt = (
            select(
                Payment.payment_type,
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .where(
                Payment.property_id == property_id,
                func.date(Payment.received_at) == business_date,
                Payment.status == PaymentStatus.CAPTURED.value,
            )
            .group_by(Payment.payment_type)
        )
        payments_res = await db.execute(payments_stmt)
        payments_by_type = {row[0]: float(row[1]) for row in payments_res.all()}
        total_payments = sum(payments_by_type.values())

        return {
            "business_date": str(business_date),
            "currency": property_obj.currency or "INR",
            "rooms": {
                "total_rooms": total_rooms,
                "rooms_available": available_rooms,
                "rooms_sold": rooms_sold,
                "rooms_ooo": rooms_ooo,
                "occupancy_rate_percent": occupancy_rate,
            },
            "financials": {
                "room_revenue": float(room_revenue),
                "service_revenue": float(service_revenue),
                "total_revenue": float(room_revenue + service_revenue),
                "total_tax": float(tax_revenue),
                "adr": adr,
                "revpar": revpar,
            },
            "settlements": {
                "total_payments_collected": total_payments,
                "by_type": payments_by_type,
            },
        }

    async def get_audit_history(
        self, db: AsyncSession, property_id: str, skip: int = 0, limit: int = 30
    ) -> List[NightAuditResponse]:
        """Returns paginated audit records for the property."""
        stmt = (
            select(NightAudit)
            .where(NightAudit.property_id == property_id)
            .order_by(NightAudit.business_date.desc(), NightAudit.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await db.execute(stmt)
        audits = res.scalars().all()
        return [NightAuditResponse.model_validate(a) for a in audits]

    async def get_audit_report(
        self, db: AsyncSession, property_id: str, audit_id: str
    ) -> Dict[str, Any]:
        """Returns the stored manager trial balance report for a specific audit."""
        stmt = select(NightAudit).where(
            NightAudit.id == audit_id,
            NightAudit.property_id == property_id,
        )
        res = await db.execute(stmt)
        audit_obj = res.scalar_one_or_none()
        if not audit_obj:
            raise EntityNotFoundException("NightAudit", audit_id)

        prop = await db.get(Property, property_id)

        return {
            "audit_id": audit_obj.id,
            "property_id": property_id,
            "property_name": prop.name if prop else "Hotel",
            "business_date": str(audit_obj.business_date),
            "status": audit_obj.status,
            "trigger_type": audit_obj.trigger_type,
            "rooms_posted": audit_obj.rooms_posted,
            "no_shows_marked": audit_obj.no_shows_marked,
            "started_at": audit_obj.started_at.isoformat() if audit_obj.started_at else None,
            "completed_at": audit_obj.completed_at.isoformat() if audit_obj.completed_at else None,
            "summary_data": audit_obj.summary_data or {},
        }


night_audit_service = NightAuditService()
