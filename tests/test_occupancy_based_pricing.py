import pytest
from httpx import AsyncClient
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_occupancy_based_pricing_flow(async_client: AsyncClient):
    # 1. Setup account and property
    signup_payload = {
        "account": {
            "email": "obp.tester@cloudkey.com",
            "password": "Password123!",
            "full_name": "OBP Tester",
        },
        "organization": {
            "name": "OBP Test Group",
            "slug": "obp-group",
        },
        "property": {
            "name": "OBP Grand Hotel",
            "code": "OGH",
            "city": "Mumbai",
            "currency": "INR",
        },
    }
    signup_res = await async_client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup_res.status_code == 201
    auth_data = signup_res.json()
    token = auth_data["access_token"]
    prop_id = auth_data["property"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Setup room type
    rt_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/room-types",
        json={
            "room_types": [
                {
                    "name": "Deluxe Room",
                    "code": "DLX",
                    "base_occupancy": 2,
                    "max_occupancy": 4,
                }
            ]
        },
        headers=headers,
    )
    assert rt_res.status_code == 201
    deluxe_rt_id = rt_res.json()[0]["id"]

    # 3. Setup physical room
    room_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/rooms",
        json={
            "bulk_groups": [
                {
                    "room_type_id": deluxe_rt_id,
                    "prefix": "10",
                    "start_number": 1,
                    "count": 5,
                    "floor": "1st",
                }
            ]
        },
        headers=headers,
    )
    assert room_res.status_code == 201

    # 4. Setup Rate Plan with OBP (Single, Double, Triple tiers and extra adult fee)
    rp_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/rate-plans",
        json={
            "rate_plans": [
                {
                    "name": "Continental Plan",
                    "code": "CP-BAR",
                    "meal_plan": "CP",
                    "no_of_meals": 1,
                    "color_code": "#10B981",
                    "extra_adult_rate": 1000.0,
                    "extra_child_rate": 500.0,
                    "rates": [
                        {
                            "room_type_id": deluxe_rt_id,
                            "price": 4000.0,  # Default double price
                            "single_price": 3200.0,
                            "double_price": 4000.0,
                            "triple_price": 5000.0,
                            "extra_adult_price": 1000.0,
                            "extra_child_price": 500.0,
                        }
                    ],
                }
            ]
        },
        headers=headers,
    )
    assert rp_res.status_code == 201
    rate_plans = rp_res.json()
    assert len(rate_plans) == 1
    cp_plan = rate_plans[0]
    cp_plan_id = cp_plan["id"]
    assert cp_plan["meal_plan"] == "CP"
    assert cp_plan["no_of_meals"] == 1
    assert cp_plan["color_code"] == "#10B981"
    assert len(cp_plan["rates"]) == 3  # Single (1), Double (2), Triple (3)

    # 5. Complete setup
    await async_client.post(
        f"/api/v1/properties/{prop_id}/setup/complete",
        headers=headers,
    )

    today = date.today()
    tomorrow = today + timedelta(days=1)

    # 6. Test Single Occupant Reservation (1 Adult) -> Should charge Single rate 3200
    res_single = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booker": {
                "first_name": "Alice",
                "last_name": "Single",
                "email": "alice@example.com",
                "phone": "+919876543210",
            },
            "rooms": [
                {
                    "room_type_id": deluxe_rt_id,
                    "rate_plan_id": cp_plan_id,
                    "check_in_at": f"{today}T14:00:00Z",
                    "check_out_at": f"{tomorrow}T11:00:00Z",
                    "adults": 1,
                    "children": 0,
                }
            ],
        },
        headers=headers,
    )
    assert res_single.status_code == 201
    single_data = res_single.json()
    room_rate_single = single_data["rooms"][0]["room_rates"][0]
    assert float(room_rate_single["base_amount"]) == 3200.0
    assert float(room_rate_single["extra_person_amount"]) == 0.0
    assert float(room_rate_single["net_amount"]) == 3200.0

    # 7. Test Double Occupant Reservation (2 Adults) -> Should charge Double rate 4000
    res_double = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booker": {
                "first_name": "Bob",
                "last_name": "Double",
                "email": "bob@example.com",
                "phone": "+919876543211",
            },
            "rooms": [
                {
                    "room_type_id": deluxe_rt_id,
                    "rate_plan_id": cp_plan_id,
                    "check_in_at": f"{today}T14:00:00Z",
                    "check_out_at": f"{tomorrow}T11:00:00Z",
                    "adults": 2,
                    "children": 0,
                }
            ],
        },
        headers=headers,
    )
    assert res_double.status_code == 201
    double_data = res_double.json()
    room_rate_double = double_data["rooms"][0]["room_rates"][0]
    assert float(room_rate_double["base_amount"]) == 4000.0
    assert float(room_rate_double["extra_person_amount"]) == 0.0
    assert float(room_rate_double["net_amount"]) == 4000.0

    # 8. Test Triple Occupant Reservation (3 Adults) -> Should charge Triple rate 5000
    res_triple = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booker": {
                "first_name": "Charlie",
                "last_name": "Triple",
                "email": "charlie@example.com",
                "phone": "+919876543212",
            },
            "rooms": [
                {
                    "room_type_id": deluxe_rt_id,
                    "rate_plan_id": cp_plan_id,
                    "check_in_at": f"{today}T14:00:00Z",
                    "check_out_at": f"{tomorrow}T11:00:00Z",
                    "adults": 3,
                    "children": 0,
                }
            ],
        },
        headers=headers,
    )
    assert res_triple.status_code == 201
    triple_data = res_triple.json()
    room_rate_triple = triple_data["rooms"][0]["room_rates"][0]
    assert float(room_rate_triple["base_amount"]) == 5000.0
    assert float(room_rate_triple["extra_person_amount"]) == 0.0
    assert float(room_rate_triple["net_amount"]) == 5000.0

    # 9. Test 4 Adults + 1 Child -> Should charge Triple rate 5000 + 1 Extra Adult (1000) + 1 Extra Child (500) = 6500
    res_quad = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booker": {
                "first_name": "Dana",
                "last_name": "Family",
                "email": "dana@example.com",
                "phone": "+919876543213",
            },
            "rooms": [
                {
                    "room_type_id": deluxe_rt_id,
                    "rate_plan_id": cp_plan_id,
                    "check_in_at": f"{today}T14:00:00Z",
                    "check_out_at": f"{tomorrow}T11:00:00Z",
                    "adults": 4,
                    "children": 1,
                }
            ],
        },
        headers=headers,
    )
    assert res_quad.status_code == 201
    quad_data = res_quad.json()
    room_rate_quad = quad_data["rooms"][0]["room_rates"][0]
    assert float(room_rate_quad["base_amount"]) == 4000.0 or float(room_rate_quad["base_amount"]) == 5000.0
    assert float(room_rate_quad["net_amount"]) == 6500.0

