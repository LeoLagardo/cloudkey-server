from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.property import crud_property
from app.models.folio import Folio, FolioTransaction, Payment
from app.models.property import Property
from app.models.reservation import Reservation, ReservationRoom
from app.models.room import Room
from app.models.room_type import RoomType
from app.schemas.dashboard import (
    ArrivalGuestItem,
    DashboardKPIs,
    DashboardSummaryResponse,
    DepartureGuestItem,
    HousekeepingPriorityAlert,
    OccupancyDayTrend,
    PropertyBrief,
    RoomInventorySummary,
    ShiftSessionInfo,
    TapeRoomItem,
)
from app.utils.enums import (
    FolioEntryType,
    HousekeepingStatus,
    OccupancyStatus,
    ReservationStatus,
    RoomStatus,
)
from app.utils.exceptions import EntityNotFoundException


class DashboardService:
    async def get_dashboard_summary(
        self,
        db: AsyncSession,
        property_id: str,
        business_date: Optional[date] = None,
    ) -> DashboardSummaryResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        target_date: date = (
            business_date
            or prop.business_date
            or datetime.now(timezone.utc).date()
        )

        currency_symbol = "₹" if prop.currency == "INR" else f"{prop.currency} "

        # 1. Fetch Rooms with Room Types
        rooms_stmt = (
            select(Room)
            .options(selectinload(Room.room_type))
            .where(Room.property_id == property_id)
            .order_by(Room.room_number)
        )
        rooms_res = await db.execute(rooms_stmt)
        rooms: List[Room] = list(rooms_res.scalars().all())

        # 2. Fetch Reservations for property with relationships
        reservations_stmt = (
            select(Reservation)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_rates),
            )
            .where(Reservation.property_id == property_id)
            .order_by(Reservation.check_in_at.asc())
        )
        res_result = await db.execute(reservations_stmt)
        all_reservations: List[Reservation] = list(res_result.scalars().all())

        # 3. Fetch Folios & Payments for property
        folios_stmt = (
            select(Folio)
            .options(
                selectinload(Folio.transactions),
                selectinload(Folio.payments),
            )
            .where(Folio.property_id == property_id)
        )
        folios_res = await db.execute(folios_stmt)
        folios_list: List[Folio] = list(folios_res.scalars().all())
        folio_map: Dict[str, Folio] = {
            f.reservation_id: f for f in folios_list if f.reservation_id
        }

        # Also get all payments for property to calculate revenue
        payments_stmt = select(Payment).where(Payment.property_id == property_id)
        payments_res = await db.execute(payments_stmt)
        all_payments: List[Payment] = list(payments_res.scalars().all())

        # ─── CALCULATE ARRIVALS TODAY ──────────────────────────────────────────
        arrivals: List[ArrivalGuestItem] = []
        arrivals_checked_in_count = 0
        arrivals_pending_count = 0

        for r in all_reservations:
            if r.status == ReservationStatus.CANCELLED.value:
                continue

            r_check_in = r.check_in_at.date() if isinstance(r.check_in_at, datetime) else r.check_in_at
            if r_check_in == target_date:
                is_checked_in = r.status == ReservationStatus.CHECKED_IN.value
                if is_checked_in:
                    arrivals_checked_in_count += 1
                else:
                    arrivals_pending_count += 1

                # Guest details
                guest_name = "Unknown Guest"
                is_verified = False
                if r.guest:
                    guest_name = f"{r.guest.first_name} {r.guest.last_name or ''}".strip()
                    is_verified = bool(r.guest.id_number or r.guest.id_type)

                # Room details
                primary_res_room = r.rooms[0] if r.rooms else None
                assigned_room = primary_res_room.room if primary_res_room else None
                room_type = primary_res_room.room_type if primary_res_room else None

                room_num = assigned_room.room_number if assigned_room else "Unassigned"
                room_cat = room_type.name if room_type else "Standard Room"

                room_status_note = "Clean & Inspected"
                room_status_type = "ready"

                if assigned_room:
                    if assigned_room.housekeeping_status == HousekeepingStatus.DIRTY.value:
                        room_status_note = "Housekeeping in progress"
                        room_status_type = "dirty"
                    elif assigned_room.status in (RoomStatus.MAINTENANCE.value, RoomStatus.OUT_OF_SERVICE.value):
                        room_status_note = f"Room {assigned_room.status.replace('_', ' ').title()}"
                        room_status_type = "dirty"
                    else:
                        room_status_note = "Clean & Inspected"
                        room_status_type = "ready"
                else:
                    room_status_note = "Unassigned room"
                    room_status_type = "dirty"

                # Check VIP
                is_vip = bool(
                    (r.special_requests and "vip" in r.special_requests.lower())
                    or (r.guest and r.guest.notes and "vip" in r.guest.notes.lower())
                )
                if is_vip and room_status_type != "dirty":
                    room_status_type = "vip"

                # Payment details & Folio
                folio = folio_map.get(r.id)
                total_amount = r.total_amount or Decimal("0.00")

                total_paid = Decimal("0.00")
                if folio and folio.payments:
                    total_paid = sum(
                        (p.amount for p in folio.payments if p.status in ("COMPLETED", "CAPTURED")),
                        Decimal("0.00"),
                    )

                if total_amount > 0 and total_paid >= total_amount:
                    payment_status = "paid"
                    payment_text = "Paid 100%"
                elif total_paid > 0:
                    payment_status = "partial"
                    payment_text = f"Partial ({currency_symbol}{int(total_paid):,})"
                else:
                    payment_status = "unpaid"
                    payment_text = "Unpaid"

                if is_checked_in:
                    action_text = "Checked In"
                    action_type = "checkin"
                elif payment_status == "unpaid":
                    action_text = "Collect & In"
                    action_type = "collect"
                else:
                    action_text = "Check In"
                    action_type = "checkin"

                eta_time = r.check_in_at.strftime("%I:%M %p") if isinstance(r.check_in_at, datetime) else "02:00 PM"
                eta_note = r.special_requests or "Standard Check-in"

                arrivals.append(
                    ArrivalGuestItem(
                        id=r.id,
                        booking_number=r.booking_number,
                        guest_id=r.guest_id,
                        name=guest_name,
                        is_verified=is_verified,
                        is_vip=is_vip,
                        res_code=f"{r.booking_number} • {r.source.replace('_', ' ').title()}",
                        adults=primary_res_room.adults if primary_res_room else 1,
                        children=primary_res_room.children if primary_res_room else 0,
                        room_reservation_id=primary_res_room.id if primary_res_room else None,
                        room_id=assigned_room.id if assigned_room else None,
                        room_number=room_num,
                        room_category=room_cat,
                        room_status_note=room_status_note,
                        room_status_type=room_status_type,
                        eta=eta_time,
                        eta_note=eta_note,
                        folio_total=f"{currency_symbol}{total_amount:,.2f}",
                        folio_id=folio.id if folio else None,
                        payment_status=payment_status,
                        payment_text=payment_text,
                        action_text=action_text,
                        action_type=action_type,
                        reservation_status=r.status,
                    )
                )

        arrivals_total = len(arrivals)

        # ─── CALCULATE DEPARTURES TODAY ────────────────────────────────────────
        departures: List[DepartureGuestItem] = []
        departures_out_count = 0
        departures_pending_count = 0

        for r in all_reservations:
            if r.status == ReservationStatus.CANCELLED.value:
                continue

            r_check_out = r.check_out_at.date() if isinstance(r.check_out_at, datetime) else r.check_out_at
            if r_check_out == target_date:
                is_checked_out = r.status == ReservationStatus.CHECKED_OUT.value
                if is_checked_out:
                    departures_out_count += 1
                else:
                    departures_pending_count += 1

                guest_name = "Unknown Guest"
                if r.guest:
                    guest_name = f"{r.guest.first_name} {r.guest.last_name or ''}".strip()

                primary_res_room = r.rooms[0] if r.rooms else None
                assigned_room = primary_res_room.room if primary_res_room else None
                room_num = assigned_room.room_number if assigned_room else "Unassigned"

                # Calculate folio balance
                folio = folio_map.get(r.id)
                folio_balance = Decimal("0.00")
                if folio:
                    debits = sum(
                        (t.total_amount for t in folio.transactions if t.entry_type == FolioEntryType.DEBIT.value),
                        Decimal("0.00"),
                    )
                    credits = sum(
                        (t.total_amount for t in folio.transactions if t.entry_type == FolioEntryType.CREDIT.value),
                        Decimal("0.00"),
                    )
                    payments_total = sum(
                        (p.amount for p in folio.payments if p.status in ("COMPLETED", "CAPTURED")),
                        Decimal("0.00"),
                    )
                    total_settled = credits if credits > 0 else payments_total
                    folio_balance = max(Decimal("0.00"), debits - total_settled)
                elif r.total_amount:
                    folio_balance = r.total_amount

                has_balance = folio_balance > Decimal("0.00")

                if is_checked_out:
                    status = "zero"
                    status_text = "Completed"
                    action_text = "Checked Out"
                    action_type = "checkout"
                elif has_balance:
                    status = "pending"
                    status_text = "Pending Folio"
                    action_text = "Settle & Out"
                    action_type = "settle"
                else:
                    status = "zero"
                    status_text = "Zero Balance"
                    action_text = "Check Out"
                    action_type = "checkout"

                departures.append(
                    DepartureGuestItem(
                        id=r.id,
                        booking_number=r.booking_number,
                        guest_id=r.guest_id,
                        name=guest_name,
                        keycards_count=primary_res_room.adults if primary_res_room else 1,
                        late_checkout_time=None,
                        room_number=room_num,
                        status_note_primary="Inspection completed" if not has_balance else "Folio balance due",
                        status_note_secondary="Housekeeping clearance OK" if not has_balance else "Payment required at desk",
                        folio_balance=f"{currency_symbol}{folio_balance:,.2f}",
                        folio_id=folio.id if folio else None,
                        status=status,
                        status_text=status_text,
                        action_text=action_text,
                        action_type=action_type,
                        reservation_status=r.status,
                    )
                )

        departures_total = len(departures)

        # ─── IN-HOUSE & ROOM COUNTS ────────────────────────────────────────────
        in_house_reservations = [
            r for r in all_reservations if r.status == ReservationStatus.CHECKED_IN.value
        ]
        in_house_count = len(in_house_reservations)

        # Occupied rooms from real room occupancy_status or active checked-in reservations
        occupied_room_ids = {
            rm.id for rm in rooms if rm.occupancy_status == OccupancyStatus.OCCUPIED.value
        }
        for r in in_house_reservations:
            for rr in r.rooms:
                if rr.room_id:
                    occupied_room_ids.add(rr.room_id)

        in_house_rooms_count = len(occupied_room_ids)

        available_rooms_count = sum(
            1
            for r in rooms
            if r.status == RoomStatus.AVAILABLE.value
            and r.occupancy_status == OccupancyStatus.VACANT.value
            and r.housekeeping_status in (HousekeepingStatus.CLEAN.value, HousekeepingStatus.INSPECTED.value)
            and r.id not in occupied_room_ids
        )
        total_rooms_count = len(rooms)
        dirty_rooms_count = sum(
            1 for r in rooms if r.housekeeping_status == HousekeepingStatus.DIRTY.value
        )
        oos_rooms_count = sum(
            1
            for r in rooms
            if r.status in (RoomStatus.MAINTENANCE.value, RoomStatus.OUT_OF_SERVICE.value, RoomStatus.INACTIVE.value)
        )

        occupancy_rate = (
            round((in_house_rooms_count / total_rooms_count) * 100, 1)
            if total_rooms_count > 0
            else 0.0
        )

        # ─── REVENUE CALCULATIONS ──────────────────────────────────────────────
        paid_today = sum(
            (
                p.amount
                for p in all_payments
                if (
                    p.status in ("COMPLETED", "CAPTURED")
                    and (
                        (isinstance(p.received_at, datetime) and p.received_at.date() == target_date)
                        or (isinstance(p.created_at, datetime) and p.created_at.date() == target_date)
                    )
                )
            ),
            Decimal("0.00"),
        )

        # Pending revenue across active arrivals / folios
        pending_today = sum(
            (
                Decimal(g.folio_total.replace(currency_symbol, "").replace(",", ""))
                for g in arrivals
                if g.payment_status in ("unpaid", "partial")
            ),
            Decimal("0.00"),
        )
        total_revenue_stat = paid_today + pending_today

        kpis = DashboardKPIs(
            arrivals_total=arrivals_total,
            arrivals_checked_in=arrivals_checked_in_count,
            arrivals_pending=arrivals_pending_count,
            arrivals_subtext=f"{arrivals_checked_in_count} in • {arrivals_pending_count} pending",
            departures_total=departures_total,
            departures_checked_out=departures_out_count,
            departures_pending=departures_pending_count,
            departures_subtext=f"{departures_out_count} out • {departures_pending_count} pending",
            in_house_count=in_house_count,
            in_house_rooms_count=in_house_rooms_count,
            in_house_subtext=f"Across {in_house_rooms_count} occupied rooms" if in_house_rooms_count != 1 else "Across 1 occupied room",
            available_rooms_count=available_rooms_count,
            total_rooms_count=total_rooms_count,
            available_subtext="Inspected & Ready",
            occupancy_rate=occupancy_rate,
            occupancy_subtext=f"{in_house_rooms_count} of {total_rooms_count} keys occupied",
            occupancy_trend_up=occupancy_rate > 50.0,
            revenue_today=f"{currency_symbol}{total_revenue_stat:,.0f}",
            revenue_paid_today=f"{currency_symbol}{paid_today:,.0f}",
            revenue_pending_today=f"{currency_symbol}{pending_today:,.0f}",
            revenue_subtext=f"{currency_symbol}{paid_today:,.0f} paid • {currency_symbol}{pending_today:,.0f} pend",
        )

        # ─── TAPE ROOMS PREVIEW ────────────────────────────────────────────────
        tape_rooms: List[TapeRoomItem] = []
        for rm in rooms:
            type_abbr = rm.room_type.code if rm.room_type and rm.room_type.code else (rm.room_type.name[:3].upper() if rm.room_type else "STD")

            # Determine live status & dot
            is_occupied = rm.id in occupied_room_ids or rm.occupancy_status == OccupancyStatus.OCCUPIED.value
            is_dirty = rm.housekeeping_status == HousekeepingStatus.DIRTY.value
            is_oos = rm.status in (RoomStatus.MAINTENANCE.value, RoomStatus.OUT_OF_SERVICE.value, RoomStatus.INACTIVE.value)

            # Check if this room is assigned to an arrival today
            is_assigned_to_arrival = any(
                a.room_id == rm.id or a.room_number == rm.room_number for a in arrivals
            )
            has_alert = is_assigned_to_arrival and is_dirty

            if is_oos:
                st = "OOS"
                dot = "oos"
            elif is_occupied:
                st = "Occ"
                dot = "occ"
            elif is_dirty:
                st = "Drty"
                dot = "dirty"
            else:
                st = "Rdy"
                dot = "ready"

            tape_rooms.append(
                TapeRoomItem(
                    id=rm.id,
                    number=rm.room_number,
                    floor=rm.floor or "1",
                    type=type_abbr,
                    room_type_name=rm.room_type.name if rm.room_type else "Room",
                    status=st,
                    dot_color=dot,
                    is_alert=has_alert,
                )
            )

        # ─── HOUSEKEEPING ALERT ────────────────────────────────────────────────
        housekeeping_alert: Optional[HousekeepingPriorityAlert] = None
        for a in arrivals:
            if a.room_status_type == "dirty" and a.room_number != "Unassigned":
                housekeeping_alert = HousekeepingPriorityAlert(
                    room_id=a.room_id or "",
                    room_number=a.room_number,
                    guest_name=a.name,
                    reservation_id=a.id,
                    room_reservation_id=a.room_reservation_id,
                    eta=a.eta,
                    message=f"Room {a.room_number} scheduled arrival for {a.name} at {a.eta}. Currently marked 'Dirty'.",
                )
                break

        # ─── 7-DAY OCCUPANCY FORECAST ──────────────────────────────────────────
        occupancy_trend: List[OccupancyDayTrend] = []
        start_date = target_date - timedelta(days=1)
        peak_percentage = -1

        for i in range(7):
            d = start_date + timedelta(days=i)
            # Count reservations that occupy a room on this date
            day_occupied_count = 0
            for r in all_reservations:
                if r.status in (ReservationStatus.CANCELLED.value, ReservationStatus.NO_SHOW.value):
                    continue
                r_in = r.check_in_at.date() if isinstance(r.check_in_at, datetime) else r.check_in_at
                r_out = r.check_out_at.date() if isinstance(r.check_out_at, datetime) else r.check_out_at
                if r_in <= d < r_out:
                    day_occupied_count += len(r.rooms) if r.rooms else 1

            pct = (
                min(100, round((day_occupied_count / total_rooms_count) * 100))
                if total_rooms_count > 0
                else 0
            )
            if pct > peak_percentage:
                peak_percentage = pct

            occupancy_trend.append(
                OccupancyDayTrend(
                    day=d.strftime("%a"),
                    date=d.isoformat(),
                    occupied_count=day_occupied_count,
                    total_count=total_rooms_count,
                    percentage=pct,
                    is_today=(d == target_date),
                    is_peak=False,  # Will flag peak below
                )
            )

        # Flag peak
        for ot in occupancy_trend:
            if ot.percentage == peak_percentage and peak_percentage > 0:
                ot.is_peak = True
                break

        occupancy_avg = (
            round(sum(ot.percentage for ot in occupancy_trend) / len(occupancy_trend), 1)
            if occupancy_trend
            else 0.0
        )

        # ─── SESSION & AUDIT INFO ──────────────────────────────────────────────
        hour = datetime.now().hour
        if 5 <= hour < 12:
            shift_title = "LIVE FRONT DESK SESSION / SHIFT A (MORNING)"
        elif 12 <= hour < 18:
            shift_title = "LIVE FRONT DESK SESSION / SHIFT B (AFTERNOON)"
        elif 18 <= hour < 23:
            shift_title = "LIVE FRONT DESK SESSION / SHIFT C (EVENING)"
        else:
            shift_title = "LIVE FRONT DESK SESSION / NIGHT AUDIT SHIFT"

        formatted_date = target_date.strftime("%a, %d %b %Y")

        return DashboardSummaryResponse(
            property=PropertyBrief(
                id=prop.id,
                name=prop.name,
                code=prop.code,
                city=prop.city or "Bangalore",
                timezone=prop.timezone or "Asia/Kolkata",
                currency=prop.currency or "INR",
                business_date=target_date,
            ),
            session=ShiftSessionInfo(
                shift_name=shift_title,
                date_formatted=formatted_date,
                business_date=target_date,
                audit_status="Verified 04:30 AM",
                temperature_celsius=29,
                weather_condition=f"{prop.city or 'Local'}, Pleasant",
            ),
            kpis=kpis,
            arrivals=arrivals,
            departures=departures,
            room_inventory=RoomInventorySummary(
                available=available_rooms_count,
                occupied=in_house_rooms_count,
                dirty=dirty_rooms_count,
                out_of_service=oos_rooms_count,
                total=total_rooms_count,
            ),
            tape_rooms=tape_rooms,
            housekeeping_alert=housekeeping_alert,
            occupancy_trend=occupancy_trend,
            occupancy_average=occupancy_avg,
        )


dashboard_service = DashboardService()
