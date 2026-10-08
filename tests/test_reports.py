import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reports_endpoints_json_and_excel(async_client: AsyncClient):
    # 1. Setup Organization & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Reports Hotel Org", "slug": "reports-hotel-org"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={
            "name": "Reports Grand Hotel",
            "code": "RGH-01",
            "city": "Mumbai",
            "currency": "INR",
            "timezone": "Asia/Kolkata",
            "status": "ACTIVE",
        },
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 2. Setup Room Type & Room
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Deluxe Room", "code": "DLX", "base_occupancy": 2, "max_occupancy": 3},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_type_id": rt_id, "room_number": "201", "floor": "2", "status": "AVAILABLE"},
    )
    assert room_res.status_code == 201

    base_url = f"/api/v1/properties/{prop_id}/reports"

    # 3. Test Tier 1: Arrivals & Departures (JSON and Excel)
    arr_json = await async_client.get(f"{base_url}/arrivals-departures")
    assert arr_json.status_code == 200
    assert "total_arrivals" in arr_json.json()

    arr_excel = await async_client.get(f"{base_url}/arrivals-departures?export=excel")
    assert arr_excel.status_code == 200
    assert arr_excel.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(arr_excel.content) > 1000

    # 4. Test Tier 1: In-House Guests (JSON and Excel)
    inh_json = await async_client.get(f"{base_url}/in-house")
    assert inh_json.status_code == 200
    assert "total_in_house_rooms" in inh_json.json()

    inh_excel = await async_client.get(f"{base_url}/in-house?export=excel")
    assert inh_excel.status_code == 200
    assert inh_excel.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(inh_excel.content) > 1000

    # 5. Test Tier 1: Room Availability (JSON and Excel)
    avail_json = await async_client.get(f"{base_url}/room-availability")
    assert avail_json.status_code == 200
    assert "total_physical_rooms" in avail_json.json()
    assert len(avail_json.json()["items"]) > 0
    first_item = avail_json.json()["items"][0]
    assert first_item["total_rooms"] == 1
    assert first_item["available_rooms"] == 1

    avail_excel = await async_client.get(f"{base_url}/room-availability?export=excel")
    assert avail_excel.status_code == 200
    assert len(avail_excel.content) > 1000

    # 6. Test Tier 1: Booking List & Search (JSON and Excel)
    bkg_json = await async_client.get(f"{base_url}/booking-list")
    assert bkg_json.status_code == 200
    assert "total_bookings" in bkg_json.json()

    bkg_excel = await async_client.get(f"{base_url}/booking-list?export=excel")
    assert bkg_excel.status_code == 200
    assert len(bkg_excel.content) > 1000

    # 7. Test Tier 2: Occupancy Report (JSON and Excel)
    occ_json = await async_client.get(f"{base_url}/occupancy")
    assert occ_json.status_code == 200
    assert "average_occupancy_percent" in occ_json.json()

    occ_excel = await async_client.get(f"{base_url}/occupancy?export=excel")
    assert occ_excel.status_code == 200
    assert len(occ_excel.content) > 1000

    # 8. Test Tier 2: Revenue Summary (JSON and Excel)
    rev_json = await async_client.get(f"{base_url}/revenue-summary")
    assert rev_json.status_code == 200
    assert "total_gross_revenue" in rev_json.json()

    rev_excel = await async_client.get(f"{base_url}/revenue-summary?export=excel")
    assert rev_excel.status_code == 200
    assert len(rev_excel.content) > 1000

    # 9. Test Tier 2: ADR and RevPAR (JSON and Excel)
    adr_json = await async_client.get(f"{base_url}/adr-revpar")
    assert adr_json.status_code == 200
    assert "overall_adr" in adr_json.json()
    assert "overall_revpar" in adr_json.json()

    adr_excel = await async_client.get(f"{base_url}/adr-revpar?export=excel")
    assert adr_excel.status_code == 200
    assert len(adr_excel.content) > 1000

    # 10. Test Tier 2: Outstanding Balances (JSON and Excel)
    out_json = await async_client.get(f"{base_url}/outstanding-balances")
    assert out_json.status_code == 200
    assert "total_open_folios" in out_json.json()

    out_excel = await async_client.get(f"{base_url}/outstanding-balances?export=excel")
    assert out_excel.status_code == 200
    assert len(out_excel.content) > 1000

    # 11. Test Tier 2: Payments / Cash Collection (JSON and Excel)
    pay_json = await async_client.get(f"{base_url}/payments-collection")
    assert pay_json.status_code == 200
    assert "total_amount_collected" in pay_json.json()

    pay_excel = await async_client.get(f"{base_url}/payments-collection?export=excel")
    assert pay_excel.status_code == 200
    assert len(pay_excel.content) > 1000

    # 12. Test Tier 3: Tax Report (JSON and Excel)
    tax_json = await async_client.get(f"{base_url}/tax-report")
    assert tax_json.status_code == 200
    assert "total_tax_amount" in tax_json.json()

    tax_excel = await async_client.get(f"{base_url}/tax-report?export=excel")
    assert tax_excel.status_code == 200
    assert len(tax_excel.content) > 1000

    # 13. Test Tier 3: Cancellations and No-Shows (JSON and Excel)
    canc_json = await async_client.get(f"{base_url}/cancellations-noshows")
    assert canc_json.status_code == 200
    assert "total_cancellations" in canc_json.json()

    canc_excel = await async_client.get(f"{base_url}/cancellations-noshows?export=excel")
    assert canc_excel.status_code == 200
    assert len(canc_excel.content) > 1000

    # 14. Test Day-End Night Audit Summary (JSON and Excel)
    na_json = await async_client.get(f"{base_url}/night-audit-summary")
    assert na_json.status_code == 200
    assert "total_audited_days" in na_json.json()

    na_excel = await async_client.get(f"{base_url}/night-audit-summary?export=excel")
    assert na_excel.status_code == 200
    assert len(na_excel.content) > 1000

    # 15. Test Guest History & Repeat Profiles (JSON and Excel)
    gh_json = await async_client.get(f"{base_url}/guest-history")
    assert gh_json.status_code == 200
    assert "total_guests_tracked" in gh_json.json()

    gh_excel = await async_client.get(f"{base_url}/guest-history?export=excel")
    assert gh_excel.status_code == 200
    assert len(gh_excel.content) > 1000
