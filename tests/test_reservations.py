import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folio import FolioTransaction, PaymentMethod
from app.models.operation import AuditLog


@pytest.mark.asyncio
async def test_create_reservation_full_flow(async_client: AsyncClient, db_session: AsyncSession):
    # 1. Setup Organization & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Grand Hospitality", "slug": "grand-hospitality"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Grand Palace Hotel", "code": "GPH"},
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 2. Setup Room Type & Rate Plan & Rate
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Deluxe Room", "code": "DLX", "base_occupancy": 2, "max_occupancy": 3},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={
            "name": "Standard EP",
            "code": "EP",
            "room_type_id": rt_id,
            "booking_type": "NIGHTLY",
        },
    )
    assert rp_res.status_code == 201
    rp_id = rp_res.json()["id"]

    # Add Rate
    rate_res = await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={
            "duration": 1,
            "duration_unit": "NIGHT",
            "price": "2500.00",
        },
    )
    assert rate_res.status_code == 201

    # Create physical room for the room type
    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "101", "room_type_id": rt_id},
    )
    assert room_res.status_code == 201

    # 3. Create a Payment Method in the database
    pm = PaymentMethod(
        property_id=prop_id,
        name="Cash Desk",
        code="CASH_DESK",
        method_type="CASH",
    )
    db_session.add(pm)
    await db_session.commit()
    payment_method_id = pm.id

    # 4. Prepare Reservation Payload
    now = datetime.now(timezone.utc)
    check_in = now + timedelta(days=1)
    check_out = now + timedelta(days=3)  # 2 nights

    payload = {
        "booking_type": "NIGHTLY",
        "source": "DIRECT",
        "currency": "INR",
        "special_requests": "High floor room preferred",
        "booker": {
            "first_name": "Alexander",
            "last_name": "Pierce",
            "email": "alex.pierce@example.com",
            "phone": "+919876543210",
        },
        "rooms": [
            {
                "room_type_id": rt_id,
                "rate_plan_id": rp_id,
                "room_id": None,  # Stays NULL until check-in
                "check_in_at": check_in.isoformat(),
                "check_out_at": check_out.isoformat(),
                "adults": 2,
                "children": 0,
            }
        ],
        "advance_payment": {
            "payment_method_id": payment_method_id,
            "amount": "1500.00",
            "notes": "Advance deposit at front desk",
        },
    }

    # 5. Execute Create Reservation
    create_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=payload,
    )
    assert create_res.status_code == 201, create_res.text
    data = create_res.json()

    # 6. Verify Assertions
    # Booking number prefix should start with hotel code "GPH"
    assert data["booking_number"].startswith("GPH-")
    assert data["status"] == "CONFIRMED"
    assert Decimal(str(data["total_amount"])) == Decimal("5000.00")  # 2 nights x 2500

    # Booker
    assert data["booker"]["first_name"] == "Alexander"
    assert data["booker"]["phone"] == "+919876543210"

    # Rooms
    assert len(data["rooms"]) == 1
    room = data["rooms"][0]
    assert room["room_id"] is None  # Unassigned room kept NULL
    assert len(room["room_rates"]) == 2  # 2 nights snapshot
    assert Decimal(str(room["room_rates"][0]["base_amount"])) == Decimal("2500.00")

    # Folio
    assert data["folio"] is not None
    assert data["folio"]["status"] == "OPEN"
    assert data["folio"]["folio_number"].startswith("FOL-GPH-")

    # Payment
    assert len(data["payments"]) == 1
    assert Decimal(str(data["payments"][0]["amount"])) == Decimal("1500.00")

    # 7. Check database for FolioTransaction CREDIT & AuditLog
    # Folio transaction CREDIT
    txn_result = await db_session.execute(
        select(FolioTransaction).where(FolioTransaction.folio_id == data["folio"]["id"])
    )
    txns = list(txn_result.scalars().all())
    assert len(txns) == 1
    assert txns[0].entry_type == "CREDIT"
    assert txns[0].transaction_type == "PAYMENT"
    assert txns[0].amount == Decimal("1500.00")

    # Audit Log
    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "reservations",
            AuditLog.entity_id == data["id"],
        )
    )
    logs = list(audit_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].action == "CREATE"
    assert logs[0].new_values["booking_number"] == data["booking_number"]


@pytest.mark.asyncio
async def test_create_reservation_without_advance_payment(async_client: AsyncClient):
    # Setup Org & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Sea Breeze Stays", "slug": "sea-breeze"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Sea Breeze Resort", "code": "SBR"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Ocean Suite", "code": "OS"},
    )
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Bar Rate", "code": "BAR", "room_type_id": rt_id},
    )
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "4000.00"},
    )

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "201", "room_type_id": rt_id},
    )
    assert room_res.status_code == 201

    now = datetime.now(timezone.utc)
    check_in = now + timedelta(days=2)
    check_out = now + timedelta(days=3)  # 1 night

    payload = {
        "booking_type": "NIGHTLY",
        "booker": {
            "first_name": "Eleanor",
            "last_name": "Vance",
            "email": "eleanor@example.com",
        },
        "rooms": [
            {
                "room_type_id": rt_id,
                "rate_plan_id": rp_id,
                "check_in_at": check_in.isoformat(),
                "check_out_at": check_out.isoformat(),
            }
        ],
    }

    create_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=payload,
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["booking_number"].startswith("SBR-")
    assert len(data["payments"]) == 0
    assert data["folio"]["status"] == "OPEN"
    assert Decimal(str(data["total_amount"])) == Decimal("4000.00")


@pytest.mark.asyncio
async def test_checkin_checkout_and_same_day_flow(async_client: AsyncClient, db_session: AsyncSession):
    # 1. Setup Property, Room Type, Rate Plan & Room
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Palm Grove Hospitality", "slug": "palm-grove"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Palm Grove Hotel", "code": "PGH"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    # Set same_day_checkout_rule in property settings
    await async_client.put(
        f"/api/v1/properties/{prop_id}/settings",
        json={"same_day_checkout_rule": "FULL_NIGHT"},
    )

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Deluxe Palm Room", "code": "DPR"},
    )
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Standard Rate", "code": "STD", "room_type_id": rt_id},
    )
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "3000.00"},
    )

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "101", "room_type_id": rt_id},
    )
    room_id = room_res.json()["id"]

    # 2. Create a 3-night reservation
    now = datetime.now(timezone.utc)
    check_in = now + timedelta(days=1)
    check_out = now + timedelta(days=4)

    booking_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booking_type": "NIGHTLY",
            "booker": {
                "first_name": "Maya",
                "last_name": "Lin",
                "email": "maya@example.com",
            },
            "rooms": [
                {
                    "room_type_id": rt_id,
                    "rate_plan_id": rp_id,
                    "check_in_at": check_in.isoformat(),
                    "check_out_at": check_out.isoformat(),
                }
            ],
        },
    )
    assert booking_res.status_code == 201
    res_data = booking_res.json()
    res_id = res_data["id"]

    # 3. Check-In: attempt early check-in without override -> rejected with 422
    early_fail = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-in?property_id={prop_id}",
        json={"room_id": room_id, "allow_early_checkin": False},
    )
    assert early_fail.status_code == 422
    assert "Early arrival" in early_fail.text

    # 4. Check-In with allow_early_checkin=True -> succeeds
    check_in_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-in?property_id={prop_id}",
        json={"room_id": room_id, "keycards_issued": 2, "allow_early_checkin": True},
    )
    assert check_in_res.status_code == 200
    ci_data = check_in_res.json()
    assert ci_data["status"] == "CHECKED_IN"
    assert ci_data["rooms"][0]["room_id"] == room_id

    # Verify physical room is now OCCUPIED
    room_get = await async_client.get(f"/api/v1/rooms/{room_id}?property_id={prop_id}")
    assert room_get.json()["occupancy_status"] == "OCCUPIED"

    # 5. Test Undo Check-In: reverts back to CONFIRMED and frees physical room
    undo_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/undo-check-in?property_id={prop_id}"
    )
    assert undo_res.status_code == 200
    assert undo_res.json()["status"] == "CONFIRMED"
    room_after_undo = await async_client.get(f"/api/v1/rooms/{room_id}?property_id={prop_id}")
    assert room_after_undo.json()["occupancy_status"] == "VACANT"

    # 6. Re-check in to test checkout flow
    await async_client.post(
        f"/api/v1/reservations/{res_id}/check-in?property_id={prop_id}",
        json={"room_id": room_id, "allow_early_checkin": True},
    )

    # 4. Attempt Check-Out without settling balance or override -> rejected with 422
    unpaid_co_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-out?property_id={prop_id}",
        json={"allow_unpaid_override": False},
    )
    assert unpaid_co_res.status_code == 422
    assert "outstanding balance" in unpaid_co_res.text

    # 5. Check-Out with settlement payment & same-day/early departure
    co_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-out?property_id={prop_id}",
        json={
            "settlement_payment": {
                "payment_method": "CASH",
                "amount": "9000.00",
                "reference": "REC-9988",
            }
        },
    )
    assert co_res.status_code == 200
    co_data = co_res.json()
    assert co_data["status"] == "CHECKED_OUT"
    assert co_data["folio"]["status"] == "CLOSED"

    # Verify physical room transitioned to VACANT and DIRTY
    room_after = await async_client.get(f"/api/v1/rooms/{room_id}?property_id={prop_id}")
    assert room_after.json()["occupancy_status"] == "VACANT"
    assert room_after.json()["housekeeping_status"] == "DIRTY"

