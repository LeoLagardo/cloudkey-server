from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthenticatedUser, get_current_user
from app.schemas.reports import (
    ADRRevPARReportResponse,
    ArrivalDepartureReportResponse,
    BookingListReportResponse,
    CancellationReportResponse,
    GuestHistoryReportResponse,
    InHouseReportResponse,
    NightAuditReportResponse,
    OccupancyReportResponse,
    OutstandingBalancesReportResponse,
    PaymentsReportResponse,
    RevenueSummaryReportResponse,
    RoomAvailabilityReportResponse,
    TaxReportResponse,
)
from app.services.excel_export_service import excel_export_service
from app.services.night_audit_service import night_audit_service
from app.services.report_service import report_service

router = APIRouter(prefix="/properties/{property_id}/reports", tags=["Reports"])


def _stream_excel(stream, filename: str) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )


# ─── TIER 1: OPERATIONAL REPORTS ──────────────────────────────────────────────

@router.get("/arrivals-departures", response_model=ArrivalDepartureReportResponse)
async def get_arrivals_departures(
    property_id: str,
    target_date: Optional[date] = Query(None, description="Date for expected movements (YYYY-MM-DD)"),
    movement_type: str = Query("ALL", description="ALL, ARRIVALS, or DEPARTURES"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Operational front desk report of expected check-ins and check-outs."""
    data = await report_service.get_arrivals_departures(
        db, property_id=property_id, target_date=target_date, filter_type=movement_type
    )

    if export == "excel":
        columns = [
            {"key": "movement_type", "header": "Type", "width": 14},
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "guest_name", "header": "Guest Name", "width": 24},
            {"key": "guest_phone", "header": "Phone", "width": 16},
            {"key": "room_number", "header": "Room", "width": 10},
            {"key": "room_type_name", "header": "Room Type", "width": 18},
            {"key": "check_in_at", "header": "Check-in", "width": 16},
            {"key": "check_out_at", "header": "Check-out", "width": 16},
            {"key": "nights", "header": "Nights", "width": 8, "align": "center"},
            {"key": "status", "header": "Status", "width": 14},
            {"key": "total_amount", "header": "Total Amount", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "total_paid", "header": "Paid", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "balance_due", "header": "Balance Due", "width": 14, "align": "right", "format": "#,##0.00"},
        ]
        rows = [item.model_dump() for item in data.items]
        totals = {
            "booking_number": f"Total Records: {len(data.items)}",
            "balance_due": float(data.total_balance_due),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title=f"Arrivals & Departures Report ({data.filter_type})",
            property_name=data.property_name,
            date_range_label=f"Date: {data.target_date}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Arrivals_Departures",
        )
        return _stream_excel(stream, f"arrivals_departures_{data.target_date}")

    return data


@router.get("/in-house", response_model=InHouseReportResponse)
async def get_in_house_guests(
    property_id: str,
    as_of_date: Optional[date] = Query(None, description="As-of date (defaults to property business date)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Active in-house room occupants with folio balances."""
    data = await report_service.get_in_house_guests(db, property_id=property_id, as_of_date=as_of_date)

    if export == "excel":
        columns = [
            {"key": "room_number", "header": "Room #", "width": 10, "align": "center"},
            {"key": "floor", "header": "Floor", "width": 8, "align": "center"},
            {"key": "room_type_name", "header": "Room Type", "width": 18},
            {"key": "guest_name", "header": "Guest Name", "width": 24},
            {"key": "guest_phone", "header": "Phone", "width": 16},
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "check_in_at", "header": "Check-in", "width": 16},
            {"key": "check_out_at", "header": "Check-out", "width": 16},
            {"key": "stay_nights", "header": "Total Nights", "width": 12, "align": "center"},
            {"key": "nights_spent", "header": "Nights Spent", "width": 12, "align": "center"},
            {"key": "nights_remaining", "header": "Remaining", "width": 12, "align": "center"},
            {"key": "total_debits", "header": "Total Debits", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "total_credits", "header": "Total Paid", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "balance_due", "header": "Folio Balance", "width": 14, "align": "right", "format": "#,##0.00"},
        ]
        rows = [item.model_dump() for item in data.items]
        totals = {
            "room_number": f"Total In-House: {data.total_in_house_rooms}",
            "balance_due": float(data.total_outstanding_balance),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="In-House Guests Roster",
            property_name=data.property_name,
            date_range_label=f"As of: {data.as_of_date}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="In_House_Guests",
        )
        return _stream_excel(stream, f"in_house_guests_{data.as_of_date}")

    return data


@router.get("/room-availability", response_model=RoomAvailabilityReportResponse)
async def get_room_availability(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Room type availability, occupied, blocked, and maintenance rooms."""
    data = await report_service.get_room_availability(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "stay_date", "header": "Stay Date", "width": 14},
            {"key": "room_type_name", "header": "Room Type", "width": 20},
            {"key": "total_rooms", "header": "Total Rooms", "width": 12, "align": "right"},
            {"key": "sold_rooms", "header": "Occupied", "width": 12, "align": "right"},
            {"key": "blocked_rooms", "header": "Blocked", "width": 12, "align": "right"},
            {"key": "maintenance_rooms", "header": "OOO / Maint", "width": 12, "align": "right"},
            {"key": "available_rooms", "header": "Available", "width": 12, "align": "right"},
            {"key": "occupancy_percent", "header": "Occupancy %", "width": 14, "align": "right", "format": "0.0%"},
        ]
        rows = []
        for it in data.items:
            d = it.model_dump()
            d["occupancy_percent"] = d["occupancy_percent"] / 100.0  # Excel percentage formatting
            rows.append(d)

        stream = excel_export_service.generate_report_workbook(
            report_title="Room Availability and Status Report",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date}",
            columns=columns,
            rows=rows,
            sheet_name="Room_Availability",
        )
        return _stream_excel(stream, f"room_availability_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/booking-list", response_model=BookingListReportResponse)
async def get_booking_list(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Check-in from date"),
    to_date: Optional[date] = Query(None, description="Check-in to date"),
    status: Optional[str] = Query(None, description="Status filter (CONFIRMED, CHECKED_IN, etc.)"),
    source: Optional[str] = Query(None, description="Booking source (DIRECT, OTA, CORPORATE, etc.)"),
    search: Optional[str] = Query(None, description="Search guest name or booking #"),
    limit: int = Query(200, ge=1, le=1000),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Booking list audit and search report."""
    data = await report_service.get_booking_list(
        db,
        property_id=property_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
        source=source,
        search=search,
        limit=limit,
    )

    if export == "excel":
        columns = [
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "booked_at", "header": "Booked On", "width": 16},
            {"key": "guest_name", "header": "Guest Name", "width": 24},
            {"key": "source", "header": "Source", "width": 14},
            {"key": "room_type_name", "header": "Room Type", "width": 18},
            {"key": "room_number", "header": "Room", "width": 10},
            {"key": "check_in_at", "header": "Check-in", "width": 16},
            {"key": "check_out_at", "header": "Check-out", "width": 16},
            {"key": "nights", "header": "Nights", "width": 8, "align": "center"},
            {"key": "status", "header": "Status", "width": 14},
            {"key": "total_amount", "header": "Gross Amount", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "total_tax_amount", "header": "Tax Amount", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "total_paid", "header": "Paid", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "balance_due", "header": "Balance Due", "width": 14, "align": "right", "format": "#,##0.00"},
        ]
        rows = [item.model_dump() for item in data.items]
        totals = {
            "booking_number": f"Total Bookings: {data.total_bookings}",
            "total_amount": float(data.total_gross_value),
            "balance_due": float(data.total_balance_outstanding),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Reservations Master Audit List",
            property_name=data.property_name,
            date_range_label=f"Filters: {status or 'All Statuses'} | {source or 'All Sources'}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Booking_List",
        )
        return _stream_excel(stream, "booking_list_report")

    return data


# ─── TIER 2: FINANCIAL REPORTS ──────────────────────────────────────────────

@router.get("/occupancy", response_model=OccupancyReportResponse)
async def get_occupancy_report(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Daily occupancy report (rooms sold vs sellable rooms)."""
    data = await report_service.get_occupancy_report(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "stay_date", "header": "Date", "width": 14},
            {"key": "total_rooms", "header": "Total Physical", "width": 14, "align": "right"},
            {"key": "out_of_order_rooms", "header": "OOO / Maint", "width": 14, "align": "right"},
            {"key": "sellable_rooms", "header": "Sellable Rooms", "width": 14, "align": "right"},
            {"key": "rooms_sold", "header": "Rooms Sold", "width": 14, "align": "right"},
            {"key": "rooms_available", "header": "Rooms Vacant", "width": 14, "align": "right"},
            {"key": "occupancy_rate_percent", "header": "Occupancy %", "width": 14, "align": "right", "format": "0.0%"},
        ]
        rows = []
        for it in data.items:
            d = it.model_dump()
            d["occupancy_rate_percent"] = d["occupancy_rate_percent"] / 100.0
            rows.append(d)

        totals = {
            "stay_date": "Average / Total",
            "sellable_rooms": data.total_room_nights_available,
            "rooms_sold": data.total_room_nights_sold,
            "occupancy_rate_percent": data.average_occupancy_percent / 100.0,
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Daily Occupancy Summary",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | Avg Occupancy: {data.average_occupancy_percent}%",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Occupancy_Report",
        )
        return _stream_excel(stream, f"occupancy_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/revenue-summary", response_model=RevenueSummaryReportResponse)
async def get_revenue_summary(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Daily revenue breakdown (room, service, taxes, total)."""
    data = await report_service.get_revenue_summary(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "business_date", "header": "Business Date", "width": 16},
            {"key": "rooms_sold", "header": "Rooms Sold", "width": 12, "align": "right"},
            {"key": "room_revenue", "header": "Room Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "service_revenue", "header": "Service Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "tax_amount", "header": "Tax Collected", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "gross_revenue", "header": "Gross Revenue", "width": 18, "align": "right", "format": "#,##0.00"},
        ]
        rows = [it.model_dump() for it in data.items]
        totals = {
            "business_date": "Total Revenue",
            "room_revenue": float(data.total_room_revenue),
            "service_revenue": float(data.total_service_revenue),
            "tax_amount": float(data.total_tax_amount),
            "gross_revenue": float(data.total_gross_revenue),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Daily Revenue Summary Report",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} ({data.currency})",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Revenue_Summary",
        )
        return _stream_excel(stream, f"revenue_summary_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/adr-revpar", response_model=ADRRevPARReportResponse)
async def get_adr_revpar(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """ADR (Average Daily Rate) and RevPAR performance metrics."""
    data = await report_service.get_adr_revpar(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "business_date", "header": "Date", "width": 14},
            {"key": "sellable_rooms", "header": "Sellable Rooms", "width": 14, "align": "right"},
            {"key": "rooms_sold", "header": "Rooms Sold", "width": 12, "align": "right"},
            {"key": "occupancy_percent", "header": "Occupancy %", "width": 14, "align": "right", "format": "0.0%"},
            {"key": "room_revenue", "header": "Room Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "adr", "header": "ADR", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "revpar", "header": "RevPAR", "width": 14, "align": "right", "format": "#,##0.00"},
        ]
        rows = []
        for it in data.items:
            d = it.model_dump()
            d["occupancy_percent"] = d["occupancy_percent"] / 100.0
            rows.append(d)

        totals = {
            "business_date": "Overall Period",
            "occupancy_percent": data.average_occupancy_percent / 100.0,
            "adr": data.overall_adr,
            "revpar": data.overall_revpar,
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Hotel KPIs: ADR & RevPAR Report",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | ADR: {data.overall_adr} | RevPAR: {data.overall_revpar}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="ADR_RevPAR",
        )
        return _stream_excel(stream, f"adr_revpar_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/outstanding-balances", response_model=OutstandingBalancesReportResponse)
async def get_outstanding_balances(
    property_id: str,
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Open folios with unpaid balances and aging."""
    data = await report_service.get_outstanding_balances(db, property_id=property_id)

    if export == "excel":
        columns = [
            {"key": "folio_number", "header": "Folio #", "width": 16},
            {"key": "folio_type", "header": "Folio Type", "width": 14},
            {"key": "guest_name", "header": "Guest / Company", "width": 24},
            {"key": "room_number", "header": "Room", "width": 10},
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "check_out_date", "header": "Check-out Date", "width": 16},
            {"key": "aging_bucket", "header": "Aging", "width": 14, "align": "center"},
            {"key": "total_charges", "header": "Total Debits", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "total_payments", "header": "Total Paid", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "balance_due", "header": "Outstanding Balance", "width": 18, "align": "right", "format": "#,##0.00"},
        ]
        rows = [it.model_dump() for it in data.items]
        totals = {
            "folio_number": f"Open Folios: {data.total_open_folios}",
            "balance_due": float(data.total_balance_due),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Open Folios & Outstanding Balance Aging",
            property_name=data.property_name,
            date_range_label=f"Total Unpaid: {data.currency} {data.total_balance_due:,.2f}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Outstanding_Balances",
        )
        return _stream_excel(stream, "outstanding_balances_report")

    return data


@router.get("/payments-collection", response_model=PaymentsReportResponse)
async def get_payments_cash_collection(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    payment_method_id: Optional[str] = Query(None, description="Filter by payment method"),
    received_by: Optional[str] = Query(None, description="Filter by cashier user"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Desk reconciliation report: payments collected by mode, cashier and date."""
    data = await report_service.get_payments_cash_collection(
        db,
        property_id=property_id,
        from_date=from_date,
        to_date=to_date,
        payment_method_id=payment_method_id,
        received_by=received_by,
    )

    if export == "excel":
        columns = [
            {"key": "received_at", "header": "Timestamp", "width": 18},
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "guest_name", "header": "Guest Name", "width": 22},
            {"key": "payment_method_name", "header": "Payment Method", "width": 16},
            {"key": "payment_method_type", "header": "Mode", "width": 12},
            {"key": "amount", "header": "Amount", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "received_by_name", "header": "Cashier", "width": 18},
            {"key": "notes", "header": "Notes", "width": 24},
        ]
        rows = [it.model_dump() for it in data.items]
        totals = {
            "booking_number": f"Transactions: {len(data.items)}",
            "amount": float(data.total_amount_collected),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Daily Cash & Payment Reconciliation Report",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | Total: {data.currency} {data.total_amount_collected:,.2f}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Payment_Collections",
        )
        return _stream_excel(stream, f"payments_{data.from_date}_to_{data.to_date}")

    return data


# ─── TIER 3: COMPLIANCE & CONTROL ──────────────────────────────────────────

@router.get("/tax-report", response_model=TaxReportResponse)
async def get_tax_report(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Tax breakdown from immutable transaction snapshots for tax filing."""
    data = await report_service.get_tax_report(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "tax_name", "header": "Tax Name / Slab", "width": 24},
            {"key": "rate", "header": "Tax Rate %", "width": 14, "align": "right", "format": "0.00%"},
            {"key": "transaction_count", "header": "Txn Count", "width": 12, "align": "right"},
            {"key": "taxable_amount", "header": "Taxable Amount", "width": 18, "align": "right", "format": "#,##0.00"},
            {"key": "tax_amount", "header": "Tax Collected", "width": 18, "align": "right", "format": "#,##0.00"},
        ]
        rows = []
        for it in data.items:
            d = it.model_dump()
            d["rate"] = float(d["rate"]) / 100.0
            rows.append(d)

        totals = {
            "tax_name": "Total Tax Liability",
            "taxable_amount": float(data.total_taxable_amount),
            "tax_amount": float(data.total_tax_amount),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Tax Liability & Filing Report (Snapshot Audit)",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | Total Tax: {data.currency} {data.total_tax_amount:,.2f}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Tax_Report",
        )
        return _stream_excel(stream, f"tax_report_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/cancellations-noshows", response_model=CancellationReportResponse)
async def get_cancellations_noshows(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Cancellations, no-shows, projected lost revenue, and fee recovery."""
    data = await report_service.get_cancellations_noshows(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "booking_number", "header": "Booking #", "width": 16},
            {"key": "status", "header": "Status", "width": 14},
            {"key": "guest_name", "header": "Guest Name", "width": 24},
            {"key": "booked_at", "header": "Booked At", "width": 16},
            {"key": "cancelled_at", "header": "Cancelled At", "width": 16},
            {"key": "check_in_at", "header": "Arrival Date", "width": 16},
            {"key": "lost_revenue", "header": "Lost Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "fees_charged", "header": "Retention Fees", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "cancellation_reason", "header": "Reason", "width": 30},
        ]
        rows = [it.model_dump() for it in data.items]
        totals = {
            "booking_number": f"Cancellations: {data.total_cancellations} | No-Shows: {data.total_no_shows}",
            "lost_revenue": float(data.total_lost_revenue),
            "fees_charged": float(data.total_fees_charged),
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Cancellations & No-Shows Loss Analysis",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | Total Lost: {data.currency} {data.total_lost_revenue:,.2f}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Cancellations_NoShows",
        )
        return _stream_excel(stream, f"cancellations_{data.from_date}_to_{data.to_date}")

    return data


# ─── AUDIT (DAY-END) & GUEST REPORTS ──────────────────────────────────────────

@router.get("/night-audit-summary", response_model=NightAuditReportResponse)
async def get_night_audit_summary(
    property_id: str,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Locked day-end managerial trial balance snapshots per property."""
    data = await report_service.get_night_audit_summary_report(
        db, property_id=property_id, from_date=from_date, to_date=to_date
    )

    if export == "excel":
        columns = [
            {"key": "business_date", "header": "Business Date", "width": 14},
            {"key": "total_rooms", "header": "Total Rooms", "width": 12, "align": "right"},
            {"key": "rooms_available", "header": "Sellable", "width": 12, "align": "right"},
            {"key": "rooms_sold", "header": "Rooms Sold", "width": 12, "align": "right"},
            {"key": "occupancy_rate_percent", "header": "Occupancy %", "width": 14, "align": "right", "format": "0.0%"},
            {"key": "room_revenue", "header": "Room Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "service_revenue", "header": "Service Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "tax_revenue", "header": "Tax Collected", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "total_revenue", "header": "Total Revenue", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "adr", "header": "ADR", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "revpar", "header": "RevPAR", "width": 14, "align": "right", "format": "#,##0.00"},
            {"key": "total_payments_collected", "header": "Collections", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "no_shows_marked", "header": "No-Shows", "width": 10, "align": "center"},
        ]
        rows = []
        for it in data.items:
            d = it.model_dump()
            d["occupancy_rate_percent"] = d["occupancy_rate_percent"] / 100.0
            rows.append(d)

        stream = excel_export_service.generate_report_workbook(
            report_title="Night Audit Day-End Summary (Locked History)",
            property_name=data.property_name,
            date_range_label=f"From: {data.from_date} To: {data.to_date} | Total Audited Days: {data.total_audited_days}",
            columns=columns,
            rows=rows,
            sheet_name="Night_Audit_Summary",
        )
        return _stream_excel(stream, f"night_audit_summary_{data.from_date}_to_{data.to_date}")

    return data


@router.get("/guest-history", response_model=GuestHistoryReportResponse)
async def get_guest_history_report(
    property_id: str,
    limit: int = Query(100, ge=1, le=500),
    export: Optional[str] = Query(None, description="Set to 'excel' to download .xlsx"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Guest history, lifetime spend, and repeat guest frequency."""
    data = await report_service.get_guest_history_report(
        db, property_id=property_id, limit=limit
    )

    if export == "excel":
        columns = [
            {"key": "guest_name", "header": "Guest Name", "width": 24},
            {"key": "email", "header": "Email", "width": 24},
            {"key": "phone", "header": "Phone", "width": 16},
            {"key": "city", "header": "City", "width": 16},
            {"key": "total_bookings", "header": "Total Bookings", "width": 14, "align": "center"},
            {"key": "completed_stays", "header": "Completed Stays", "width": 14, "align": "center"},
            {"key": "total_nights", "header": "Total Nights", "width": 12, "align": "center"},
            {"key": "total_spent", "header": "Total Spent", "width": 16, "align": "right", "format": "#,##0.00"},
            {"key": "is_repeat_guest", "header": "Repeat Guest", "width": 14, "align": "center"},
            {"key": "last_visit", "header": "Last Visit", "width": 16},
        ]
        rows = [it.model_dump() for it in data.items]
        totals = {
            "guest_name": f"Tracked: {data.total_guests_tracked} | Repeat: {data.repeat_guests_count}",
        }
        stream = excel_export_service.generate_report_workbook(
            report_title="Guest History & Repeat Profiles",
            property_name=data.property_name,
            date_range_label=f"Total Guests: {data.total_guests_tracked} | Repeat Guests: {data.repeat_guests_count}",
            columns=columns,
            rows=rows,
            summary_totals=totals,
            sheet_name="Guest_History",
        )
        return _stream_excel(stream, "guest_history_report")

    return data
