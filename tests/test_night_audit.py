import pytest
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folio import Folio, FolioTransaction
from app.models.operation import NightAudit, PropertyDailySummary
from app.models.property import Property
from app.models.property_settings import PropertySettings
from app.models.reservation import Reservation, ReservationRoomRate
from app.models.room import Room
from app.scheduler.night_audit_scheduler import check_and_run_scheduled_night_audits
from app.utils.enums import (
    FolioEntryType,
    FolioTransactionSource,
    FolioTransactionType,
    NightAuditStatus,
    ReservationStatus,
)


@pytest.mark.asyncio
async def test_night_audit_full_flow(async_client: AsyncClient, db_session: AsyncSession):
    # 1. Setup Organization & Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Night Audit Hotels", "slug": "night-audit-hotels"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Hotel Midnight Sun", "code": "HMS"},
        headers={"X-Organization-ID": org_id},
    )
    assert prop_res.status_code == 201
    prop_id = prop_res.json()["id"]

    # 2. Setup Room Type & Physical Room
    rt_res = await async_client.post(
        f"/api/v1/room-types?property_id={prop_id}",
        json={"name": "Executive Suite", "code": "EXE", "base_occupancy": 2, "max_occupancy": 4},
    )
    assert rt_res.status_code == 201
    rt_id = rt_res.json()["id"]

    room_res = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_type_id": rt_id, "room_number": "101", "floor": "1"},
    )
    assert room_res.status_code == 201
    room_id = room_res.json()["id"]

    # Another room for unarrived reservation
    room_res2 = await async_client.post(
        f"/api/v1/rooms?property_id={prop_id}",
        json={"room_type_id": rt_id, "room_number": "102", "floor": "1"},
    )
    assert room_res2.status_code == 201
    room_id2 = room_res2.json()["id"]

    # 3. Setup Rate Plan & Daily Price
    rp_res = await async_client.post(
        f"/api/v1/rate-plans?property_id={prop_id}",
        json={"name": "Daily Rate", "code": "BAR", "room_type_id": rt_id, "booking_type": "NIGHTLY"},
    )
    assert rp_res.status_code == 201
    rp_id = rp_res.json()["id"]

    await async_client.post(
        f"/api/v1/rate-plans/{rp_id}/rates",
        json={"duration": 1, "duration_unit": "NIGHT", "price": "3500.00"},
    )

    # 4. Check initial Night Audit status
    status_res = await async_client.get(f"/api/v1/properties/{prop_id}/night-audit/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["property_id"] == prop_id
    assert status_data["night_audit_mode"] == "MANUAL"
    assert status_data["can_run_audit"] is True

    # 5. Update Property Settings to AUTO mode with scheduled time 13:00
    settings_up = await async_client.put(
        f"/api/v1/properties/{prop_id}/settings",
        json={
            "night_audit_mode": "AUTO",
            "night_audit_time": "13:00:00",
            "night_audit_config": {
                "auto_no_show": True,
                "auto_checkout": False,
            },
        },
    )
    assert settings_up.status_code == 200
    assert settings_up.json()["night_audit_mode"] == "AUTO"
    assert settings_up.json()["night_audit_time"] == "13:00:00"
    assert settings_up.json()["night_audit_config"]["auto_no_show"] is True

    # Fetch property business date
    prop_obj = await db_session.get(Property, prop_id)
    initial_business_date = prop_obj.business_date or date.today()
    check_in_dt = datetime.combine(initial_business_date, time(14, 0), tzinfo=timezone.utc)
    check_out_dt = check_in_dt + timedelta(days=2)

    # 6. Create Reservation 1: will be Checked-In
    res1_in = {
        "booking_type": "NIGHTLY",
        "booker": {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "phone": "+919876543210",
        },
        "rooms": [
            {
                "room_type_id": rt_id,
                "rate_plan_id": rp_id,
                "check_in_at": check_in_dt.isoformat(),
                "check_out_at": check_out_dt.isoformat(),
                "adults": 2,
            }
        ],
    }
    r1 = await async_client.post(f"/api/v1/reservations?property_id={prop_id}", json=res1_in)
    assert r1.status_code == 201
    res1_id = r1.json()["id"]

    # Check In Reservation 1
    ci_res = await async_client.post(
        f"/api/v1/reservations/{res1_id}/check-in?property_id={prop_id}",
        json={"room_id": room_id},
    )
    assert ci_res.status_code == 200
    assert ci_res.json()["status"] == "CHECKED_IN"

    # 7. Create Reservation 2: will remain unarrived CONFIRMED (Candidate for NO_SHOW)
    res2_in = {
        "booking_type": "NIGHTLY",
        "booker": {
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
        },
        "rooms": [
            {
                "room_type_id": rt_id,
                "rate_plan_id": rp_id,
                "check_in_at": check_in_dt.isoformat(),
                "check_out_at": check_out_dt.isoformat(),
                "adults": 1,
            }
        ],
    }
    r2 = await async_client.post(f"/api/v1/reservations?property_id={prop_id}", json=res2_in)
    assert r2.status_code == 201
    res2_id = r2.json()["id"]

    # 8. Pre-check API validation
    precheck = await async_client.get(f"/api/v1/properties/{prop_id}/night-audit/pre-check")
    assert precheck.status_code == 200
    pc_data = precheck.json()
    assert len(pc_data["pending_arrivals"]) == 1
    assert pc_data["pending_arrivals"][0]["reservation_id"] == res2_id
    assert len(pc_data["rooms_to_post"]) == 1
    assert pc_data["rooms_to_post"][0]["reservation_id"] == res1_id
    assert pc_data["can_run"] is True

    # 9. Execute Night Audit manually
    audit_run = await async_client.post(
        f"/api/v1/properties/{prop_id}/night-audit/run",
        json={"auto_no_show": True, "notes": "End of Day close test"},
    )
    assert audit_run.status_code == 200
    run_data = audit_run.json()
    assert run_data["status"] == "COMPLETED"
    assert run_data["rooms_posted"] == 1
    assert run_data["no_shows_marked"] == 1
    assert run_data["summary_data"] is not None
    assert "financials" in run_data["summary_data"]
    assert run_data["summary_data"]["financials"]["room_revenue"] == 3500.0

    # 10. Verify Database Changes
    # Property business_date must have rolled to initial_business_date + 1 day
    await db_session.refresh(prop_obj)
    expected_new_date = initial_business_date + timedelta(days=1)
    assert prop_obj.business_date == expected_new_date

    # Reservation 2 must now be NO_SHOW
    res2_db = await db_session.get(Reservation, res2_id)
    assert res2_db.status == ReservationStatus.NO_SHOW.value

    # Reservation 1's folio must have a DEBIT ROOM_CHARGE from NIGHT_AUDIT
    folio_q = await db_session.execute(select(Folio).where(Folio.reservation_id == res1_id))
    folio1 = folio_q.scalars().first()
    assert folio1 is not None

    txn_q = await db_session.execute(
        select(FolioTransaction).where(
            FolioTransaction.folio_id == folio1.id,
            FolioTransaction.transaction_type == FolioTransactionType.ROOM_CHARGE.value,
        )
    )
    room_charge_txn = txn_q.scalars().first()
    assert room_charge_txn is not None
    assert room_charge_txn.entry_type == FolioEntryType.DEBIT.value
    assert room_charge_txn.source == FolioTransactionSource.NIGHT_AUDIT.value
    assert room_charge_txn.amount == Decimal("3500.00")

    # ReservationRoomRate should be stamped with folio_transaction_id
    rate_q = await db_session.execute(
        select(ReservationRoomRate).where(
            ReservationRoomRate.stay_date == initial_business_date,
            ReservationRoomRate.folio_transaction_id.is_not(None),
        )
    )
    posted_rate = rate_q.scalars().first()
    assert posted_rate is not None
    assert posted_rate.folio_transaction_id == room_charge_txn.id

    # Verify dedicated PropertyDailySummary row was written per property
    pds_q = await db_session.execute(
        select(PropertyDailySummary).where(
            PropertyDailySummary.property_id == prop_id,
            PropertyDailySummary.business_date == initial_business_date,
        )
    )
    pds_row = pds_q.scalar_one_or_none()
    assert pds_row is not None
    assert pds_row.rooms_sold == 1
    assert pds_row.no_shows_marked == 1
    assert pds_row.room_revenue == Decimal("3500.00")
    assert pds_row.total_revenue == Decimal("3500.00")

    # 11. Verify Audit History and Report Endpoints
    history_res = await async_client.get(f"/api/v1/properties/{prop_id}/night-audit/history")
    assert history_res.status_code == 200
    assert len(history_res.json()) >= 1

    audit_id = run_data["id"]
    report_res = await async_client.get(f"/api/v1/properties/{prop_id}/night-audit/{audit_id}/report")
    assert report_res.status_code == 200
    rep_data = report_res.json()
    assert rep_data["audit_id"] == audit_id
    assert rep_data["rooms_posted"] == 1
    assert rep_data["summary_data"]["rooms"]["rooms_sold"] == 1


@pytest.mark.asyncio
async def test_scheduler_poller_execution(async_client: AsyncClient, db_session: AsyncSession, monkeypatch):
    # 1. Setup Property
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Scheduler Org", "slug": "scheduler-org"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Auto Audit Resort", "code": "AAR", "timezone": "Asia/Kolkata"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    # 2. Configure Property Settings with AUTO mode and a scheduled time (e.g. 13:00)
    await async_client.put(
        f"/api/v1/properties/{prop_id}/settings",
        json={
            "night_audit_mode": "AUTO",
            "night_audit_time": "13:00:00",
            "night_audit_config": {
                "auto_no_show": True,
                "auto_checkout": False,
            },
        },
    )

    prop_obj = await db_session.get(Property, prop_id)
    initial_bdate = prop_obj.business_date

    # Monkeypatch AsyncSessionLocal in night_audit_scheduler to yield db_session in tests
    from unittest.mock import MagicMock
    from app.scheduler import night_audit_scheduler

    class MockAsyncSessionContext:
        async def __aenter__(self):
            return db_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(night_audit_scheduler, "AsyncSessionLocal", lambda: MockAsyncSessionContext())

    # Case A: If local time is before 13:00 (e.g. 10:00), poller should NOT trigger
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Kolkata")
    mock_morning = datetime.combine(initial_bdate, datetime.min.time()).replace(hour=10, tzinfo=tz)

    class MockDateTimeMorning:
        @classmethod
        def now(cls, tz=None):
            return mock_morning

    monkeypatch.setattr(night_audit_scheduler, "datetime", MockDateTimeMorning)

    await check_and_run_scheduled_night_audits()

    # Verify no audit ran and business_date didn't advance
    await db_session.refresh(prop_obj)
    assert prop_obj.business_date == initial_bdate

    # Case B: If local time reaches or passes 13:00 (e.g. 13:05), poller SHOULD trigger!
    mock_afternoon = datetime.combine(initial_bdate, datetime.min.time()).replace(hour=13, minute=5, tzinfo=tz)

    class MockDateTimeAfternoon:
        @classmethod
        def now(cls, tz=None):
            return mock_afternoon

    monkeypatch.setattr(night_audit_scheduler, "datetime", MockDateTimeAfternoon)

    await check_and_run_scheduled_night_audits()

    # Verify business_date advanced by +1 day
    await db_session.refresh(prop_obj)
    assert prop_obj.business_date == initial_bdate + timedelta(days=1)

    # Verify NightAudit record was created with trigger_type == 'SCHEDULED'
    stmt = select(NightAudit).where(NightAudit.property_id == prop_id)
    audit_row = (await db_session.execute(stmt)).scalars().first()
    assert audit_row is not None
    assert audit_row.status == NightAuditStatus.COMPLETED.value
    assert audit_row.trigger_type == "SCHEDULED"

    # Case C: On next minute tick, it should NOT re-run for the same business date
    await check_and_run_scheduled_night_audits()
    await db_session.refresh(prop_obj)
    assert prop_obj.business_date == initial_bdate + timedelta(days=1)

