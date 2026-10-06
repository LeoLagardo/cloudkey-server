import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_endpoint(async_client: AsyncClient):
    # 1. Create Organization
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Dashboard Group", "slug": "dashboard-group"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    # 2. Create Property
    prop_res = await async_client.post(
        "/api/v1/properties",
        json={
            "name": "Dashboard Palms",
            "code": "DBP-01",
            "city": "Bengaluru",
            "currency": "INR",
            "timezone": "Asia/Kolkata",
            "status": "ACTIVE",
        },
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 3. Create Room Type & Rooms
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={
            "name": "Deluxe View",
            "code": "DLX",
            "base_occupancy": 2,
            "max_occupancy": 3,
        },
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={
            "room_type_id": rt_id,
            "room_number": "101",
            "floor": "1",
            "status": "AVAILABLE",
        },
    )
    assert room_res.status_code == 201

    # 4. Call Dashboard Summary API
    dash_res = await async_client.get(f"/api/v1/dashboard?property_id={prop_id}")
    assert dash_res.status_code == 200
    data = dash_res.json()

    # Validate structure
    assert data["property"]["id"] == prop_id
    assert data["property"]["name"] == "Dashboard Palms"
    assert data["property"]["currency"] == "INR"
    assert "kpis" in data
    assert data["kpis"]["total_rooms_count"] == 1
    assert data["kpis"]["available_rooms_count"] == 1
    assert len(data["tape_rooms"]) == 1
    assert data["tape_rooms"][0]["number"] == "101"
    assert data["tape_rooms"][0]["dot_color"] == "ready"
    assert "occupancy_trend" in data
    assert len(data["occupancy_trend"]) == 7
