import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_inventory_lifecycle_and_triggers(async_client: AsyncClient, db_session: AsyncSession):
    # 1. Setup Organization & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Inventory Test Org", "slug": "inv-test-org"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Inventory Grand Hotel", "code": "IGH"},
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 2. Setup Room Type -> Trigger 1: rolling window generated
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Executive Suite", "code": "EXEC", "base_occupancy": 2, "max_occupancy": 4},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    # Rate plan setup
    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Standard Rate", "code": "STD", "room_type_id": rt_id},
    )
    assert rp_res.status_code == 201
    rp_id = rp_res.json()["id"]

    rate_res = await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "5000.00"},
    )
    assert rate_res.status_code == 201

    # Add 2 physical rooms -> Trigger 2: total_rooms recomputed
    r1 = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "301", "room_type_id": rt_id},
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "302", "room_type_id": rt_id},
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]

    # Verify inventory grid: total_rooms should now be 2, sold_rooms=0, blocked_rooms=0, available=2
    now = datetime.now(timezone.utc)
    d1 = (now + timedelta(days=5)).date()
    d2 = (now + timedelta(days=6)).date()

    grid_res = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d1.isoformat()}&end_date={d2.isoformat()}&room_type_id={rt_id}"
    )
    assert grid_res.status_code == 200
    grid = grid_res.json()
    assert len(grid) == 2
    assert grid[0]["total_rooms"] == 2
    assert grid[0]["blocked_rooms"] == 0
    assert grid[0]["sold_rooms"] == 0
    assert grid[0]["available"] == 2

    # 3. Trigger 3: Room block insert -> recompute blocked_rooms
    block_start = datetime.combine(d1, datetime.min.time(), tzinfo=timezone.utc)
    block_end = datetime.combine(d2, datetime.min.time(), tzinfo=timezone.utc)
    block_res = await async_client.post(
        f"/api/v1/room-blocks?property_id={prop_id}",
        json={
            "room_id": r1_id,
            "block_type": "OUT_OF_ORDER",
            "start_at": block_start.isoformat(),
            "end_at": block_end.isoformat(),
            "reason": "AC leak repair",
        },
    )
    assert block_res.status_code == 201
    block_id = block_res.json()["id"]

    # Verify inventory blocked_rooms for d1 is now 1, available is 2 - 1 - 0 = 1
    grid_res2 = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d1.isoformat()}&end_date={d1.isoformat()}&room_type_id={rt_id}"
    )
    assert grid_res2.status_code == 200
    row_d1 = grid_res2.json()[0]
    assert row_d1["blocked_rooms"] == 1
    assert row_d1["available"] == 1

    # 4. Trigger 4: Booking created -> locks row, checks available >= 1, increments sold_rooms
    check_in_dt = datetime.combine(d1, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
    check_out_dt = datetime.combine(d2, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=11)

    booking_payload = {
        "booking_type": "NIGHTLY",
        "booker": {
            "first_name": "James",
            "last_name": "Bond",
            "email": "007@mi6.gov.uk",
        },
        "rooms": [
            {
                "room_type_id": rt_id,
                "rate_plan_id": rp_id,
                "check_in_at": check_in_dt.isoformat(),
                "check_out_at": check_out_dt.isoformat(),
            }
        ],
    }

    res_1 = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=booking_payload,
    )
    assert res_1.status_code == 201
    res_1_id = res_1.json()["id"]

    # Verify inventory row: sold_rooms=1, available=0 (total 2 - blocked 1 - sold 1 = 0)
    grid_res3 = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d1.isoformat()}&end_date={d1.isoformat()}&room_type_id={rt_id}"
    )
    row_d1_after = grid_res3.json()[0]
    assert row_d1_after["sold_rooms"] == 1
    assert row_d1_after["available"] == 0

    # 5. Overbooking prevention: Attempt to create another reservation when available is 0 -> Rejected!
    res_2 = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=booking_payload,
    )
    assert res_2.status_code == 422
    assert "Insufficient inventory" in res_2.text

    # 6. Trigger 5: Check-in & Check-out -> No change to sold_rooms
    checkin_res = await async_client.post(
        f"/api/v1/reservations/{res_1_id}/check-in?property_id={prop_id}"
    )
    assert checkin_res.status_code == 200
    assert checkin_res.json()["status"] == "CHECKED_IN"

    grid_res4 = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d1.isoformat()}&end_date={d1.isoformat()}&room_type_id={rt_id}"
    )
    assert grid_res4.json()[0]["sold_rooms"] == 1  # Unchanged!

    # 7. Channel / Yield Restrictions Update (Stop Sell, CTA, CTD, Overbooking Limit)
    d3 = (now + timedelta(days=10)).date()
    controls_res = await async_client.patch(
        f"/api/v1/inventory/controls?property_id={prop_id}",
        json={
            "room_type_ids": [rt_id],
            "start_date": d3.isoformat(),
            "end_date": d3.isoformat(),
            "stop_sell": True,
            "min_stay": 3,
            "overbooking_limit": 5,
        },
    )
    assert controls_res.status_code == 200

    grid_d3 = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d3.isoformat()}&end_date={d3.isoformat()}&room_type_id={rt_id}"
    )
    d3_row = grid_d3.json()[0]
    assert d3_row["stop_sell"] is True
    assert d3_row["min_stay"] == 3
    assert d3_row["overbooking_limit"] == 5
    # available = 2 - 0 - 0 + 5 = 7
    assert d3_row["available"] == 7

    # Booking on Stop Sell date -> Rejected!
    d3_in = datetime.combine(d3, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
    d3_out = datetime.combine(d3 + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=11)
    d3_booking = {
        "booking_type": "NIGHTLY",
        "booker": {"first_name": "Test", "email": "test@stop.com"},
        "rooms": [{
            "room_type_id": rt_id,
            "rate_plan_id": rp_id,
            "check_in_at": d3_in.isoformat(),
            "check_out_at": d3_out.isoformat(),
        }],
    }
    stop_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=d3_booking,
    )
    assert stop_res.status_code == 422
    assert "Stop Sell is active" in stop_res.text

    # 8. Trigger 6: Cancellation -> Decrements sold_rooms
    # First create a future booking
    d4 = (now + timedelta(days=15)).date()
    d4_in = datetime.combine(d4, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
    d4_out = datetime.combine(d4 + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=11)
    future_booking = {
        "booking_type": "NIGHTLY",
        "booker": {"first_name": "Future", "email": "future@test.com"},
        "rooms": [{
            "room_type_id": rt_id,
            "rate_plan_id": rp_id,
            "check_in_at": d4_in.isoformat(),
            "check_out_at": d4_out.isoformat(),
        }],
    }
    future_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json=future_booking,
    )
    assert future_res.status_code == 201
    future_id = future_res.json()["id"]

    # Check sold_rooms is 1
    d4_grid_before = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d4.isoformat()}&end_date={d4.isoformat()}&room_type_id={rt_id}"
    )
    assert d4_grid_before.json()[0]["sold_rooms"] == 1

    # Cancel reservation
    cancel_res = await async_client.post(
        f"/api/v1/reservations/{future_id}/cancel?property_id={prop_id}&reason=Plans+changed"
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Check sold_rooms is restored to 0
    d4_grid_after = await async_client.get(
        f"/api/v1/inventory?property_id={prop_id}&start_date={d4.isoformat()}&end_date={d4.isoformat()}&room_type_id={rt_id}"
    )
    assert d4_grid_after.json()[0]["sold_rooms"] == 0
    assert d4_grid_after.json()[0]["available"] == 2
