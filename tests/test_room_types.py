import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_room_types_crud(async_client: AsyncClient):
    # Setup Org & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Alps Resorts", "slug": "alps-resorts"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Alpine Lodge", "code": "AL-01"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    # 1. Create Room Type
    rt_payload = {
        "name": "Deluxe Chalet Suite",
        "code": "DCS",
        "base_occupancy": 2,
        "max_occupancy": 4,
        "description": "Spacious chalet with mountain view",
        "status": "ACTIVE",
    }
    create_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json=rt_payload,
    )
    assert create_res.status_code == 201
    rt_data = create_res.json()
    assert rt_data["code"] == "DCS"
    assert rt_data["base_occupancy"] == 2
    assert rt_data["max_occupancy"] == 4
    rt_id = rt_data["id"]

    # 2. List Room Types
    list_res = await async_client.get(f"/api/v1/room-types?property_id={prop_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 3. Update Room Type
    update_res = await async_client.put(
        f"/api/v1/room-types/{rt_id}",
        json={"max_occupancy": 5},
    )
    assert update_res.status_code == 200
    assert update_res.json()["max_occupancy"] == 5
