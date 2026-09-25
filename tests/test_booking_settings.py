import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_booking_settings(async_client: AsyncClient):
    # Setup Org & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Pacific Hotels", "slug": "pacific-hotels"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Pacific Bay Hotel", "code": "PBH-01"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    # 1. Get default booking settings automatically created with property
    get_res = await async_client.get(f"/api/v1/booking-settings/{prop_id}")
    assert get_res.status_code == 200
    settings = get_res.json()
    assert settings["property_id"] == prop_id
    assert settings["nightly_booking_enabled"] is True
    assert settings["hourly_booking_enabled"] is False
    assert settings["check_in_time"].startswith("14:00")
    assert settings["check_out_time"].startswith("11:00")

    # 2. Update booking settings
    update_res = await async_client.put(
        f"/api/v1/booking-settings/{prop_id}",
        json={
            "hourly_booking_enabled": True,
            "minimum_hourly_duration": 2,
            "maximum_hourly_duration": 12,
            "check_in_time": "15:00:00",
            "check_out_time": "10:00:00",
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["hourly_booking_enabled"] is True
    assert updated["minimum_hourly_duration"] == 2
    assert updated["maximum_hourly_duration"] == 12
    assert updated["check_in_time"].startswith("15:00")
    assert updated["check_out_time"].startswith("10:00")
