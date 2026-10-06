import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_taxes_and_tax_groups(async_client: AsyncClient):
    # Setup Org & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Heritage Hospitality", "slug": "heritage-hosp"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Heritage Palace", "code": "HP-01"},
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 1. Create Individual Tax (CGST 6%)
    cgst_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/taxes",
        json={
            "name": "Central GST",
            "code": "CGST_6",
            "rate_type": "PERCENTAGE",
            "rate": "6.0000",
            "status": "ACTIVE",
        },
    )
    assert cgst_res.status_code == 201
    cgst_data = cgst_res.json()
    assert cgst_data["code"] == "CGST_6"
    assert len(cgst_data["rates"]) == 1
    cgst_id = cgst_data["id"]

    # 2. Create Second Individual Tax (SGST 6%)
    sgst_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/taxes",
        json={
            "name": "State GST",
            "code": "SGST_6",
            "rate_type": "PERCENTAGE",
            "rate": "6.0000",
            "status": "ACTIVE",
        },
    )
    assert sgst_res.status_code == 201
    sgst_data = sgst_res.json()
    sgst_id = sgst_data["id"]

    # 3. Update Tax (modify rate to 9%)
    update_cgst_res = await async_client.put(
        f"/api/v1/properties/{prop_id}/taxes/{cgst_id}",
        json={
            "name": "Central GST 9%",
            "rate": "9.0000",
        },
    )
    assert update_cgst_res.status_code == 200
    updated_cgst = update_cgst_res.json()
    assert updated_cgst["name"] == "Central GST 9%"
    assert float(updated_cgst["rates"][0]["rate"]) == 9.0

    # Reset back to 6%
    await async_client.put(
        f"/api/v1/properties/{prop_id}/taxes/{cgst_id}",
        json={"name": "Central GST", "rate": "6.0000"},
    )

    # 4. Create Tax Group (GST 12%)
    group_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/tax-groups",
        json={
            "name": "GST 12% - Rooms",
            "code": "GST_ROOM_12",
            "applies_to": "ROOM",
            "status": "ACTIVE",
            "items": [
                {"tax_id": cgst_id, "sequence": 1, "is_compound": False},
                {"tax_id": sgst_id, "sequence": 2, "is_compound": False},
            ],
        },
    )
    assert group_res.status_code == 201
    group_data = group_res.json()
    assert group_data["code"] == "GST_ROOM_12"
    assert len(group_data["items"]) == 2
    group_id = group_data["id"]

    # 5. Get Tax Group
    get_grp_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/tax-groups/{group_id}"
    )
    assert get_grp_res.status_code == 200
    assert get_grp_res.json()["name"] == "GST 12% - Rooms"

    # 6. Update Tax Group
    upd_grp_res = await async_client.put(
        f"/api/v1/properties/{prop_id}/tax-groups/{group_id}",
        json={"name": "GST 12% - Standard Rooms"},
    )
    assert upd_grp_res.status_code == 200
    assert upd_grp_res.json()["name"] == "GST 12% - Standard Rooms"

    # 7. Create Room Type & Rate Plan with Tax Group
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Palace Suite", "code": "PLS"},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    plan_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={
            "name": "Suite Special BAR",
            "code": "STE-BAR",
            "room_type_id": rt_id,
            "tax_group_id": group_id,
            "is_tax_inclusive": True,
            "booking_type": "NIGHTLY",
            "base_rate": {
                "duration": 1,
                "duration_unit": "NIGHT",
                "price": "5000.00",
                "min_occupancy": 1,
                "max_occupancy": 2,
            },
        },
    )
    assert plan_res.status_code == 201
    plan_data = plan_res.json()
    assert plan_data["tax_group_id"] == group_id
    assert plan_data["is_tax_inclusive"] is True
    assert len(plan_data["rates"]) == 1
    assert float(plan_data["rates"][0]["price"]) == 5000.0
    assert plan_data["tax_group"]["code"] == "GST_ROOM_12"
    assert plan_data["room_type"]["code"] == "PLS"
