import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from app.integrations.aiosell.auth import (
    decrypt_card_field,
    decrypt_credit_card_payload,
    generate_basic_auth_header,
    verify_basic_auth,
)
from app.integrations.aiosell.client import AiosellClient
from app.integrations.aiosell.inventory import push_property_inventory
from app.integrations.aiosell.mappings import (
    set_rate_plan_mapping,
    set_room_type_mapping,
)
from app.integrations.aiosell.rates import push_property_rates
from app.integrations.aiosell.reservations import (
    handle_webhook_reservation,
    mark_reservation_noshow,
)
from app.integrations.aiosell.schemas import (
    AiosellBookingAmount,
    AiosellBookingGuest,
    AiosellDailyPrice,
    AiosellReservationWebhookPayload,
    AiosellRoomBookingItem,
    AiosellRoomOccupancy,
)
from app.models.channel_manager import AiosellPropertyConfig
from app.models.organization import Organization
from app.models.property import Property
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate
from app.models.reservation import Reservation
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.utils.enums import ReservationStatus


# ---------------------------------------------------------------------------
# Test Auth & Encryption
# ---------------------------------------------------------------------------

def test_basic_auth_generation_and_verification():
    header = generate_basic_auth_header("myuser", "mypass123")
    assert header.startswith("Basic ")

    assert verify_basic_auth(header, "myuser", "mypass123") is True
    assert verify_basic_auth(header, "wronguser", "mypass123") is False
    assert verify_basic_auth(header, "myuser", "wrongpass") is False
    assert verify_basic_auth("Bearer token123", "myuser", "mypass123") is False
    assert verify_basic_auth(None, "myuser", "mypass123") is False


def test_credit_card_decryption_aes128_ecb():
    key = "1234567890123456"  # Exactly 16 bytes for AES-128
    plaintext = "4111111111111111"

    # Encrypt using PKCS7
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.ECB())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    hex_ciphertext = ciphertext.hex()

    # Test decrypt_card_field
    decrypted = decrypt_card_field(hex_ciphertext, key)
    assert decrypted == plaintext

    # Test decrypt_credit_card_payload
    payload = {
        "cardNumber": hex_ciphertext,
        "cvv": None,
    }
    decrypted_dict = decrypt_credit_card_payload(payload, key)
    assert decrypted_dict["cardNumber"] == plaintext
    assert decrypted_dict["cvv"] is None


# ---------------------------------------------------------------------------
# Test Inbound Webhook: Book, Modify, Cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aiosell_reservation_webhook_lifecycle(db_session):
    # Setup test organization and property
    org = Organization(name="Test Hotel Chain", slug="test-hotel-chain")
    db_session.add(org)
    await db_session.flush()

    prop = Property(
        organization_id=org.id,
        name="Grand Test Hotel",
        code="GTH",
        currency="INR",
    )
    db_session.add(prop)
    await db_session.flush()

    # Setup room type and rate plan
    rt = RoomType(
        property_id=prop.id,
        name="Deluxe Room",
        code="DELUXE",
        base_occupancy=2,
        max_occupancy=3,
    )
    db_session.add(rt)
    await db_session.flush()

    rp = RatePlan(
        property_id=prop.id,
        room_type_id=rt.id,
        name="Room Only",
        code="RO",
        booking_type="NIGHTLY",
        status="ACTIVE",
    )
    db_session.add(rp)
    await db_session.flush()

    # Setup Aiosell Property Config
    aiosell_config = AiosellPropertyConfig(
        property_id=prop.id,
        aiosell_hotel_code="sandbox-hotel",
        pms_slug="sample-pms",
        is_active=True,
    )
    db_session.add(aiosell_config)

    # Setup mappings
    await set_room_type_mapping(db_session, prop.id, rt.id, "deluxe-room-code")
    await set_rate_plan_mapping(db_session, prop.id, rp.id, "ro-rateplan-code")

    # Setup initial inventory record
    inv_date = date(2026, 11, 1)
    inv = RoomTypeInventory(
        property_id=prop.id,
        room_type_id=rt.id,
        stay_date=inv_date,
        total_rooms=10,
        sold_rooms=0,
    )
    db_session.add(inv)
    await db_session.commit()

    # 1. ACTION: BOOK
    book_payload = AiosellReservationWebhookPayload(
        action="book",
        hotelCode="sandbox-hotel",
        channel="booking.com",
        bookingId="BK-999888",
        checkin="2026-11-01",
        checkout="2026-11-02",
        guest=AiosellBookingGuest(
            firstName="John",
            lastName="Doe",
            email="john.doe@example.com",
            phone="9876543210",
        ),
        amount=AiosellBookingAmount(
            amountAfterTax=5000.0,
            amountBeforeTax=4500.0,
            tax=500.0,
            currency="INR",
        ),
        rooms=[
            AiosellRoomBookingItem(
                roomCode="deluxe-room-code",
                rateplanCode="ro-rateplan-code",
                occupancy=AiosellRoomOccupancy(adults=2, children=0),
                prices=[AiosellDailyPrice(date="2026-11-01", sellRate=5000.0)],
            )
        ],
        specialRequests="Quiet room requested",
    )

    book_resp = await handle_webhook_reservation(db_session, book_payload)
    assert book_resp.success is True

    # Verify reservation created in database
    res = await db_session.get(Reservation, (await db_session.execute(
        Reservation.__table__.select().where(Reservation.channel_booking_ref == "BK-999888")
    )).scalar_one())
    assert res is not None
    assert res.channel_name == "booking.com"
    assert res.status == ReservationStatus.CONFIRMED.value
    assert res.total_amount == Decimal("5000.00")
    assert res.special_requests == "Quiet room requested"

    # Verify inventory was incremented
    await db_session.refresh(inv)
    assert inv.sold_rooms == 1

    # 2. ACTION: MODIFY
    modify_payload = AiosellReservationWebhookPayload(
        action="modify",
        hotelCode="sandbox-hotel",
        channel="booking.com",
        bookingId="BK-999888",
        checkin="2026-11-01",
        checkout="2026-11-02",
        amount=AiosellBookingAmount(
            amountAfterTax=5500.0,
            amountBeforeTax=5000.0,
            tax=500.0,
            currency="INR",
        ),
        specialRequests="High floor requested",
    )

    modify_resp = await handle_webhook_reservation(db_session, modify_payload)
    assert modify_resp.success is True

    await db_session.refresh(res)
    assert res.total_amount == Decimal("5500.00")
    assert res.special_requests == "High floor requested"

    # 3. ACTION: CANCEL
    cancel_payload = AiosellReservationWebhookPayload(
        action="cancel",
        hotelCode="sandbox-hotel",
        channel="booking.com",
        bookingId="BK-999888",
    )

    cancel_resp = await handle_webhook_reservation(db_session, cancel_payload)
    assert cancel_resp.success is True

    await db_session.refresh(res)
    assert res.status == ReservationStatus.CANCELLED.value
    assert res.cancelled_at is not None

    # Verify inventory was decremented
    await db_session.refresh(inv)
    assert inv.sold_rooms == 0


# ---------------------------------------------------------------------------
# Test Outbound Push (Mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inventory_and_rate_push(db_session):
    org = Organization(name="Outbound Push Hotel Org", slug="outbound-push-hotel-org")
    db_session.add(org)
    await db_session.flush()

    prop = Property(organization_id=org.id, name="Push Hotel", code="PUSH", currency="INR")
    db_session.add(prop)
    await db_session.flush()

    rt = RoomType(
        property_id=prop.id,
        name="Suite",
        code="SUITE",
        base_occupancy=2,
        max_occupancy=4,
    )
    db_session.add(rt)
    await db_session.flush()

    rp = RatePlan(
        property_id=prop.id,
        room_type_id=rt.id,
        name="Suite Rate",
        code="SR",
        booking_type="NIGHTLY",
        status="ACTIVE",
    )
    db_session.add(rp)
    await db_session.flush()

    # Rate plan price
    rpr = RatePlanRate(
        rate_plan_id=rp.id,
        duration=1,
        duration_unit="NIGHT",
        price=Decimal("7500.00"),
    )
    db_session.add(rpr)

    aiosell_config = AiosellPropertyConfig(
        property_id=prop.id,
        aiosell_hotel_code="hotel-push-1",
        pms_slug="sample-pms",
        sync_inventory=True,
        sync_rates=True,
        is_active=True,
    )
    db_session.add(aiosell_config)

    await set_room_type_mapping(db_session, prop.id, rt.id, "suite-code")
    await set_rate_plan_mapping(db_session, prop.id, rp.id, "suite-rate-code")

    # Add inventory
    test_dt = date(2026, 12, 1)
    inv = RoomTypeInventory(
        property_id=prop.id,
        room_type_id=rt.id,
        stay_date=test_dt,
        total_rooms=5,
        sold_rooms=1,
    )
    db_session.add(inv)
    await db_session.commit()

    # Mock client push
    with patch("app.integrations.aiosell.client.AiosellClient.push_inventory", new_callable=AsyncMock) as mock_inv, \
         patch("app.integrations.aiosell.client.AiosellClient.push_rates", new_callable=AsyncMock) as mock_rates:

        mock_inv.return_value = {"success": True}
        mock_rates.return_value = {"success": True}

        # Test inventory push
        await push_property_inventory(db_session, prop.id, test_dt, test_dt)
        mock_inv.assert_called_once()
        inv_payload = mock_inv.call_args[0][0]
        assert inv_payload.hotelCode == "hotel-push-1"
        assert inv_payload.updates[0].rooms[0].available == 4  # 5 total - 1 sold

        # Test rate push
        await push_property_rates(db_session, prop.id, test_dt, test_dt)
        mock_rates.assert_called_once()
        rates_payload = mock_rates.call_args[0][0]
        assert rates_payload.hotelCode == "hotel-push-1"
        assert rates_payload.updates[0].rates[0].rate == 7500.0


@pytest.mark.asyncio
async def test_webhook_endpoint_http(async_client, db_session):
    # Setup test org and property
    org = Organization(name="HTTP Org", slug="http-org")
    db_session.add(org)
    await db_session.flush()

    prop = Property(organization_id=org.id, name="HTTP Hotel", code="HTTP", currency="INR")
    db_session.add(prop)
    await db_session.flush()

    rt = RoomType(
        property_id=prop.id,
        name="Deluxe",
        code="DLX",
        base_occupancy=2,
        max_occupancy=2,
    )
    db_session.add(rt)
    await db_session.flush()

    rp = RatePlan(
        property_id=prop.id,
        room_type_id=rt.id,
        name="Standard",
        code="STD",
        booking_type="NIGHTLY",
        status="ACTIVE",
    )
    db_session.add(rp)
    await db_session.flush()

    aiosell_config = AiosellPropertyConfig(
        property_id=prop.id,
        aiosell_hotel_code="hotel-http-test",
        pms_slug="sample-pms",
        is_active=True,
    )
    db_session.add(aiosell_config)
    await set_room_type_mapping(db_session, prop.id, rt.id, "aiosell-dlx")
    await set_rate_plan_mapping(db_session, prop.id, rp.id, "aiosell-std")
    await db_session.commit()

    webhook_payload = {
        "action": "book",
        "hotelCode": "hotel-http-test",
        "channel": "agoda",
        "bookingId": "AGODA-5544",
        "checkin": "2026-11-15",
        "checkout": "2026-11-16",
        "guest": {
            "firstName": "Alice",
            "lastName": "Wonder",
            "email": "alice@example.com",
            "phone": "9988776655"
        },
        "amount": {
            "amountAfterTax": 3200.0,
            "amountBeforeTax": 2800.0,
            "tax": 400.0,
            "currency": "INR"
        },
        "rooms": [
            {
                "roomCode": "aiosell-dlx",
                "rateplanCode": "aiosell-std",
                "occupancy": {"adults": 1, "children": 0},
                "prices": [{"date": "2026-11-15", "sellRate": 3200.0}]
            }
        ]
    }

    from app.config import settings
    response = await async_client.post(
        "/api/v1/webhooks/aiosell/reservations",
        json=webhook_payload,
        auth=(settings.AIOSELL_WEBHOOK_USERNAME, settings.AIOSELL_WEBHOOK_PASSWORD),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

