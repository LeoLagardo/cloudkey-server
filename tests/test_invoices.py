from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.folio import Folio, FolioTransaction
from app.models.guest import Guest
from app.models.rate_plan import RatePlan
from app.models.reservation import Reservation, ReservationRoom
from app.models.room import Room
from app.models.room_type import RoomType
from app.models.service import Service
from app.models.tax import Tax, TaxGroup, TaxGroupItem, TaxRate
from app.utils.enums import (
    EntityStatus,
    FolioEntryType,
    FolioTransactionSource,
    FolioTransactionType,
    FolioType,
    InvoiceStatus,
    InvoiceType,
    ReservationStatus,
    TaxRateType,
)


async def setup_test_invoice_data(async_client: AsyncClient, db_session: AsyncSession) -> dict:
    """Sets up an org, property with GSTIN, guest, room, room rate, service, and checked-in reservation with folio."""
    # 1. Organization & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Grand Horizon Hospitality", "slug": "grand-horizon"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={
            "name": "Grand Horizon Resort",
            "code": "GHR-01",
            "currency": "INR",
            "gstin": "27AAPCG1234F1Z5",
            "address_line_1": "100 Beach Boulevard",
            "city": "Goa",
            "state": "Goa",
            "country": "India",
            "postal_code": "403001",
        },
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 2. Taxes (CGST 6% + SGST 6%) & Tax Group
    cgst = Tax(
        organization_id=org_id,
        name="CGST",
        code="CGST_6",
        status=EntityStatus.ACTIVE.value,
    )
    sgst = Tax(
        organization_id=org_id,
        name="SGST",
        code="SGST_6",
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add_all([cgst, sgst])
    await db_session.flush()

    cgst_rate = TaxRate(
        tax_id=cgst.id,
        rate_type=TaxRateType.PERCENTAGE.value,
        rate=Decimal("6.0000"),
        valid_from=datetime.now(timezone.utc).date() - timedelta(days=30),
    )
    sgst_rate = TaxRate(
        tax_id=sgst.id,
        rate_type=TaxRateType.PERCENTAGE.value,
        rate=Decimal("6.0000"),
        valid_from=datetime.now(timezone.utc).date() - timedelta(days=30),
    )
    tax_group = TaxGroup(
        organization_id=org_id,
        name="GST 12%",
        code="GST_12",
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add_all([cgst_rate, sgst_rate, tax_group])
    await db_session.flush()

    tg_item1 = TaxGroupItem(tax_group_id=tax_group.id, tax_id=cgst.id, sequence=1)
    tg_item2 = TaxGroupItem(tax_group_id=tax_group.id, tax_id=sgst.id, sequence=2)
    db_session.add_all([tg_item1, tg_item2])
    await db_session.flush()

    # 3. Room Type & Room
    rt = RoomType(
        property_id=prop_id,
        name="Deluxe Ocean View",
        code="DELUXE",
        base_occupancy=2,
        max_occupancy=3,
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add(rt)
    await db_session.flush()

    room = Room(
        property_id=prop_id,
        room_type_id=rt.id,
        room_number="101",
        status="AVAILABLE",
    )
    db_session.add(room)

    # 4. Rate Plan
    rp = RatePlan(
        property_id=prop_id,
        room_type_id=rt.id,
        name="Standard Rate",
        code="BAR",
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add(rp)

    # 5. Service (F&B Breakfast)
    svc = Service(
        property_id=prop_id,
        name="Buffet Breakfast",
        code="BF-01",
        category="FOOD_BEVERAGE",
        default_price=Decimal("500.00"),
        tax_group_id=tax_group.id,
        hsn_sac_code="996331",
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add(svc)

    # 6. Guest
    guest = Guest(
        organization_id=org_id,
        first_name="Raj",
        last_name="Malhotra",
        email="raj.malhotra@example.com",
        phone="+919876543210",
        address_line_1="42 Park Avenue",
        city="Mumbai",
        state="Maharashtra",
        country="India",
        postal_code="400001",
        gstin="27AABCU9603R1ZM",
    )
    db_session.add(guest)

    # 7. Corporate Company
    company = Company(
        organization_id=org_id,
        name="Acme Tech Global India Pvt Ltd",
        company_type="CORPORATE",
        gstin="29ABCDE1234F2Z5",
        billing_address="Tower 4, Electronic City, Bangalore, Karnataka 560100",
        status=EntityStatus.ACTIVE.value,
    )
    db_session.add(company)
    await db_session.flush()

    # 8. Reservation & Room
    now = datetime.now(timezone.utc)
    res = Reservation(
        property_id=prop_id,
        guest_id=guest.id,
        booking_number="BK-TEST-1001",
        booking_type="DIRECT",
        source="FRONT_DESK",
        status=ReservationStatus.CHECKED_IN.value,
        check_in_at=now,
        check_out_at=now + timedelta(days=2),
        currency="INR",
        total_amount=Decimal("5000.00"),
        total_tax_amount=Decimal("600.00"),
    )
    db_session.add(res)
    await db_session.flush()

    res_room = ReservationRoom(
        reservation_id=res.id,
        room_type_id=rt.id,
        room_id=room.id,
        rate_plan_id=rp.id,
        status=ReservationStatus.CHECKED_IN.value,
        check_in_at=now,
        check_out_at=now + timedelta(days=2),
        adults=2,
        children=0,
    )
    db_session.add(res_room)

    # 9. Folio & Folio Transactions
    folio = Folio(
        property_id=prop_id,
        reservation_id=res.id,
        guest_id=guest.id,
        folio_number=f"FOL-{res.booking_number}",
        folio_type=FolioType.GUEST.value,
        status="OPEN",
        currency="INR",
        opened_at=now,
    )
    db_session.add(folio)
    await db_session.flush()

    # Stay Room Charge
    room_txn = FolioTransaction(
        property_id=prop_id,
        folio_id=folio.id,
        business_date=now.date(),
        entry_type=FolioEntryType.DEBIT.value,
        transaction_type=FolioTransactionType.ROOM_CHARGE.value,
        description="Room Night Charge (DELUXE)",
        quantity=Decimal("1.00"),
        unit_price=Decimal("4000.00"),
        amount=Decimal("4000.00"),
        tax_amount=Decimal("480.00"),
        total_amount=Decimal("4480.00"),
        hsn_sac_code="996311",
        source=FolioTransactionSource.SYSTEM.value,
        posted_at=now,
    )
    db_session.add(room_txn)
    await db_session.commit()

    return {
        "org_id": org_id,
        "prop_id": prop_id,
        "guest_id": guest.id,
        "company_id": company.id,
        "reservation_id": res.id,
        "folio_id": folio.id,
        "service_id": svc.id,
        "room_id": room.id,
    }


@pytest.mark.asyncio
async def test_generate_tax_invoice_from_folio(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]

    # 1. Post incidental service charge to folio
    svc_res = await async_client.post(
        f"/api/v1/reservations/{env['reservation_id']}/services?property_id={prop_id}",
        json={
            "service_id": env["service_id"],
            "quantity": "2.00",
        },
    )
    assert svc_res.status_code == 201

    # 2. Generate Tax Invoice
    inv_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={
            "folio_id": folio_id,
            "invoice_type": "TAX_INVOICE",
            "recipient_type": "GUEST",
        },
    )
    assert inv_res.status_code == 201
    data = inv_res.json()

    assert data["invoice_type"] == "TAX_INVOICE"
    assert data["status"] == "ISSUED"
    assert "INV-" in data["invoice_number"]
    assert data["bill_to_name"] == "Raj Malhotra"
    assert data["bill_to_gstin"] == "27AABCU9603R1ZM"
    assert len(data["lines"]) == 2  # Room charge + Breakfast

    # Check line item details
    room_line = next(l for l in data["lines"] if "Room Night" in l["description"])
    assert room_line["hsn_sac_code"] == "996311"
    assert Decimal(str(room_line["unit_price"])) == Decimal("4000.00")

    bfast_line = next(l for l in data["lines"] if "Buffet Breakfast" in l["description"])
    assert bfast_line["hsn_sac_code"] == "996331"
    assert Decimal(str(bfast_line["quantity"])) == Decimal("2.00")
    assert Decimal(str(bfast_line["taxable_amount"])) == Decimal("1000.00")
    assert Decimal(str(bfast_line["tax_amount"])) == Decimal("120.00")
    assert len(bfast_line["tax_breakdown"]) == 2

    # Check totals
    assert Decimal(str(data["subtotal"])) == Decimal("5000.00")
    assert Decimal(str(data["tax_total"])) == Decimal("600.00")
    assert Decimal(str(data["grand_total"])) == Decimal("5600.00")
    assert data["property"]["gstin"] == "27AAPCG1234F1Z5"


@pytest.mark.asyncio
async def test_generate_proforma_invoice(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]

    proforma_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={
            "folio_id": folio_id,
            "invoice_type": "PROFORMA",
            "recipient_type": "GUEST",
        },
    )
    assert proforma_res.status_code == 201
    p_data = proforma_res.json()

    assert p_data["invoice_type"] == "PROFORMA"
    assert p_data["status"] == "DRAFT"
    assert "PRO-" in p_data["invoice_number"]
    assert Decimal(str(p_data["grand_total"])) == Decimal("4480.00")


@pytest.mark.asyncio
async def test_corporate_billing_invoice(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]
    company_id = env["company_id"]

    inv_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={
            "folio_id": folio_id,
            "invoice_type": "TAX_INVOICE",
            "recipient_type": "COMPANY",
            "company_id": company_id,
        },
    )
    assert inv_res.status_code == 201
    data = inv_res.json()

    assert data["bill_to_name"] == "Acme Tech Global India Pvt Ltd"
    assert data["bill_to_gstin"] == "29ABCDE1234F2Z5"
    assert "Electronic City" in data["bill_to_address"]
    assert data["company_id"] == company_id


@pytest.mark.asyncio
async def test_issue_credit_note_and_cancel(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]

    # 1. Generate active invoice
    inv_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "TAX_INVOICE"},
    )
    assert inv_res.status_code == 201
    orig_invoice = inv_res.json()
    orig_id = orig_invoice["id"]

    # 2. Issue Credit Note
    cn_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices/{orig_id}/credit-note",
        json={"reason": "Customer discount dispute post-checkout"},
    )
    assert cn_res.status_code == 201
    cn_data = cn_res.json()

    assert cn_data["invoice_type"] == "CREDIT_NOTE"
    assert "CN-" in cn_data["invoice_number"]
    assert cn_data["original_invoice_id"] == orig_id
    assert Decimal(str(cn_data["grand_total"])) == -abs(Decimal(str(orig_invoice["grand_total"])))
    assert len(cn_data["lines"]) == len(orig_invoice["lines"])

    # 3. Cancel the original invoice
    cancel_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices/{orig_id}/cancel",
        json={"reason": "Re-issuing amended bill"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_list_and_folio_invoices(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]

    # Issue an invoice
    await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "TAX_INVOICE"},
    )

    # 1. List invoices for property
    list_res = await async_client.get(f"/api/v1/properties/{prop_id}/invoices")
    assert list_res.status_code == 200
    invoices = list_res.json()
    assert len(invoices) >= 1

    # 2. Search invoices
    search_res = await async_client.get(f"/api/v1/properties/{prop_id}/invoices?search=Raj")
    assert search_res.status_code == 200
    assert len(search_res.json()) >= 1

    # 3. List folio invoices
    folio_inv_res = await async_client.get(f"/api/v1/properties/{prop_id}/folios/{folio_id}/invoices")
    assert folio_inv_res.status_code == 200
    assert len(folio_inv_res.json()) >= 1


@pytest.mark.asyncio
async def test_checkout_with_auto_tax_invoice(async_client: AsyncClient, db_session: AsyncSession):
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    res_id = env["reservation_id"]
    folio_id = env["folio_id"]

    # Checkout reservation with settlement payment and generate_tax_invoice = True
    co_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-out?property_id={prop_id}",
        json={
            "settlement_payment": {
                "payment_method": "CASH",
                "amount": "4480.00",
                "reference": "RCPT-AUTO-01",
            },
            "generate_tax_invoice": True,
        },
    )
    assert co_res.status_code == 200
    res_data = co_res.json()
    assert res_data["status"] == "CHECKED_OUT"

    # Verify that tax invoice exists for this folio
    folio_invs = await async_client.get(f"/api/v1/properties/{prop_id}/folios/{folio_id}/invoices")
    assert folio_invs.status_code == 200
    inv_list = folio_invs.json()
    assert len(inv_list) >= 1
    assert any(inv["invoice_type"] == "TAX_INVOICE" for inv in inv_list)


@pytest.mark.asyncio
async def test_tax_invoice_includes_nightly_breakdown_multi_night(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that a multi-night reservation without prior night audit includes each night itemized in the Tax Invoice."""
    # 1. Setup Org & Property with GSTIN
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Himalayan Retreats", "slug": "himalayan-retreats"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={
            "name": "Himalayan Grand Resort",
            "code": "HGR",
            "currency": "INR",
            "gstin": "02AAPCH9988G1Z1",
            "address_line_1": "Mall Road",
            "city": "Manali",
            "state": "Himachal Pradesh",
            "country": "India",
            "postal_code": "175131",
        },
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    # 2. Taxes (CGST 6% + SGST 6%) & Tax Group
    cgst = Tax(organization_id=org_id, name="CGST", code="CGST_6", status=EntityStatus.ACTIVE.value)
    sgst = Tax(organization_id=org_id, name="SGST", code="SGST_6", status=EntityStatus.ACTIVE.value)
    db_session.add_all([cgst, sgst])
    await db_session.flush()

    cgst_rate = TaxRate(
        tax_id=cgst.id,
        rate_type=TaxRateType.PERCENTAGE.value,
        rate=Decimal("6.0000"),
        valid_from=datetime.now(timezone.utc).date() - timedelta(days=30),
    )
    sgst_rate = TaxRate(
        tax_id=sgst.id,
        rate_type=TaxRateType.PERCENTAGE.value,
        rate=Decimal("6.0000"),
        valid_from=datetime.now(timezone.utc).date() - timedelta(days=30),
    )
    tax_group = TaxGroup(organization_id=org_id, name="GST 12%", code="GST_12", status=EntityStatus.ACTIVE.value)
    db_session.add_all([cgst_rate, sgst_rate, tax_group])
    await db_session.flush()

    db_session.add_all([
        TaxGroupItem(tax_group_id=tax_group.id, tax_id=cgst.id, sequence=1),
        TaxGroupItem(tax_group_id=tax_group.id, tax_id=sgst.id, sequence=2),
    ])
    await db_session.flush()

    # 3. Room Type, Rate Plan with Tax Group, and Room
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Pine Suite", "code": "PINE"},
    )
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "European Plan", "code": "EP", "room_type_id": rt_id, "tax_group_id": tax_group.id},
    )
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "3000.00"},
    )

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "301", "room_type_id": rt_id},
    )
    room_id = room_res.json()["id"]

    # 4. Create 3-night reservation
    now = datetime.now(timezone.utc)
    check_in = now + timedelta(days=1)
    check_out = now + timedelta(days=4)  # 3 nights

    res_post = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booking_type": "NIGHTLY",
            "booker": {
                "first_name": "Vikram",
                "last_name": "Aditya",
                "email": "vikram@example.com",
                "phone": "+919123456780",
            },
            "rooms": [
                {
                    "room_type_id": rt_id,
                    "room_id": room_id,
                    "rate_plan_id": rp_id,
                    "check_in_at": check_in.isoformat(),
                    "check_out_at": check_out.isoformat(),
                    "adults": 2,
                    "children": 0,
                }
            ],
        },
    )
    assert res_post.status_code == 201
    res_data = res_post.json()
    folio_id = res_data["folio"]["id"]

    # 5. Generate Tax Invoice directly without running night audit
    inv_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={
            "folio_id": folio_id,
            "invoice_type": "TAX_INVOICE",
            "recipient_type": "GUEST",
        },
    )
    assert inv_res.status_code == 201
    inv_data = inv_res.json()

    assert inv_data["invoice_type"] == "TAX_INVOICE"
    assert inv_data["status"] == "ISSUED"
    # Should have 3 itemized lines: one for each stay night!
    assert len(inv_data["lines"]) == 3

    for idx, line in enumerate(inv_data["lines"]):
        stay_d = (check_in + timedelta(days=idx)).date().isoformat()
        assert "Room Night Charge" in line["description"]
        assert stay_d in line["description"]
        assert line["hsn_sac_code"] == "996311"
        assert Decimal(str(line["quantity"])) == Decimal("1.00")
        assert Decimal(str(line["unit_price"])) == Decimal("3000.00")
        assert Decimal(str(line["taxable_amount"])) == Decimal("3000.00")
        assert Decimal(str(line["tax_amount"])) == Decimal("360.00")
        assert Decimal(str(line["total_amount"])) == Decimal("3360.00")
        assert len(line["tax_breakdown"]) == 2

    # Grand totals for 3 nights: Subtotal 9000, Tax 1080, Grand Total 10080
    assert Decimal(str(inv_data["subtotal"])) == Decimal("9000.00")
    assert Decimal(str(inv_data["tax_total"])) == Decimal("1080.00")
    assert Decimal(str(inv_data["grand_total"])) == Decimal("10080.00")


@pytest.mark.asyncio
async def test_proforma_includes_nightly_breakdown_unposted(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that a Proforma Invoice quotes each night itemized even before transactions are posted to the ledger."""
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Coastal Sands Co", "slug": "coastal-sands"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Coastal Sands Resort", "code": "CSR", "currency": "INR"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Beach Villa", "code": "BV"},
    )
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Standard Rate", "code": "BAR", "room_type_id": rt_id},
    )
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "5000.00"},
    )

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "501", "room_type_id": rt_id},
    )
    room_id = room_res.json()["id"]

    now = datetime.now(timezone.utc)
    res_post = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booking_type": "NIGHTLY",
            "booker": {
                "first_name": "Pooja",
                "last_name": "Hegde",
                "email": "pooja@example.com",
            },
            "rooms": [
                {
                    "room_type_id": rt_id,
                    "room_id": room_id,
                    "rate_plan_id": rp_id,
                    "check_in_at": (now + timedelta(days=1)).isoformat(),
                    "check_out_at": (now + timedelta(days=3)).isoformat(),  # 2 nights
                    "adults": 2,
                    "children": 0,
                }
            ],
        },
    )
    assert res_post.status_code == 201
    folio_id = res_post.json()["folio"]["id"]

    # Generate Proforma
    proforma_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={
            "folio_id": folio_id,
            "invoice_type": "PROFORMA",
            "recipient_type": "GUEST",
        },
    )
    assert proforma_res.status_code == 201
    p_data = proforma_res.json()

    assert p_data["invoice_type"] == "PROFORMA"
    assert p_data["status"] == "DRAFT"
    assert len(p_data["lines"]) == 2  # 2 nights itemized
    for line in p_data["lines"]:
        assert "Room Night Charge" in line["description"]
        assert line["hsn_sac_code"] == "996311"
        assert Decimal(str(line["taxable_amount"])) == Decimal("5000.00")

    assert Decimal(str(p_data["subtotal"])) == Decimal("10000.00")


@pytest.mark.asyncio
async def test_checkout_posts_itemized_nightly_room_charges_to_folio_and_invoice(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verifies that checkout posts distinct nightly room charges to the folio and generates an itemized tax invoice."""
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Serene Valley Resorts", "slug": "serene-valley"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Serene Valley Inn", "code": "SVI", "currency": "INR", "gstin": "07AAACS1234E1Z8"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Valley View Suite", "code": "VVS"},
    )
    rt_id = rt_res.json()["id"]

    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Standard Rate", "code": "BAR", "room_type_id": rt_id},
    )
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "2500.00"},
    )

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_number": "105", "room_type_id": rt_id},
    )
    room_id = room_res.json()["id"]

    now = datetime.now(timezone.utc)
    check_in = now
    check_out = now + timedelta(days=2)  # 2 nights = 5000.00

    res_post = await async_client.post(
        f"/api/v1/reservations?property_id={prop_id}",
        json={
            "booking_type": "NIGHTLY",
            "booker": {
                "first_name": "Rohan",
                "last_name": "Mehra",
                "email": "rohan.mehra@example.com",
            },
            "rooms": [
                {
                    "room_type_id": rt_id,
                    "room_id": room_id,
                    "rate_plan_id": rp_id,
                    "check_in_at": check_in.isoformat(),
                    "check_out_at": check_out.isoformat(),
                    "adults": 1,
                    "children": 0,
                }
            ],
        },
    )
    assert res_post.status_code == 201
    res_data = res_post.json()
    res_id = res_data["id"]
    folio_id = res_data["folio"]["id"]

    # Check in
    ci_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-in?property_id={prop_id}",
        json={"room_id": room_id, "allow_early_checkin": True},
    )
    assert ci_res.status_code == 200

    # Checkout with settlement payment (2 nights @ 2500 = 5000) and generate_tax_invoice = True
    co_res = await async_client.post(
        f"/api/v1/reservations/{res_id}/check-out?property_id={prop_id}",
        json={
            "settlement_payment": {
                "payment_method": "CASH",
                "amount": "5000.00",
                "reference": "RCPT-VVS-01",
            },
            "generate_tax_invoice": True,
        },
    )
    assert co_res.status_code == 200
    assert co_res.json()["status"] == "CHECKED_OUT"

    # Verify that the folio now has 2 distinct DEBIT ROOM_CHARGE transactions (one for each night)
    txn_q = await db_session.execute(
        select(FolioTransaction).where(
            FolioTransaction.folio_id == folio_id,
            FolioTransaction.transaction_type == FolioTransactionType.ROOM_CHARGE.value,
        )
    )
    room_charges = list(txn_q.scalars().all())
    assert len(room_charges) == 2
    for rc in room_charges:
        assert rc.hsn_sac_code == "996311"
        assert rc.amount == Decimal("2500.00")
        assert "Room Night Charge" in rc.description

    # Verify that the generated Tax Invoice has both nights itemized
    inv_res = await async_client.get(f"/api/v1/properties/{prop_id}/folios/{folio_id}/invoices")
    assert inv_res.status_code == 200
    invoices = inv_res.json()
    assert len(invoices) >= 1
    tax_inv_id = invoices[0]["id"]

    inv_detail = await async_client.get(f"/api/v1/properties/{prop_id}/invoices/{tax_inv_id}")
    assert inv_detail.status_code == 200
    detail_data = inv_detail.json()
    assert len(detail_data["lines"]) == 2
    assert Decimal(str(detail_data["subtotal"])) == Decimal("5000.00")


@pytest.mark.asyncio
async def test_single_invoice_lifecycle_per_folio(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that re-clicking Proforma updates in-place and re-clicking Tax Invoice returns the existing issued invoice without duplicate numbers."""
    env = await setup_test_invoice_data(async_client, db_session)
    prop_id = env["prop_id"]
    folio_id = env["folio_id"]

    # 1. First Proforma generation
    p1_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "PROFORMA", "recipient_type": "GUEST"},
    )
    assert p1_res.status_code == 201
    p1_data = p1_res.json()
    p1_id = p1_data["id"]
    p1_num = p1_data["invoice_number"]

    # 2. Second Proforma generation -> must update in place, NOT create a second proforma
    p2_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "PROFORMA", "recipient_type": "GUEST"},
    )
    assert p2_res.status_code == 201
    p2_data = p2_res.json()
    assert p2_data["id"] == p1_id
    assert p2_data["invoice_number"] == p1_num

    # 3. First Tax Invoice generation
    t1_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "TAX_INVOICE", "recipient_type": "GUEST"},
    )
    assert t1_res.status_code == 201
    t1_data = t1_res.json()
    t1_id = t1_data["id"]
    t1_num = t1_data["invoice_number"]

    # 4. Second Tax Invoice generation -> must return the existing issued invoice, NOT create a second one
    t2_res = await async_client.post(
        f"/api/v1/properties/{prop_id}/invoices",
        json={"folio_id": folio_id, "invoice_type": "TAX_INVOICE", "recipient_type": "GUEST"},
    )
    assert t2_res.status_code == 201
    t2_data = t2_res.json()
    assert t2_data["id"] == t1_id
    assert t2_data["invoice_number"] == t1_num

    # 5. Verify total invoices for folio: exactly 1 Proforma and 1 Tax Invoice
    list_res = await async_client.get(f"/api/v1/properties/{prop_id}/folios/{folio_id}/invoices")
    assert list_res.status_code == 200
    all_invs = list_res.json()
    assert len(all_invs) == 2
    proformas = [i for i in all_invs if i["invoice_type"] == "PROFORMA"]
    tax_invs = [i for i in all_invs if i["invoice_type"] == "TAX_INVOICE"]
    assert len(proformas) == 1
    assert len(tax_invs) == 1



