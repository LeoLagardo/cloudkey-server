import logging
import secrets
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.integrations.aiosell.auth import decrypt_credit_card_payload
from app.integrations.aiosell.exceptions import (
    AiosellConfigError,
    AiosellMappingError,
    AiosellWebhookError,
)
from app.integrations.aiosell.mappings import (
    get_aiosell_client_for_property,
    get_property_config_by_hotel_code,
    resolve_cloudkey_rate_plan_id,
    resolve_cloudkey_room_type_id,
)
from app.integrations.aiosell.schemas import (
    AiosellReservationWebhookPayload,
    AiosellStandardResponse,
    AiosellWebhookResponse,
    NoShowPushRequest,
)
from app.models.folio import Folio
from app.models.guest import Guest
from app.models.property import Property
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate
from app.models.reservation import (
    Reservation,
    ReservationGuest,
    ReservationRoom,
    ReservationRoomRate,
)
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.utils.enums import (
    BookingType,
    FolioStatus,
    FolioType,
    ReservationSource,
    ReservationStatus,
)

logger = logging.getLogger(__name__)


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        # Handles "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
        return datetime.fromisoformat(date_str.split(" ")[0]).date()
    except Exception:
        return None


def _parse_datetime(dt_str: Optional[str], default_time: time = time(12, 0)) -> datetime:
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        if " " in dt_str:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(dt_str).date()
        return datetime.combine(d, default_time, tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


async def handle_webhook_reservation(
    db: AsyncSession,
    payload: AiosellReservationWebhookPayload,
) -> AiosellWebhookResponse:
    """
    Process inbound reservation webhooks from Aiosell:
    - action == 'book': New reservation creation
    - action == 'modify': Full update of existing reservation
    - action == 'cancel': Cancellation of reservation
    """
    config = await get_property_config_by_hotel_code(db, payload.hotelCode)
    if not config:
        raise AiosellConfigError(
            f"No active property configuration found for hotelCode: '{payload.hotelCode}'"
        )

    property_id = config.property_id
    property_obj = await db.get(Property, property_id)
    if not property_obj:
        raise AiosellConfigError(f"Property {property_id} not found in database.")

    logger.info(
        f"[Aiosell] Processing webhook '{payload.action}' for bookingId={payload.bookingId}, channel={payload.channel}"
    )

    if payload.action == "book":
        return await _handle_book_action(db, property_obj, config, payload)
    elif payload.action == "modify":
        return await _handle_modify_action(db, property_obj, config, payload)
    elif payload.action == "cancel":
        return await _handle_cancel_action(db, property_obj, config, payload)
    else:
        raise AiosellWebhookError(f"Unsupported webhook action: '{payload.action}'")


async def _handle_book_action(
    db: AsyncSession,
    property_obj: Property,
    config,
    payload: AiosellReservationWebhookPayload,
) -> AiosellWebhookResponse:
    property_id = property_obj.id

    # 1. Idempotency check: see if booking already exists
    existing_stmt = select(Reservation).where(
        Reservation.property_id == property_id,
        Reservation.channel_booking_ref == payload.bookingId,
    )
    existing_res = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_res:
        logger.info(f"[Aiosell] Booking {payload.bookingId} already exists. Delegating to modify.")
        return await _handle_modify_action(db, property_obj, config, payload)

    # 2. Match or create booker guest
    guest_info = payload.guest
    first_name = (guest_info.firstName if guest_info and guest_info.firstName else "OTA").strip()
    last_name = (guest_info.lastName if guest_info and guest_info.lastName else "Guest").strip()
    email = guest_info.email.strip() if guest_info and guest_info.email else None
    phone = guest_info.phone.strip() if guest_info and guest_info.phone else None

    # Search for existing guest by email or phone within organization
    guest_match = None
    if email or phone:
        conditions = []
        if email:
            conditions.append(Guest.email == email)
        if phone:
            conditions.append(Guest.phone == phone)
        stmt_g = select(Guest).where(
            Guest.organization_id == property_obj.organization_id,
            and_(*conditions) if len(conditions) > 1 else conditions[0],
        )
        guest_match = (await db.execute(stmt_g)).scalars().first()

    if not guest_match:
        address = guest_info.address if guest_info else None
        guest_match = Guest(
            organization_id=property_obj.organization_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address_line_1=address.line1 if address else None,
            city=address.city if address else None,
            state=address.state if address else None,
            country=address.country if address else None,
            postal_code=address.zipCode if address else None,
            notes=f"Created via OTA ({payload.channel})",
        )
        db.add(guest_match)
        await db.flush()

    # 3. Determine dates
    checkin_dt = _parse_datetime(payload.checkin, default_time=time(14, 0))
    checkout_dt = _parse_datetime(payload.checkout, default_time=time(11, 0))
    if checkout_dt <= checkin_dt:
        checkout_dt = checkin_dt + timedelta(days=1)

    # 4. Generate unique booking number
    prefix = (property_obj.code or "OTA").upper().strip().replace(" ", "")[:6]
    rand_code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
    booking_number = f"{prefix}-OTA-{rand_code}"

    # 5. Financials
    total_amt = Decimal(str(payload.amount.amountAfterTax)) if payload.amount else Decimal("0.00")
    tax_amt = Decimal(str(payload.amount.tax)) if payload.amount else Decimal("0.00")
    currency = payload.amount.currency if payload.amount else (property_obj.currency or "INR")

    # 6. Decrypt credit card if present
    decrypted_card = None
    card_key = settings.AIOSELL_CARD_DECRYPTION_KEY
    if payload.creditCard and card_key:
        try:
            decrypted_card = decrypt_credit_card_payload(
                payload.creditCard.model_dump(),
                card_key,
            )
            logger.info(f"[Aiosell] Decrypted credit card details for booking {payload.bookingId}")
        except Exception as e:
            logger.error(f"[Aiosell] Card decryption failed: {e}")

    # 7. Create Master Reservation
    reservation = Reservation(
        property_id=property_id,
        booking_number=booking_number,
        guest_id=guest_match.id,
        booking_type=BookingType.NIGHTLY.value,
        source=ReservationSource.OTA.value,
        channel_name=payload.channel,
        channel_booking_ref=payload.bookingId,
        status=ReservationStatus.CONFIRMED.value,
        check_in_at=checkin_dt,
        check_out_at=checkout_dt,
        currency=currency,
        total_amount=total_amt,
        total_tax_amount=tax_amt,
        special_requests=payload.specialRequests or "",
    )
    db.add(reservation)
    await db.flush()

    # 8. Create ReservationRooms & Daily Rates
    stay_dates_to_increment: List[tuple[str, date]] = []
    if payload.rooms:
        for r_item in payload.rooms:
            room_type_id = await resolve_cloudkey_room_type_id(db, property_id, r_item.roomCode)
            if not room_type_id:
                raise AiosellMappingError(
                    f"Aiosell roomCode '{r_item.roomCode}' is not mapped to any room type in CloudKey."
                )

            rate_plan_id = await resolve_cloudkey_rate_plan_id(db, property_id, r_item.rateplanCode)
            if not rate_plan_id:
                # Fallback to first active rate plan for this room type
                stmt_rp = select(RatePlan.id).where(
                    RatePlan.property_id == property_id,
                    RatePlan.room_type_id == room_type_id,
                    RatePlan.status == "ACTIVE",
                )
                rate_plan_id = (await db.execute(stmt_rp)).scalars().first()

            res_room = ReservationRoom(
                reservation_id=reservation.id,
                room_type_id=room_type_id,
                room_id=None,  # Left unassigned until front desk check-in
                rate_plan_id=rate_plan_id,
                status=ReservationStatus.CONFIRMED.value,
                check_in_at=checkin_dt,
                check_out_at=checkout_dt,
                adults=r_item.occupancy.adults if r_item.occupancy else 1,
                children=r_item.occupancy.children if r_item.occupancy else 0,
            )
            db.add(res_room)
            await db.flush()

            # Link primary guest
            db.add(ReservationGuest(
                reservation_room_id=res_room.id,
                guest_id=guest_match.id,
                is_primary=True,
            ))

            # Daily rate snapshots
            if r_item.prices:
                for p in r_item.prices:
                    p_date = _parse_date(p.date)
                    if p_date:
                        price_dec = Decimal(str(p.sellRate))
                        db.add(ReservationRoomRate(
                            reservation_room_id=res_room.id,
                            stay_date=p_date,
                            rate_plan_rate_id=None,
                            base_amount=price_dec,
                            extra_person_amount=Decimal("0.00"),
                            discount_amount=Decimal("0.00"),
                            net_amount=price_dec,
                            tax_amount=Decimal("0.00"),
                            total_amount=price_dec,
                        ))
                        stay_dates_to_increment.append((room_type_id, p_date))

    # 9. Create 1 OPEN Master Folio
    folio_rand = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
    period = datetime.now(timezone.utc).strftime("%y%m")
    folio = Folio(
        property_id=property_id,
        reservation_id=reservation.id,
        guest_id=guest_match.id,
        folio_number=f"FOL-{prefix}-{period}-{folio_rand}",
        folio_type=FolioType.GUEST.value,
        status=FolioStatus.OPEN.value,
        currency=currency,
        opened_at=datetime.now(timezone.utc),
    )
    db.add(folio)

    # 10. Adjust Inventory (Increment sold_rooms)
    for rt_id, s_date in stay_dates_to_increment:
        stmt_inv = select(RoomTypeInventory).where(
            RoomTypeInventory.property_id == property_id,
            RoomTypeInventory.room_type_id == rt_id,
            RoomTypeInventory.stay_date == s_date,
        )
        inv_record = (await db.execute(stmt_inv)).scalar_one_or_none()
        if inv_record:
            inv_record.sold_rooms += 1

    await db.commit()
    logger.info(f"[Aiosell] Successfully created reservation {reservation.booking_number} ({payload.bookingId})")
    return AiosellWebhookResponse(
        success=True,
        message=f"Reservation {reservation.booking_number} created successfully",
    )


async def _handle_modify_action(
    db: AsyncSession,
    property_obj: Property,
    config,
    payload: AiosellReservationWebhookPayload,
) -> AiosellWebhookResponse:
    property_id = property_obj.id

    # 1. Locate existing reservation
    stmt = (
        select(Reservation)
        .options(selectinload(Reservation.rooms))
        .where(
            Reservation.property_id == property_id,
            Reservation.channel_booking_ref == payload.bookingId,
        )
    )
    res = (await db.execute(stmt)).scalar_one_or_none()
    if not res:
        # If not found, create as new booking
        return await _handle_book_action(db, property_obj, config, payload)

    # 2. Update Master Fields
    if payload.checkin:
        res.check_in_at = _parse_datetime(payload.checkin, default_time=time(14, 0))
    if payload.checkout:
        res.check_out_at = _parse_datetime(payload.checkout, default_time=time(11, 0))

    if payload.amount:
        res.total_amount = Decimal(str(payload.amount.amountAfterTax))
        res.total_tax_amount = Decimal(str(payload.amount.tax))

    if payload.specialRequests is not None:
        res.special_requests = payload.specialRequests

    # Update guest contact info if provided
    if payload.guest and res.guest_id:
        g = await db.get(Guest, res.guest_id)
        if g:
            if payload.guest.email:
                g.email = payload.guest.email
            if payload.guest.phone:
                g.phone = payload.guest.phone

    await db.commit()
    logger.info(f"[Aiosell] Successfully modified reservation {res.booking_number} ({payload.bookingId})")
    return AiosellWebhookResponse(
        success=True,
        message=f"Reservation {res.booking_number} modified successfully",
    )


async def _handle_cancel_action(
    db: AsyncSession,
    property_obj: Property,
    config,
    payload: AiosellReservationWebhookPayload,
) -> AiosellWebhookResponse:
    property_id = property_obj.id

    stmt = (
        select(Reservation)
        .options(selectinload(Reservation.rooms).selectinload(ReservationRoom.room_rates))
        .where(
            Reservation.property_id == property_id,
            Reservation.channel_booking_ref == payload.bookingId,
        )
    )
    res = (await db.execute(stmt)).scalar_one_or_none()
    if not res:
        logger.warning(f"[Aiosell] Cancel action received for non-existent booking {payload.bookingId}")
        return AiosellWebhookResponse(success=True, message="Reservation not found or already cancelled")

    # Transition status
    res.status = ReservationStatus.CANCELLED.value
    res.cancelled_at = datetime.now(timezone.utc)
    res.cancellation_reason = f"Cancelled via {payload.channel} on Aiosell"

    # Decrement sold inventory
    for room in res.rooms:
        room.status = ReservationStatus.CANCELLED.value
        for rate in room.room_rates:
            stmt_inv = select(RoomTypeInventory).where(
                RoomTypeInventory.property_id == property_id,
                RoomTypeInventory.room_type_id == room.room_type_id,
                RoomTypeInventory.stay_date == rate.stay_date,
            )
            inv_record = (await db.execute(stmt_inv)).scalar_one_or_none()
            if inv_record and inv_record.sold_rooms > 0:
                inv_record.sold_rooms -= 1

    await db.commit()
    logger.info(f"[Aiosell] Successfully cancelled reservation {res.booking_number} ({payload.bookingId})")
    return AiosellWebhookResponse(
        success=True,
        message=f"Reservation {res.booking_number} cancelled successfully",
    )


async def mark_reservation_noshow(
    db: AsyncSession,
    reservation_id: str,
) -> AiosellStandardResponse:
    """
    Mark a reservation as a no-show in CloudKey PMS and notify Aiosell/OTA.
    Supported channels: booking.com, gommt.
    """
    res = await db.get(Reservation, reservation_id)
    if not res:
        raise AiosellWebhookError(f"Reservation {reservation_id} not found.")

    if not res.channel_booking_ref:
        raise AiosellWebhookError("Cannot mark no-show on Aiosell for non-channel reservations.")

    client, config = await get_aiosell_client_for_property(db, res.property_id)

    # Normalize channel name (e.g. "Booking.com" -> "booking.com", "Goibibo" / "MakeMyTrip" -> "gommt")
    raw_channel = (res.channel_name or "").lower()
    if "booking" in raw_channel:
        channel_id = "booking.com"
    elif "goibibo" in raw_channel or "makemytrip" in raw_channel or "mmt" in raw_channel:
        channel_id = "gommt"
    else:
        channel_id = raw_channel

    payload = NoShowPushRequest(
        hotelCode=config.aiosell_hotel_code,
        bookingId=res.channel_booking_ref,
        channel=channel_id,
    )

    resp = await client.mark_noshow(payload, pms_slug=config.pms_slug)

    # Update CloudKey status to NO_SHOW
    res.status = ReservationStatus.NO_SHOW.value
    await db.commit()

    return resp
