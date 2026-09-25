import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_properties(async_client: AsyncClient):
    # 1. Create Organization
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Seaside Group", "slug": "seaside-group"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    # 2. Create Property with X-Organization-ID header
    prop_payload = {
        "name": "Seaside Haven Resort",
        "code": "SHR-01",
        "address_line_1": "100 Beach Blvd",
        "city": "Goa",
        "state": "Goa",
        "country": "India",
        "postal_code": "403001",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
        "status": "ACTIVE",
    }
    prop_res = await async_client.post(
        "/api/v1/properties",
        json=prop_payload,
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_data = prop_res.json()
    assert prop_data["name"] == prop_payload["name"]
    assert prop_data["organization_id"] == org_id
    assert prop_data["currency"] == "INR"
    assert prop_data["timezone"] == "Asia/Kolkata"
    prop_id = prop_data["id"]

    # 3. List Properties for this organization
    list_res = await async_client.get(
        "/api/v1/properties",
        headers={"X-Organization-ID": org_id},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 4. Get Property by ID
    get_res = await async_client.get(f"/api/v1/properties/{prop_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == prop_id

    # 5. Get Property Settings
    settings_res = await async_client.get(f"/api/v1/properties/{prop_id}/settings")
    assert settings_res.status_code == 200
    settings_data = settings_res.json()
    assert settings_data["property_id"] == prop_id
    assert settings_data["date_format"] == "DD/MM/YYYY"
    assert settings_data["time_format"] == "24H"
    assert settings_data["language"] == "en"
    assert settings_data["number_format"] == "en-IN"
    assert settings_data["week_start_day"] == 1
    assert settings_data["night_audit_time"] == "02:00:00"
    assert settings_data["same_day_checkout_rule"] == "FULL_NIGHT"

    # 6. Update Property Settings
    update_res = await async_client.put(
        f"/api/v1/properties/{prop_id}/settings",
        json={
            "date_format": "YYYY-MM-DD",
            "time_format": "12H",
            "language": "es",
            "number_format": "en-US",
            "week_start_day": 0,
            "night_audit_time": "03:30:00",
            "same_day_checkout_rule": "DAY_USE",
            "invoice_prefix": "INV-HOTEL-",
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["date_format"] == "YYYY-MM-DD"
    assert updated_data["time_format"] == "12H"
    assert updated_data["language"] == "es"
    assert updated_data["number_format"] == "en-US"
    assert updated_data["week_start_day"] == 0
    assert updated_data["night_audit_time"] == "03:30:00"
    assert updated_data["same_day_checkout_rule"] == "DAY_USE"
    assert updated_data["invoice_prefix"] == "INV-HOTEL-"
