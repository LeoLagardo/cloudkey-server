import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_property_setup_wizard_flow(async_client: AsyncClient):
    # =========================================================================
    # 0. Initial Signup & Property Provisioning
    # =========================================================================
    signup_payload = {
        "account": {
            "email": "resort.manager@cloudkey.com",
            "password": "ManagerPassword123!",
            "full_name": "Maya Lin",
        },
        "organization": {
            "name": "Azure Coast Hospitality",
            "slug": "azure-coast",
        },
        "property": {
            "name": "Azure Bay Resort",
            "code": "ABR-01",
            "city": "Goa",
            "currency": "INR",
        },
    }
    signup_res = await async_client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup_res.status_code == 201
    auth_data = signup_res.json()
    token = auth_data["access_token"]
    prop_id = auth_data["property"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # =========================================================================
    # 1. Inspect Initial Setup Status
    # =========================================================================
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["property_id"] == prop_id
    assert status_data["is_setup_completed"] is False
    assert status_data["current_step"] == "ROOM_TYPES"
    assert status_data["steps"]["property_details"]["is_completed"] is True
    prop_details = status_data["steps"]["property_details"]["details"]
    assert prop_details["timezone"] is not None
    assert prop_details["currency"] is not None
    assert prop_details["classification"] is not None
    assert "address_line_1" in prop_details
    assert "state" in prop_details
    assert "business_date" in prop_details
    assert status_data["steps"]["room_types"]["is_completed"] is False
    assert status_data["steps"]["rooms"]["is_completed"] is False
    assert status_data["steps"]["rate_plans"]["is_completed"] is False

    # Premature completion attempt should fail with 422
    premature_complete = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/complete",
        headers=headers,
    )
    assert premature_complete.status_code == 422
    assert "Room Type" in premature_complete.json()["detail"]

    # =========================================================================
    # 2. Step 1: Setup Room Types
    # =========================================================================
    room_types_payload = {
        "room_types": [
            {
                "name": "Deluxe Sea View",
                "code": "DSV",
                "base_occupancy": 2,
                "max_occupancy": 3,
                "extra_beds": 1,
            },
            {
                "name": "Presidential Beach Villa",
                "code": "PBV",
                "base_occupancy": 4,
                "max_occupancy": 6,
                "extra_beds": 2,
            },
        ]
    }
    rt_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/room-types",
        json=room_types_payload,
        headers=headers,
    )
    assert rt_res.status_code == 201
    created_rts = rt_res.json()
    assert len(created_rts) == 2
    rt1_id = created_rts[0]["id"]
    rt2_id = created_rts[1]["id"]

    # Verify status advanced to ROOMS
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["current_step"] == "ROOMS"
    assert status_res.json()["steps"]["room_types"]["is_completed"] is True
    assert status_res.json()["steps"]["room_types"]["count"] == 2

    # =========================================================================
    # 3. Step 2: Setup Rooms (Individual + Bulk Range Generation)
    # =========================================================================
    rooms_payload = {
        "rooms": [
            {"room_number": "101", "room_type_id": rt1_id, "floor": "1"},
        ],
        "bulk_groups": [
            {
                "room_type_id": rt1_id,
                "prefix": "10",
                "start_number": 2,
                "count": 3,  # Generates 102, 103, 104
                "floor": "1",
            },
            {
                "room_type_id": rt2_id,
                "room_numbers": ["VILLA-01", "VILLA-02"],
                "floor": "Ground",
            },
        ],
    }
    rooms_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/rooms",
        json=rooms_payload,
        headers=headers,
    )
    assert rooms_res.status_code == 201
    created_rooms = rooms_res.json()
    # 1 individual + 3 bulk + 2 list = 6 rooms
    assert len(created_rooms) == 6

    # Verify status advanced to RATE_PLANS
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["current_step"] == "RATE_PLANS"
    assert status_res.json()["steps"]["rooms"]["is_completed"] is True
    assert status_res.json()["steps"]["rooms"]["count"] == 6

    # =========================================================================
    # 4. Step 3: Setup Rate Plans & Pricing
    # =========================================================================
    rate_plans_payload = {
        "rate_plans": [
            {
                "name": "Best Available Rate",
                "booking_type": "NIGHTLY",
                "description": "Standard flexible rate with breakfast",
                "meal_plan": "Bed & Breakfast",
                "rates": [
                    {
                        "room_type_id": rt1_id,
                        "base_rate": 6500.0,
                        "occupancy": 2,
                        "extra_adult_rate": 1500.0,
                    },
                    {
                        "room_type_id": rt2_id,
                        "base_rate": 22000.0,
                        "occupancy": 4,
                        "extra_adult_rate": 3000.0,
                    },
                ],
            },
            {
                "name": "Non-Refundable Promo",
                "booking_type": "NIGHTLY",
                "cancellation_policy": "Non-refundable, full charge on booking",
                "rates": [
                    {
                        "room_type_id": rt1_id,
                        "base_rate": 5500.0,
                        "occupancy": 2,
                    },
                ],
            },
        ]
    }
    rp_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/rate-plans",
        json=rate_plans_payload,
        headers=headers,
    )
    assert rp_res.status_code == 201
    created_plans = rp_res.json()
    assert len(created_plans) == 3

    # Verify status advanced to BOOKING_SETTINGS (or SETUP_COMPLETE since default settings exist)
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["steps"]["rate_plans"]["is_completed"] is True
    assert status_res.json()["steps"]["rate_plans"]["count"] == 3

    # =========================================================================
    # 5. Step 4: Configure Taxes & Tax Groups
    # =========================================================================
    taxes_payload = {
        "taxes": [
            {"name": "Central GST", "code": "CGST", "rate": 6.0, "rate_type": "PERCENTAGE"},
            {"name": "State GST", "code": "SGST", "rate": 6.0, "rate_type": "PERCENTAGE"},
        ],
        "tax_groups": [
            {
                "name": "GST - Room 12%",
                "code": "GST_ROOM_12",
                "applies_to": "ROOM",
                "tax_codes": ["CGST", "SGST"],
                "is_compound": False,
            }
        ],
        "apply_to_rate_plans": True,
        "is_tax_inclusive": False,
    }
    tax_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/taxes",
        json=taxes_payload,
        headers=headers,
    )
    assert tax_res.status_code == 201
    created_tax_groups = tax_res.json()
    assert len(created_tax_groups) == 1
    assert created_tax_groups[0]["code"] == "GST_ROOM_12"

    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["steps"]["taxes"]["is_completed"] is True
    assert status_res.json()["steps"]["taxes"]["count"] == 1

    # =========================================================================
    # 6. Step 5: Configure Property Booking Settings
    # =========================================================================
    booking_payload = {
        "nightly_booking_enabled": True,
        "hourly_booking_enabled": True,
        "minimum_hourly_duration": 2,
        "maximum_hourly_duration": 8,
        "check_in_time": "15:00:00",
        "check_out_time": "11:00:00",
        "same_day_booking_enabled": True,
    }
    settings_res = await async_client.put(
        f"/api/v1/properties/{prop_id}/setup/booking-settings",
        json=booking_payload,
        headers=headers,
    )
    assert settings_res.status_code == 200
    updated_settings = settings_res.json()
    assert updated_settings["check_in_time"] == "15:00:00"
    assert updated_settings["hourly_booking_enabled"] is True

    # Verify status advanced to SETUP_COMPLETE
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["current_step"] == "SETUP_COMPLETE"

    # =========================================================================
    # 7. Step 6: Finalize Setup
    # =========================================================================
    complete_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/complete",
        headers=headers,
    )
    assert complete_res.status_code == 200
    complete_data = complete_res.json()
    assert complete_data["is_setup_completed"] is True
    assert complete_data["current_step"] == "COMPLETED"
    assert complete_data["summary"]["rooms_count"] == 6
    assert complete_data["summary"]["room_types_count"] == 2
    assert complete_data["summary"]["tax_groups_count"] == 1

    # Status is now COMPLETED
    status_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/setup/status",
        headers=headers,
    )
    assert status_res.json()["current_step"] == "COMPLETED"
    assert status_res.json()["is_setup_completed"] is True

    # =========================================================================
    # 8. PMS Dashboard View
    # =========================================================================
    dashboard_res = await async_client.get(
        f"/api/v1/properties/{prop_id}/dashboard",
        headers=headers,
    )
    assert dashboard_res.status_code == 200
    dashboard = dashboard_res.json()

    assert dashboard["property"]["id"] == prop_id
    assert dashboard["property"]["is_setup_completed"] is True

    # Check metrics
    metrics = dashboard["metrics"]
    assert metrics["total_rooms"] == 6
    assert metrics["available_rooms"] == 6
    assert metrics["total_room_types"] == 2
    assert metrics["active_rate_plans"] == 3
    assert metrics["total_tax_groups"] == 1

    # Check policies
    policies = dashboard["policies"]
    assert policies["check_in_time"] == "15:00:00"
    assert policies["hourly_booking_enabled"] is True

    # Check readiness
    readiness = dashboard["readiness"]
    assert readiness["setup_completed"] is True
    assert readiness["is_operational"] is True
    assert readiness["inventory_ready"] is True
    assert readiness["pricing_ready"] is True
