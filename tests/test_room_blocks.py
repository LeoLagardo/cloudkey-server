import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_room_block_crud_and_inventory(async_client: AsyncClient):
    # 1. Setup Org & Property & Room Type
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Block Test Hotel", "slug": "block-test-hotel"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Block Resort", "code": "BLK-01"},
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Deluxe King", "code": "DLX-K"},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    # Create 2 rooms
    r1_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "101", "floor": "1", "room_type_id": rt_id, "status": "AVAILABLE"},
    )
    assert r1_res.status_code == 201
    r1_id = r1_res.json()["id"]

    r2_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "102", "floor": "1", "room_type_id": rt_id, "status": "AVAILABLE"},
    )
    assert r2_res.status_code == 201
    r2_id = r2_res.json()["id"]

    # 2. Create Room Block on Room 101
    now = datetime.now(timezone.utc)
    start_at = (now).isoformat()
    end_at = (now + timedelta(days=3)).isoformat()

    block_payload = {
        "room_id": r1_id,
        "block_type": "MAINTENANCE",
        "start_at": start_at,
        "end_at": end_at,
        "reason": "Air conditioner overhaul",
    }
    block_res = await async_client.post(
        f"/api/v1/room-blocks?property_id={prop_id}",
        json=block_payload,
    )
    assert block_res.status_code == 201
    block_data = block_res.json()
    assert block_data["room_id"] == r1_id
    assert block_data["block_type"] == "MAINTENANCE"
    assert block_data["room_number"] == "101"
    block_id = block_data["id"]

    # Room status should now be synced to MAINTENANCE
    room1_chk = await async_client.get(f"/api/v1/rooms/{r1_id}")
    assert room1_chk.status_code == 200
    assert room1_chk.json()["status"] == "MAINTENANCE"

    # 3. List room blocks
    list_res = await async_client.get(f"/api/v1/room-blocks?property_id={prop_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 4. Attempting to assign room 101 to a new reservation during block period should fail
    rate_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={
            "name": "Standard Rate",
            "code": "BAR",
            "room_type_id": rt_id,
            "booking_type": "NIGHTLY",
        },
    )
    assert rate_res.status_code == 201
    rp_id = rate_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={
            "duration": 1,
            "duration_unit": "NIGHT",
            "price": "2500.00",
        },
    )

    conflict_res = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booking_type": "NIGHTLY",
            "source": "DIRECT",
            "currency": "INR",
            "booker": {"first_name": "John", "last_name": "Doe"},
            "rooms": [
                {
                    "room_type_id": rt_id,
                    "room_id": r1_id,
                    "rate_plan_id": rp_id,
                    "check_in_at": start_at,
                    "check_out_at": (now + timedelta(days=2)).isoformat(),
                    "adults": 1,
                }
            ],
        },
    )
    assert conflict_res.status_code == 422, conflict_res.text
    assert "blocked" in conflict_res.json()["detail"].lower()

    # 5. Delete Room Block (Unblock)
    del_res = await async_client.delete(f"/api/v1/room-blocks/{block_id}")
    assert del_res.status_code == 200

    # Room status should revert to AVAILABLE
    room1_revert = await async_client.get(f"/api/v1/rooms/{r1_id}")
    assert room1_revert.status_code == 200
    assert room1_revert.json()["status"] == "AVAILABLE"
