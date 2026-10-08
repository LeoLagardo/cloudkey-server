import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.folio import (
    Folio,
    FolioTransaction,
    FolioTransactionTax,
    Payment,
    PaymentMethod,
)
from app.models.guest import Guest
from app.models.operation import NightAudit, PropertyDailySummary
from app.models.property import Property
from app.models.rate_plan import RatePlan
from app.models.reservation import (
    Reservation,
    ReservationRoom,
)
from app.models.room import Room
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.models.user import User
from app.schemas.reports import (
    ADRRevPARDayItem,
    ADRRevPARReportResponse,
    ArrivalDepartureItem,
    ArrivalDepartureReportResponse,
    BookingListItem,
    BookingListReportResponse,
    CancellationItem,
    CancellationReportResponse,
    GuestHistoryItem,
    GuestHistoryReportResponse,
    InHouseGuestItem,
    InHouseReportResponse,
    NightAuditReportResponse,
    NightAuditSummaryItem,
    OccupancyDayItem,
    OccupancyReportResponse,
    OutstandingBalancesReportResponse,
    OutstandingFolioItem,
    PaymentCollectionItem,
    PaymentsReportResponse,
    RevenueDayItem,
    RevenueSummaryReportResponse,
    RoomAvailabilityReportResponse,
    RoomAvailabilityTypeDay,
    TaxBreakdownItem,
    TaxReportResponse,
)
from app.utils.enums import (
    FolioEntryType,
    FolioStatus,
    FolioTransactionType,
    OccupancyStatus,
    PaymentStatus,
    ReservationStatus,
    RoomStatus,
)
from app.utils.exceptions import EntityNotFoundException

logger = logging.getLogger("cloudkey.reports")


class ReportService:
    """
    Core reporting service executing analytical SQL queries over bookings,
    folios, transactions, taxes, and night audit daily snapshots.
    """

    async def _get_property_or_404(self, db: AsyncSession, property_id: str) -> Property:
        prop = await db.get(Property, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)
        return prop

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 1: OPERATIONAL REPORTS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_arrivals_departures(
        self,
        db: AsyncSession,
        property_id: str,
        target_date: Optional[date] = None,
        filter_type: str = "ALL",  # ALL, ARRIVALS, DEPARTURES
    ) -> ArrivalDepartureReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        t_date = target_date or prop.business_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        filter_type = filter_type.upper()
        if filter_type not in ("ALL", "ARRIVALS", "DEPARTURES"):
            filter_type = "ALL"

        conditions = [Reservation.property_id == property_id]

        if filter_type == "ARRIVALS":
            conditions.append(func.date(Reservation.check_in_at) == t_date)
            conditions.append(Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]))
        elif filter_type == "DEPARTURES":
            conditions.append(func.date(Reservation.check_out_at) == t_date)
            conditions.append(Reservation.status.in_([ReservationStatus.CHECKED_IN.value, ReservationStatus.CHECKED_OUT.value]))
        else:
            conditions.append(
                or_(
                    and_(
                        func.date(Reservation.check_in_at) == t_date,
                        Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
                    ),
                    and_(
                        func.date(Reservation.check_out_at) == t_date,
                        Reservation.status.in_([ReservationStatus.CHECKED_IN.value, ReservationStatus.CHECKED_OUT.value]),
                    ),
                )
            )

        stmt = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
            )
            .where(*conditions)
            .order_by(Reservation.check_in_at.asc())
        )
        res = await db.execute(stmt)
        reservations = list(res.scalars().all())

        # Fetch payments to compute balance due per reservation
        res_ids = [r.id for r in reservations]
        paid_map: Dict[str, Decimal] = {}
        if res_ids:
            p_stmt = (
                select(Payment.reservation_id, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
                .where(Payment.reservation_id.in_(res_ids), Payment.status == PaymentStatus.CAPTURED.value)
                .group_by(Payment.reservation_id)
            )
            p_res = await db.execute(p_stmt)
            for row in p_res.all():
                paid_map[row[0]] = Decimal(str(row[1]))

        items: List[ArrivalDepartureItem] = []
        total_arrivals = 0
        total_departures = 0
        total_balance = Decimal("0.00")

        for r in reservations:
            check_in_d = r.check_in_at.date()
            check_out_d = r.check_out_at.date()

            is_arr = (check_in_d == t_date)
            is_dep = (check_out_d == t_date)

            mov_type = "ARRIVAL" if is_arr else "DEPARTURE"
            if is_arr:
                total_arrivals += 1
            if is_dep:
                total_departures += 1

            nights = max(1, (check_out_d - check_in_d).days)
            primary_room = r.rooms[0] if r.rooms else None
            room_no = primary_room.room.room_number if primary_room and primary_room.room else "Unassigned"
            rt_name = primary_room.room_type.name if primary_room and primary_room.room_type else "Standard"

            tot_amt = r.total_amount or Decimal("0.00")
            tot_paid = paid_map.get(r.id, Decimal("0.00"))
            bal_due = max(Decimal("0.00"), tot_amt - tot_paid)
            total_balance += bal_due

            guest_name = f"{r.guest.first_name} {r.guest.last_name}".strip() if r.guest else "Unknown Guest"

            items.append(
                ArrivalDepartureItem(
                    reservation_id=r.id,
                    booking_number=r.booking_number,
                    movement_type=mov_type,
                    guest_name=guest_name,
                    guest_phone=r.guest.phone if r.guest else None,
                    guest_email=r.guest.email if r.guest else None,
                    room_number=room_no,
                    room_type_name=rt_name,
                    check_in_at=r.check_in_at,
                    check_out_at=r.check_out_at,
                    nights=nights,
                    adults=primary_room.adults if primary_room else 1,
                    children=primary_room.children if primary_room else 0,
                    status=r.status,
                    total_amount=tot_amt,
                    total_paid=tot_paid,
                    balance_due=bal_due,
                    special_requests=r.special_requests,
                )
            )

        return ArrivalDepartureReportResponse(
            property_id=property_id,
            property_name=prop.name,
            target_date=t_date,
            filter_type=filter_type,
            currency=currency,
            total_arrivals=total_arrivals,
            total_departures=total_departures,
            total_balance_due=total_balance,
            items=items,
        )

    async def get_in_house_guests(
        self,
        db: AsyncSession,
        property_id: str,
        as_of_date: Optional[date] = None,
    ) -> InHouseReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        target_d = as_of_date or prop.business_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        stmt = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
            )
            .where(
                Reservation.property_id == property_id,
                Reservation.status == ReservationStatus.CHECKED_IN.value,
                func.date(Reservation.check_in_at) <= target_d,
                func.date(Reservation.check_out_at) >= target_d,
            )
            .order_by(Reservation.check_in_at.asc())
        )
        res = await db.execute(stmt)
        reservations = list(res.scalars().all())

        # Load open folios for these reservations to calculate real-time ledger balance
        res_ids = [r.id for r in reservations]
        folio_balances: Dict[str, tuple[str, Decimal, Decimal, Decimal]] = {}
        if res_ids:
            f_stmt = (
                select(Folio)
                .options(selectinload(Folio.transactions), selectinload(Folio.payments))
                .where(Folio.reservation_id.in_(res_ids), Folio.property_id == property_id)
            )
            f_res = await db.execute(f_stmt)
            for f in f_res.scalars().all():
                debits = sum(
                    (t.total_amount for t in f.transactions if t.entry_type == FolioEntryType.DEBIT.value),
                    Decimal("0.00"),
                )
                credits = sum(
                    (t.total_amount for t in f.transactions if t.entry_type == FolioEntryType.CREDIT.value),
                    Decimal("0.00"),
                )
                payments = sum(
                    (p.amount for p in f.payments if p.status == PaymentStatus.CAPTURED.value),
                    Decimal("0.00"),
                )
                tot_credits = credits + payments
                bal = debits - tot_credits
                if f.reservation_id:
                    folio_balances[f.reservation_id] = (f.id, debits, tot_credits, bal)

        items: List[InHouseGuestItem] = []
        total_balance = Decimal("0.00")
        total_guests = 0

        for r in reservations:
            primary_room = r.rooms[0] if r.rooms else None
            room_no = primary_room.room.room_number if primary_room and primary_room.room else "Unassigned"
            floor_no = primary_room.room.floor if primary_room and primary_room.room else None
            rt_name = primary_room.room_type.name if primary_room and primary_room.room_type else "Standard"

            check_in_d = r.check_in_at.date()
            check_out_d = r.check_out_at.date()
            stay_nights = max(1, (check_out_d - check_in_d).days)
            nights_spent = max(0, (target_d - check_in_d).days)
            nights_rem = max(0, (check_out_d - target_d).days)

            adults = primary_room.adults if primary_room else 1
            children = primary_room.children if primary_room else 0
            total_guests += (adults + children)

            f_id, debits, credits, bal = folio_balances.get(
                r.id,
                (None, r.total_amount or Decimal("0.00"), Decimal("0.00"), r.total_amount or Decimal("0.00")),
            )
            total_balance += bal

            guest_name = f"{r.guest.first_name} {r.guest.last_name}".strip() if r.guest else "Unknown Guest"

            items.append(
                InHouseGuestItem(
                    reservation_id=r.id,
                    booking_number=r.booking_number,
                    room_number=room_no,
                    room_type_name=rt_name,
                    floor=floor_no,
                    guest_name=guest_name,
                    guest_phone=r.guest.phone if r.guest else None,
                    adults=adults,
                    children=children,
                    check_in_at=r.check_in_at,
                    check_out_at=r.check_out_at,
                    stay_nights=stay_nights,
                    nights_spent=nights_spent,
                    nights_remaining=nights_rem,
                    folio_id=f_id,
                    total_debits=debits,
                    total_credits=credits,
                    balance_due=bal,
                    status=r.status,
                )
            )

        return InHouseReportResponse(
            property_id=property_id,
            property_name=prop.name,
            as_of_date=target_d,
            currency=currency,
            total_in_house_rooms=len(items),
            total_guests=total_guests,
            total_outstanding_balance=total_balance,
            items=items,
        )

    async def get_room_availability(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> RoomAvailabilityReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or prop.business_date or datetime.now(timezone.utc).date()
        end_d = to_date or (start_d + timedelta(days=7))

        if end_d < start_d:
            end_d = start_d + timedelta(days=7)

        # Get total physical rooms count
        tot_phys_q = await db.execute(
            select(func.count(Room.id)).where(Room.property_id == property_id, Room.status != RoomStatus.INACTIVE.value)
        )
        total_phys_rooms = tot_phys_q.scalar() or 0

        # Fetch room types
        rt_stmt = select(RoomType).where(RoomType.property_id == property_id).order_by(RoomType.name)
        rt_res = await db.execute(rt_stmt)
        room_types = list(rt_res.scalars().all())

        # Fetch physical rooms count per room type
        phys_by_type_q = await db.execute(
            select(Room.room_type_id, func.count(Room.id))
            .where(Room.property_id == property_id, Room.status != RoomStatus.INACTIVE.value)
            .group_by(Room.room_type_id)
        )
        phys_by_type = {row[0]: row[1] for row in phys_by_type_q.all()}

        # Fetch inventory rows in date range
        inv_stmt = (
            select(RoomTypeInventory)
            .where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.stay_date >= start_d,
                RoomTypeInventory.stay_date <= end_d,
            )
        )
        inv_res = await db.execute(inv_stmt)
        inv_map: Dict[tuple[str, date], RoomTypeInventory] = {
            (inv.room_type_id, inv.stay_date): inv for inv in inv_res.scalars().all()
        }

        # Fetch maintenance / OOO rooms
        ooo_q = await db.execute(
            select(Room.room_type_id, func.count(Room.id))
            .where(
                Room.property_id == property_id,
                Room.status.in_([RoomStatus.OUT_OF_SERVICE.value, RoomStatus.MAINTENANCE.value]),
            )
            .group_by(Room.room_type_id)
        )
        ooo_by_type = {row[0]: row[1] for row in ooo_q.all()}

        items: List[RoomAvailabilityTypeDay] = []
        cur_d = start_d
        while cur_d <= end_d:
            for rt in room_types:
                inv_obj = inv_map.get((rt.id, cur_d))
                total_r = inv_obj.total_rooms if inv_obj else phys_by_type.get(rt.id, 0)
                sold_r = inv_obj.sold_rooms if inv_obj else 0
                blocked_r = inv_obj.blocked_rooms if inv_obj else 0
                maint_r = ooo_by_type.get(rt.id, 0)

                avail_r = max(0, total_r - sold_r - blocked_r - maint_r)
                occ_pct = round((sold_r / total_r * 100), 1) if total_r > 0 else 0.0

                items.append(
                    RoomAvailabilityTypeDay(
                        stay_date=cur_d,
                        room_type_id=rt.id,
                        room_type_name=rt.name,
                        total_rooms=total_r,
                        sold_rooms=sold_r,
                        blocked_rooms=blocked_r,
                        maintenance_rooms=maint_r,
                        available_rooms=avail_r,
                        occupancy_percent=occ_pct,
                    )
                )
            cur_d += timedelta(days=1)

        return RoomAvailabilityReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            total_physical_rooms=total_phys_rooms,
            items=items,
        )

    async def get_booking_list(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> BookingListReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        currency = prop.currency or "INR"

        conditions = [Reservation.property_id == property_id]

        if from_date:
            conditions.append(func.date(Reservation.check_in_at) >= from_date)
        if to_date:
            conditions.append(func.date(Reservation.check_in_at) <= to_date)
        if status:
            conditions.append(Reservation.status == status.upper())
        if source:
            conditions.append(Reservation.source == source.upper())

        stmt = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.rate_plan),
            )
            .where(*conditions)
            .order_by(Reservation.created_at.desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        reservations = list(res.scalars().all())

        # If text search is specified, filter in memory or by search term
        if search:
            s = search.lower().strip()
            filtered = []
            for r in reservations:
                g_name = f"{r.guest.first_name} {r.guest.last_name}".lower() if r.guest else ""
                b_no = r.booking_number.lower()
                phone = (r.guest.phone or "").lower() if r.guest else ""
                if s in g_name or s in b_no or s in phone:
                    filtered.append(r)
            reservations = filtered

        # Fetch payments to compute balances
        res_ids = [r.id for r in reservations]
        paid_map: Dict[str, Decimal] = {}
        if res_ids:
            p_stmt = (
                select(Payment.reservation_id, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
                .where(Payment.reservation_id.in_(res_ids), Payment.status == PaymentStatus.CAPTURED.value)
                .group_by(Payment.reservation_id)
            )
            p_res = await db.execute(p_stmt)
            for row in p_res.all():
                paid_map[row[0]] = Decimal(str(row[1]))

        items: List[BookingListItem] = []
        tot_gross = Decimal("0.00")
        tot_bal = Decimal("0.00")

        for r in reservations:
            p_room = r.rooms[0] if r.rooms else None
            rt_name = p_room.room_type.name if p_room and p_room.room_type else "Standard"
            rm_no = p_room.room.room_number if p_room and p_room.room else None
            rp_name = p_room.rate_plan.name if p_room and p_room.rate_plan else None

            nights = max(1, (r.check_out_at.date() - r.check_in_at.date()).days)
            gross = r.total_amount or Decimal("0.00")
            tax = r.total_tax_amount or Decimal("0.00")
            paid = paid_map.get(r.id, Decimal("0.00"))
            bal = max(Decimal("0.00"), gross - paid)

            tot_gross += gross
            tot_bal += bal

            g_name = f"{r.guest.first_name} {r.guest.last_name}".strip() if r.guest else "Unknown"

            items.append(
                BookingListItem(
                    reservation_id=r.id,
                    booking_number=r.booking_number,
                    booked_at=r.created_at,
                    guest_name=g_name,
                    guest_phone=r.guest.phone if r.guest else None,
                    source=r.source,
                    channel_name=r.channel_name,
                    room_type_name=rt_name,
                    room_number=rm_no,
                    rate_plan_name=rp_name,
                    check_in_at=r.check_in_at,
                    check_out_at=r.check_out_at,
                    nights=nights,
                    status=r.status,
                    total_amount=gross,
                    total_tax_amount=tax,
                    total_paid=paid,
                    balance_due=bal,
                )
            )

        return BookingListReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=from_date,
            to_date=to_date,
            currency=currency,
            total_bookings=len(items),
            total_gross_value=tot_gross,
            total_balance_outstanding=tot_bal,
            items=items,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 2: FINANCIAL REPORTS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_occupancy_report(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> OccupancyReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or (datetime.now(timezone.utc).date() - timedelta(days=6))
        end_d = to_date or datetime.now(timezone.utc).date()

        # Total rooms count
        tot_rooms_q = await db.execute(
            select(func.count(Room.id)).where(Room.property_id == property_id, Room.status != RoomStatus.INACTIVE.value)
        )
        total_rooms = tot_rooms_q.scalar() or 0

        # Out-of-order count
        ooo_rooms_q = await db.execute(
            select(func.count(Room.id)).where(
                Room.property_id == property_id,
                Room.status.in_([RoomStatus.OUT_OF_SERVICE.value, RoomStatus.MAINTENANCE.value]),
            )
        )
        ooo_rooms = ooo_rooms_q.scalar() or 0
        sellable = max(0, total_rooms - ooo_rooms)

        # 1. Check dedicated property daily summary table for locked historical dates
        pds_stmt = (
            select(PropertyDailySummary)
            .where(
                PropertyDailySummary.property_id == property_id,
                PropertyDailySummary.business_date >= start_d,
                PropertyDailySummary.business_date <= end_d,
            )
        )
        pds_res = await db.execute(pds_stmt)
        daily_summaries = {s.business_date: s for s in pds_res.scalars().all()}

        # 2. Check completed night audits for fallback history
        audit_stmt = (
            select(NightAudit)
            .where(
                NightAudit.property_id == property_id,
                NightAudit.business_date >= start_d,
                NightAudit.business_date <= end_d,
                NightAudit.status == "COMPLETED",
            )
        )
        audit_res = await db.execute(audit_stmt)
        audits = {a.business_date: a for a in audit_res.scalars().all()}

        # For remaining dates, compute sold rooms from inventory / reservations
        inv_stmt = (
            select(RoomTypeInventory.stay_date, func.sum(RoomTypeInventory.sold_rooms))
            .where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.stay_date >= start_d,
                RoomTypeInventory.stay_date <= end_d,
            )
            .group_by(RoomTypeInventory.stay_date)
        )
        inv_res = await db.execute(inv_stmt)
        inv_sold_map = {row[0]: int(row[1]) for row in inv_res.all()}

        items: List[OccupancyDayItem] = []
        tot_avail = 0
        tot_sold = 0

        cur_d = start_d
        while cur_d <= end_d:
            if cur_d in daily_summaries:
                s = daily_summaries[cur_d]
                d_tot = s.total_rooms
                d_ooo = s.rooms_ooo
                d_sellable = s.rooms_available
                d_sold = s.rooms_sold
                occ_pct = float(s.occupancy_rate_percent)
            elif cur_d in audits and audits[cur_d].summary_data:
                s_data = audits[cur_d].summary_data.get("rooms", {})
                d_tot = s_data.get("total_rooms", total_rooms)
                d_ooo = s_data.get("rooms_ooo", ooo_rooms)
                d_sellable = s_data.get("rooms_available", sellable)
                d_sold = s_data.get("rooms_sold", 0)
                occ_pct = s_data.get("occupancy_rate_percent", 0.0)
            else:
                d_tot = total_rooms
                d_ooo = ooo_rooms
                d_sellable = sellable
                d_sold = inv_sold_map.get(cur_d, 0)
                occ_pct = round((d_sold / d_sellable * 100), 2) if d_sellable > 0 else 0.0

            avail = max(0, d_sellable - d_sold)
            tot_avail += d_sellable
            tot_sold += d_sold

            items.append(
                OccupancyDayItem(
                    stay_date=cur_d,
                    total_rooms=d_tot,
                    out_of_order_rooms=d_ooo,
                    sellable_rooms=d_sellable,
                    rooms_sold=d_sold,
                    rooms_available=avail,
                    occupancy_rate_percent=float(occ_pct),
                )
            )
            cur_d += timedelta(days=1)

        avg_occ = round((tot_sold / tot_avail * 100), 2) if tot_avail > 0 else 0.0

        return OccupancyReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            average_occupancy_percent=avg_occ,
            total_room_nights_available=tot_avail,
            total_room_nights_sold=tot_sold,
            items=items,
        )

    async def get_revenue_summary(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> RevenueSummaryReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or (datetime.now(timezone.utc).date() - timedelta(days=6))
        end_d = to_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        # 1. Check dedicated property daily summary table for locked historical dates
        pds_stmt = (
            select(PropertyDailySummary)
            .where(
                PropertyDailySummary.property_id == property_id,
                PropertyDailySummary.business_date >= start_d,
                PropertyDailySummary.business_date <= end_d,
            )
        )
        pds_res = await db.execute(pds_stmt)
        daily_summaries = {s.business_date: s for s in pds_res.scalars().all()}

        # 2. Check Night Audit summary for fallback historical dates
        audit_stmt = (
            select(NightAudit)
            .where(
                NightAudit.property_id == property_id,
                NightAudit.business_date >= start_d,
                NightAudit.business_date <= end_d,
                NightAudit.status == "COMPLETED",
            )
        )
        audit_res = await db.execute(audit_stmt)
        audits = {a.business_date: a for a in audit_res.scalars().all()}

        # Aggregate live transactions per business date
        txn_stmt = (
            select(
                FolioTransaction.business_date,
                FolioTransaction.transaction_type,
                func.coalesce(func.sum(FolioTransaction.amount), Decimal("0.00")),
                func.coalesce(func.sum(FolioTransaction.tax_amount), Decimal("0.00")),
                func.count(distinct(FolioTransaction.folio_id)),
            )
            .where(
                FolioTransaction.property_id == property_id,
                FolioTransaction.business_date >= start_d,
                FolioTransaction.business_date <= end_d,
                FolioTransaction.entry_type == FolioEntryType.DEBIT.value,
            )
            .group_by(FolioTransaction.business_date, FolioTransaction.transaction_type)
        )
        txn_res = await db.execute(txn_stmt)

        daily_data: Dict[date, Dict[str, Any]] = {}
        for row in txn_res.all():
            b_date, t_type, amt, tax_amt, cnt = row[0], row[1], Decimal(str(row[2])), Decimal(str(row[3])), int(row[4])
            if b_date not in daily_data:
                daily_data[b_date] = {
                    "room_rev": Decimal("0.00"),
                    "service_rev": Decimal("0.00"),
                    "tax_amt": Decimal("0.00"),
                    "rooms_sold": 0,
                }
            if t_type == FolioTransactionType.ROOM_CHARGE.value:
                daily_data[b_date]["room_rev"] += amt
                daily_data[b_date]["rooms_sold"] += cnt
            elif t_type == FolioTransactionType.SERVICE_CHARGE.value:
                daily_data[b_date]["service_rev"] += amt
            daily_data[b_date]["tax_amt"] += tax_amt

        items: List[RevenueDayItem] = []
        tot_room = Decimal("0.00")
        tot_srv = Decimal("0.00")
        tot_tax = Decimal("0.00")
        tot_gross = Decimal("0.00")

        cur_d = start_d
        while cur_d <= end_d:
            if cur_d in daily_summaries:
                s = daily_summaries[cur_d]
                r_rev = s.room_revenue
                s_rev = s.service_revenue
                t_amt = s.tax_revenue
                sold = s.rooms_sold
            elif cur_d in audits and audits[cur_d].summary_data:
                f_data = audits[cur_d].summary_data.get("financials", {})
                r_data = audits[cur_d].summary_data.get("rooms", {})
                r_rev = Decimal(str(f_data.get("room_revenue", 0)))
                s_rev = Decimal(str(f_data.get("service_revenue", 0)))
                t_amt = Decimal(str(f_data.get("total_tax", 0)))
                sold = int(r_data.get("rooms_sold", 0))
            else:
                live = daily_data.get(
                    cur_d,
                    {"room_rev": Decimal("0.00"), "service_rev": Decimal("0.00"), "tax_amt": Decimal("0.00"), "rooms_sold": 0},
                )
                r_rev = live["room_rev"]
                s_rev = live["service_rev"]
                t_amt = live["tax_amt"]
                sold = live["rooms_sold"]

            gross = r_rev + s_rev + t_amt
            tot_room += r_rev
            tot_srv += s_rev
            tot_tax += t_amt
            tot_gross += gross

            items.append(
                RevenueDayItem(
                    business_date=cur_d,
                    room_revenue=r_rev,
                    service_revenue=s_rev,
                    tax_amount=t_amt,
                    gross_revenue=gross,
                    rooms_sold=sold,
                )
            )
            cur_d += timedelta(days=1)

        return RevenueSummaryReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            currency=currency,
            total_room_revenue=tot_room,
            total_service_revenue=tot_srv,
            total_tax_amount=tot_tax,
            total_gross_revenue=tot_gross,
            items=items,
        )

    async def get_adr_revpar(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> ADRRevPARReportResponse:
        occ_rep = await self.get_occupancy_report(db, property_id, from_date, to_date)
        rev_rep = await self.get_revenue_summary(db, property_id, from_date, to_date)

        rev_map = {item.business_date: item for item in rev_rep.items}

        items: List[ADRRevPARDayItem] = []
        tot_rooms_sold = 0
        tot_room_rev = Decimal("0.00")
        tot_sellable = 0

        for occ in occ_rep.items:
            rev_item = rev_map.get(occ.stay_date)
            r_rev = rev_item.room_revenue if rev_item else Decimal("0.00")
            sold = occ.rooms_sold
            sellable = occ.sellable_rooms

            adr = round(float(r_rev) / sold, 2) if sold > 0 else 0.0
            revpar = round(float(r_rev) / sellable, 2) if sellable > 0 else 0.0

            tot_rooms_sold += sold
            tot_room_rev += r_rev
            tot_sellable += sellable

            items.append(
                ADRRevPARDayItem(
                    business_date=occ.stay_date,
                    sellable_rooms=sellable,
                    rooms_sold=sold,
                    room_revenue=r_rev,
                    adr=adr,
                    revpar=revpar,
                    occupancy_percent=occ.occupancy_rate_percent,
                )
            )

        overall_adr = round(float(tot_room_rev) / tot_rooms_sold, 2) if tot_rooms_sold > 0 else 0.0
        overall_revpar = round(float(tot_room_rev) / tot_sellable, 2) if tot_sellable > 0 else 0.0
        avg_occ = round((tot_rooms_sold / tot_sellable * 100), 2) if tot_sellable > 0 else 0.0

        return ADRRevPARReportResponse(
            property_id=property_id,
            property_name=occ_rep.property_name,
            from_date=occ_rep.from_date,
            to_date=occ_rep.to_date,
            currency=rev_rep.currency,
            overall_adr=overall_adr,
            overall_revpar=overall_revpar,
            average_occupancy_percent=avg_occ,
            items=items,
        )

    async def get_outstanding_balances(
        self,
        db: AsyncSession,
        property_id: str,
    ) -> OutstandingBalancesReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        currency = prop.currency or "INR"
        today = prop.business_date or datetime.now(timezone.utc).date()

        stmt = (
            select(Folio)
            .options(
                selectinload(Folio.transactions),
                selectinload(Folio.payments),
                selectinload(Folio.guest),
                selectinload(Folio.reservation).selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
            )
            .where(
                Folio.property_id == property_id,
                Folio.status.in_([FolioStatus.OPEN.value, FolioStatus.CLOSED.value]),
            )
            .order_by(Folio.opened_at.desc())
        )
        res = await db.execute(stmt)
        folios = list(res.scalars().all())

        items: List[OutstandingFolioItem] = []
        tot_balance = Decimal("0.00")

        for f in folios:
            debits = sum(
                (t.total_amount for t in f.transactions if t.entry_type == FolioEntryType.DEBIT.value),
                Decimal("0.00"),
            )
            credits = sum(
                (t.total_amount for t in f.transactions if t.entry_type == FolioEntryType.CREDIT.value),
                Decimal("0.00"),
            )
            payments = sum(
                (p.amount for p in f.payments if p.status == PaymentStatus.CAPTURED.value),
                Decimal("0.00"),
            )
            tot_paid = credits + payments
            balance = debits - tot_paid

            # Only include folios with positive outstanding balance
            if balance <= Decimal("0.01"):
                continue

            tot_balance += balance

            g_name = (
                f"{f.guest.first_name} {f.guest.last_name}".strip()
                if f.guest
                else (
                    f"{f.reservation.guest.first_name} {f.reservation.guest.last_name}".strip()
                    if f.reservation and f.reservation.guest
                    else "Non-Guest Folio"
                )
            )

            p_room = f.reservation.rooms[0] if f.reservation and f.reservation.rooms else None
            room_no = p_room.room.room_number if p_room and p_room.room else None
            co_date = f.reservation.check_out_at.date() if f.reservation else None

            # Aging computation
            ref_date = co_date or f.opened_at.date()
            days_old = max(0, (today - ref_date).days)
            if days_old <= 30:
                aging = "0-30 days"
            elif days_old <= 60:
                aging = "31-60 days"
            else:
                aging = "60+ days"

            items.append(
                OutstandingFolioItem(
                    folio_id=f.id,
                    folio_number=f.folio_number,
                    folio_type=f.folio_type,
                    status=f.status,
                    reservation_id=f.reservation_id,
                    booking_number=f.reservation.booking_number if f.reservation else None,
                    guest_name=g_name,
                    room_number=room_no,
                    check_out_date=co_date,
                    opened_at=f.opened_at,
                    total_charges=debits,
                    total_payments=tot_paid,
                    balance_due=balance,
                    aging_bucket=aging,
                )
            )

        return OutstandingBalancesReportResponse(
            property_id=property_id,
            property_name=prop.name,
            currency=currency,
            total_open_folios=len(items),
            total_balance_due=tot_balance,
            items=items,
        )

    async def get_payments_cash_collection(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        payment_method_id: Optional[str] = None,
        received_by: Optional[str] = None,
    ) -> PaymentsReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or prop.business_date or datetime.now(timezone.utc).date()
        end_d = to_date or start_d
        currency = prop.currency or "INR"

        conditions = [
            Payment.property_id == property_id,
            Payment.status == PaymentStatus.CAPTURED.value,
            func.date(Payment.received_at) >= start_d,
            func.date(Payment.received_at) <= end_d,
        ]

        if payment_method_id:
            conditions.append(Payment.payment_method_id == payment_method_id)
        if received_by:
            conditions.append(Payment.received_by == received_by)

        stmt = (
            select(Payment)
            .options(
                selectinload(Payment.payment_method),
                selectinload(Payment.receiver),
                selectinload(Payment.reservation).selectinload(Reservation.guest),
            )
            .where(*conditions)
            .order_by(Payment.received_at.desc())
        )
        res = await db.execute(stmt)
        payments = list(res.scalars().all())

        items: List[PaymentCollectionItem] = []
        tot_amount = Decimal("0.00")
        method_map: Dict[str, Decimal] = {}

        for p in payments:
            amt = p.amount
            tot_amount += amt

            m_name = p.payment_method.name if p.payment_method else "Other"
            method_map[m_name] = method_map.get(m_name, Decimal("0.00")) + amt

            g_name = (
                f"{p.reservation.guest.first_name} {p.reservation.guest.last_name}".strip()
                if p.reservation and p.reservation.guest
                else "Direct Folio"
            )

            r_name = (
                f"{p.receiver.first_name} {p.receiver.last_name}".strip()
                if p.receiver and (p.receiver.first_name or p.receiver.last_name)
                else (p.receiver.email if p.receiver else "System")
            )

            items.append(
                PaymentCollectionItem(
                    payment_id=p.id,
                    received_at=p.received_at,
                    booking_number=p.reservation.booking_number if p.reservation else None,
                    guest_name=g_name,
                    payment_method_name=m_name,
                    payment_method_type=p.payment_method.method_type if p.payment_method else "CASH",
                    payment_type=p.payment_type,
                    amount=amt,
                    received_by_name=r_name,
                    notes=p.notes,
                )
            )

        return PaymentsReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            currency=currency,
            total_amount_collected=tot_amount,
            by_payment_method=method_map,
            items=items,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TIER 3: COMPLIANCE & CONTROL REPORTS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_tax_report(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> TaxReportResponse:
        """
        Reads directly from FolioTransactionTax immutable historical snapshots.
        """
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or (datetime.now(timezone.utc).date().replace(day=1))
        end_d = to_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        stmt = (
            select(
                FolioTransactionTax.tax_name,
                FolioTransactionTax.rate,
                func.coalesce(func.sum(FolioTransactionTax.taxable_amount), Decimal("0.00")),
                func.coalesce(func.sum(FolioTransactionTax.tax_amount), Decimal("0.00")),
                func.count(FolioTransactionTax.id),
            )
            .join(FolioTransaction, FolioTransaction.id == FolioTransactionTax.folio_transaction_id)
            .where(
                FolioTransaction.property_id == property_id,
                FolioTransaction.business_date >= start_d,
                FolioTransaction.business_date <= end_d,
                FolioTransaction.entry_type == FolioEntryType.DEBIT.value,
            )
            .group_by(FolioTransactionTax.tax_name, FolioTransactionTax.rate)
            .order_by(FolioTransactionTax.tax_name)
        )
        res = await db.execute(stmt)

        items: List[TaxBreakdownItem] = []
        tot_taxable = Decimal("0.00")
        tot_tax = Decimal("0.00")

        for row in res.all():
            t_name, rate, taxable, tax_amt, cnt = row[0], row[1], Decimal(str(row[2])), Decimal(str(row[3])), int(row[4])
            tot_taxable += taxable
            tot_tax += tax_amt

            items.append(
                TaxBreakdownItem(
                    tax_name=t_name,
                    rate=rate,
                    taxable_amount=taxable,
                    tax_amount=tax_amt,
                    transaction_count=cnt,
                )
            )

        return TaxReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            currency=currency,
            total_taxable_amount=tot_taxable,
            total_tax_amount=tot_tax,
            items=items,
        )

    async def get_cancellations_noshows(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> CancellationReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or (datetime.now(timezone.utc).date() - timedelta(days=30))
        end_d = to_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        stmt = (
            select(Reservation)
            .options(selectinload(Reservation.guest))
            .where(
                Reservation.property_id == property_id,
                Reservation.status.in_([ReservationStatus.CANCELLED.value, ReservationStatus.NO_SHOW.value]),
                func.date(func.coalesce(Reservation.cancelled_at, Reservation.check_in_at)) >= start_d,
                func.date(func.coalesce(Reservation.cancelled_at, Reservation.check_in_at)) <= end_d,
            )
            .order_by(Reservation.cancelled_at.desc().nullslast())
        )
        res = await db.execute(stmt)
        reservations = list(res.scalars().all())

        # Check for cancellation charges posted on their folios
        res_ids = [r.id for r in reservations]
        fee_map: Dict[str, Decimal] = {}
        if res_ids:
            fee_stmt = (
                select(Folio.reservation_id, func.coalesce(func.sum(FolioTransaction.total_amount), Decimal("0.00")))
                .join(FolioTransaction, FolioTransaction.folio_id == Folio.id)
                .where(
                    Folio.reservation_id.in_(res_ids),
                    FolioTransaction.transaction_type == FolioTransactionType.CANCELLATION_FEE.value,
                )
                .group_by(Folio.reservation_id)
            )
            fee_res = await db.execute(fee_stmt)
            for row in fee_res.all():
                fee_map[row[0]] = Decimal(str(row[1]))

        items: List[CancellationItem] = []
        tot_canc = 0
        tot_noshow = 0
        tot_lost = Decimal("0.00")
        tot_fees = Decimal("0.00")

        for r in reservations:
            is_canc = (r.status == ReservationStatus.CANCELLED.value)
            if is_canc:
                tot_canc += 1
            else:
                tot_noshow += 1

            lost = r.total_amount or Decimal("0.00")
            fees = fee_map.get(r.id, Decimal("0.00"))
            tot_lost += lost
            tot_fees += fees

            g_name = f"{r.guest.first_name} {r.guest.last_name}".strip() if r.guest else "Unknown"

            items.append(
                CancellationItem(
                    reservation_id=r.id,
                    booking_number=r.booking_number,
                    booked_at=r.created_at,
                    cancelled_at=r.cancelled_at,
                    status=r.status,
                    guest_name=g_name,
                    check_in_at=r.check_in_at,
                    check_out_at=r.check_out_at,
                    lost_revenue=lost,
                    fees_charged=fees,
                    cancellation_reason=r.cancellation_reason,
                )
            )

        return CancellationReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            currency=currency,
            total_cancellations=tot_canc,
            total_no_shows=tot_noshow,
            total_lost_revenue=tot_lost,
            total_fees_charged=tot_fees,
            items=items,
        )

    async def get_night_audit_summary_report(
        self,
        db: AsyncSession,
        property_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> NightAuditReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        start_d = from_date or (datetime.now(timezone.utc).date() - timedelta(days=30))
        end_d = to_date or datetime.now(timezone.utc).date()
        currency = prop.currency or "INR"

        stmt = (
            select(PropertyDailySummary)
            .where(
                PropertyDailySummary.property_id == property_id,
                PropertyDailySummary.business_date >= start_d,
                PropertyDailySummary.business_date <= end_d,
            )
            .order_by(PropertyDailySummary.business_date.desc())
        )
        res = await db.execute(stmt)
        summaries = list(res.scalars().all())

        items: List[NightAuditSummaryItem] = []
        for s in summaries:
            items.append(
                NightAuditSummaryItem(
                    business_date=s.business_date,
                    total_rooms=s.total_rooms,
                    rooms_available=s.rooms_available,
                    rooms_sold=s.rooms_sold,
                    rooms_ooo=s.rooms_ooo,
                    occupancy_rate_percent=float(s.occupancy_rate_percent),
                    room_revenue=s.room_revenue,
                    service_revenue=s.service_revenue,
                    tax_revenue=s.tax_revenue,
                    total_revenue=s.total_revenue,
                    adr=float(s.adr),
                    revpar=float(s.revpar),
                    total_payments_collected=s.total_payments_collected,
                    no_shows_marked=s.no_shows_marked,
                )
            )

        return NightAuditReportResponse(
            property_id=property_id,
            property_name=prop.name,
            from_date=start_d,
            to_date=end_d,
            currency=currency,
            total_audited_days=len(items),
            items=items,
        )

    async def get_guest_history_report(
        self,
        db: AsyncSession,
        property_id: str,
        limit: int = 100,
    ) -> GuestHistoryReportResponse:
        prop = await self._get_property_or_404(db, property_id)
        currency = prop.currency or "INR"

        stmt = (
            select(
                Guest,
                func.count(Reservation.id).label("total_bookings"),
                func.count(case((Reservation.status == ReservationStatus.CHECKED_OUT.value, 1))).label("completed_stays"),
                func.coalesce(func.sum(Reservation.total_amount), Decimal("0.00")).label("total_spent"),
                func.max(Reservation.check_out_at).label("last_visit"),
            )
            .join(Reservation, Reservation.guest_id == Guest.id)
            .where(
                Reservation.property_id == property_id,
                Guest.organization_id == prop.organization_id,
            )
            .group_by(Guest.id)
            .order_by(func.coalesce(func.sum(Reservation.total_amount), Decimal("0.00")).desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        rows = res.all()

        items: List[GuestHistoryItem] = []
        repeat_count = 0

        for row in rows:
            g = row[0]
            tot_bkg = int(row[1])
            comp_stays = int(row[2])
            tot_spent = Decimal(str(row[3]))
            last_v = row[4]

            is_rep = (tot_bkg > 1)
            if is_rep:
                repeat_count += 1

            items.append(
                GuestHistoryItem(
                    guest_id=g.id,
                    guest_name=f"{g.first_name} {g.last_name or ''}".strip(),
                    email=g.email,
                    phone=g.phone,
                    city=g.city,
                    total_bookings=tot_bkg,
                    completed_stays=comp_stays,
                    total_nights=tot_bkg,
                    total_spent=tot_spent,
                    is_repeat_guest=is_rep,
                    last_visit=last_v,
                )
            )

        return GuestHistoryReportResponse(
            property_id=property_id,
            property_name=prop.name,
            currency=currency,
            total_guests_tracked=len(items),
            repeat_guests_count=repeat_count,
            items=items,
        )


report_service = ReportService()
