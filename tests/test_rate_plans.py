import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rate_plans_and_rates(async_client: AsyncClient):
    # Setup Org, Property & Room Type
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Boutique Group", "slug": "boutique-group"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Boutique Inn", "code": "BI-01"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Deluxe Room", "code": "DLR"},
    )
    rt_id = rt_res.json()["id"]

    # 1. Create Rate Plan (room_type_id required)
    plan_payload = {
        "name": "Best Available Rate",
        "code": "BAR",
        "room_type_id": rt_id,
        "booking_type": "NIGHTLY",
        "currency": "INR",
        "status": "ACTIVE",
    }
    plan_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json=plan_payload,
    )
    assert plan_res.status_code == 201
    plan_data = plan_res.json()
    assert plan_data["code"] == "BAR"
    assert plan_data["room_type_id"] == rt_id
    plan_id = plan_data["id"]

    # 2. Add Rate to Plan (duration, duration_unit, price, valid_from/to)
    rate_payload = {
        "duration": 1,
        "duration_unit": "NIGHT",
        "price": "3500.00",
        "min_occupancy": 1,
        "max_occupancy": 2,
        "valid_from": "2026-10-01",
        "valid_to": "2026-10-31",
    }
    add_rate_res = await async_client.post(
        f"/api/v1/rate-plans/{plan_id}/rates",
        json=rate_payload,
    )
    assert add_rate_res.status_code == 201
    rate_data = add_rate_res.json()
    assert rate_data["duration"] == 1
    assert rate_data["duration_unit"] == "NIGHT"
    rate_id = rate_data["id"]

    # 3. List Rates
    list_rates_res = await async_client.get(f"/api/v1/rate-plans/{plan_id}/rates")
    assert list_rates_res.status_code == 200
    assert len(list_rates_res.json()) == 1

    # 4. Delete Rate
    del_rate_res = await async_client.delete(f"/api/v1/rate-plans/{plan_id}/rates/{rate_id}")
    assert del_rate_res.status_code == 200
