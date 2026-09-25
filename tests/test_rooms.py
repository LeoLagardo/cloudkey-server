import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rooms_crud(async_client: AsyncClient):
    # Setup Org, Property & Room Type
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Urban Stays", "slug": "urban-stays"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "City Center Hotel", "code": "CCH-01"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Standard Single", "code": "STD-S"},
    )
    rt_id = rt_res.json()["id"]

    # 1. Create Room
    room_payload = {
        "room_number": "301",
        "floor": "3",
        "room_type_id": rt_id,
        "status": "AVAILABLE",
    }
    create_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json=room_payload,
    )
    assert create_res.status_code == 201
    room_data = create_res.json()
    assert room_data["room_number"] == "301"
    assert room_data["status"] == "AVAILABLE"
    room_id = room_data["id"]

    # 2. Duplicate room number test
    dup_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json=room_payload,
    )
    assert dup_res.status_code == 409

    # 3. Update room status to MAINTENANCE (valid check constraint value)
    up_res = await async_client.put(
        f"/api/v1/rooms/{room_id}",
        json={"status": "MAINTENANCE"},
    )
    assert up_res.status_code == 200
    assert up_res.json()["status"] == "MAINTENANCE"
