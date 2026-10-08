from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


# ─── TIER 1: OPERATIONAL REPORT SCHEMAS ────────────────────────────────────────

class ArrivalDepartureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: str
    booking_number: str
    movement_type: str  # ARRIVAL or DEPARTURE
    guest_name: str
    guest_phone: Optional[str] = None
    guest_email: Optional[str] = None
    room_number: Optional[str] = None
    room_type_name: str
    check_in_at: datetime
    check_out_at: datetime
    nights: int
    adults: int
    children: int
    status: str
    total_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    special_requests: Optional[str] = None


class ArrivalDepartureReportResponse(BaseModel):
    property_id: str
    property_name: str
    target_date: date
    filter_type: str  # ALL, ARRIVALS, DEPARTURES
    currency: str
    total_arrivals: int
    total_departures: int
    total_balance_due: Decimal
    items: List[ArrivalDepartureItem]


class InHouseGuestItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: str
    booking_number: str
    room_number: str
    room_type_name: str
    floor: Optional[str] = None
    guest_name: str
    guest_phone: Optional[str] = None
    adults: int
    children: int
    check_in_at: datetime
    check_out_at: datetime
    stay_nights: int
    nights_spent: int
    nights_remaining: int
    folio_id: Optional[str] = None
    total_debits: Decimal
    total_credits: Decimal
    balance_due: Decimal
    status: str


class InHouseReportResponse(BaseModel):
    property_id: str
    property_name: str
    as_of_date: date
    currency: str
    total_in_house_rooms: int
    total_guests: int
    total_outstanding_balance: Decimal
    items: List[InHouseGuestItem]


class RoomAvailabilityTypeDay(BaseModel):
    stay_date: date
    room_type_id: str
    room_type_name: str
    total_rooms: int
    sold_rooms: int
    blocked_rooms: int
    maintenance_rooms: int
    available_rooms: int
    occupancy_percent: float


class RoomAvailabilityReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    total_physical_rooms: int
    items: List[RoomAvailabilityTypeDay]


class BookingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: str
    booking_number: str
    booked_at: datetime
    guest_name: str
    guest_phone: Optional[str] = None
    source: str
    channel_name: Optional[str] = None
    room_type_name: str
    room_number: Optional[str] = None
    rate_plan_name: Optional[str] = None
    check_in_at: datetime
    check_out_at: datetime
    nights: int
    status: str
    total_amount: Decimal
    total_tax_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal


class BookingListReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    currency: str
    total_bookings: int
    total_gross_value: Decimal
    total_balance_outstanding: Decimal
    items: List[BookingListItem]


# ─── TIER 2: FINANCIAL REPORT SCHEMAS ──────────────────────────────────────────

class OccupancyDayItem(BaseModel):
    stay_date: date
    total_rooms: int
    out_of_order_rooms: int
    sellable_rooms: int
    rooms_sold: int
    rooms_available: int
    occupancy_rate_percent: float


class OccupancyReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    average_occupancy_percent: float
    total_room_nights_available: int
    total_room_nights_sold: int
    items: List[OccupancyDayItem]


class RevenueDayItem(BaseModel):
    business_date: date
    room_revenue: Decimal
    service_revenue: Decimal
    tax_amount: Decimal
    gross_revenue: Decimal
    rooms_sold: int


class RevenueSummaryReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    total_room_revenue: Decimal
    total_service_revenue: Decimal
    total_tax_amount: Decimal
    total_gross_revenue: Decimal
    items: List[RevenueDayItem]


class ADRRevPARDayItem(BaseModel):
    business_date: date
    sellable_rooms: int
    rooms_sold: int
    room_revenue: Decimal
    adr: float
    revpar: float
    occupancy_percent: float


class ADRRevPARReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    overall_adr: float
    overall_revpar: float
    average_occupancy_percent: float
    items: List[ADRRevPARDayItem]


class OutstandingFolioItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    folio_id: str
    folio_number: str
    folio_type: str
    status: str
    reservation_id: Optional[str] = None
    booking_number: Optional[str] = None
    guest_name: str
    room_number: Optional[str] = None
    check_out_date: Optional[date] = None
    opened_at: datetime
    total_charges: Decimal
    total_payments: Decimal
    balance_due: Decimal
    aging_bucket: str  # 0-30 days, 31-60 days, 60+ days


class OutstandingBalancesReportResponse(BaseModel):
    property_id: str
    property_name: str
    currency: str
    total_open_folios: int
    total_balance_due: Decimal
    items: List[OutstandingFolioItem]


class PaymentCollectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    received_at: datetime
    booking_number: Optional[str] = None
    guest_name: str
    payment_method_name: str
    payment_method_type: str
    payment_type: str
    amount: Decimal
    received_by_name: str
    notes: Optional[str] = None


class PaymentsReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    total_amount_collected: Decimal
    by_payment_method: Dict[str, Decimal]
    items: List[PaymentCollectionItem]


# ─── TIER 3: COMPLIANCE & CONTROL SCHEMAS ──────────────────────────────────────

class TaxBreakdownItem(BaseModel):
    tax_name: str
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    transaction_count: int


class TaxReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    total_taxable_amount: Decimal
    total_tax_amount: Decimal
    items: List[TaxBreakdownItem]


class CancellationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: str
    booking_number: str
    booked_at: datetime
    cancelled_at: Optional[datetime] = None
    status: str  # CANCELLED or NO_SHOW
    guest_name: str
    check_in_at: datetime
    check_out_at: datetime
    lost_revenue: Decimal
    fees_charged: Decimal
    cancellation_reason: Optional[str] = None


class CancellationReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    total_cancellations: int
    total_no_shows: int
    total_lost_revenue: Decimal
    total_fees_charged: Decimal
    items: List[CancellationItem]


# ─── AUDIT (DAY-END) & GUEST REPORTS ──────────────────────────────────────────

class NightAuditSummaryItem(BaseModel):
    business_date: date
    total_rooms: int
    rooms_available: int
    rooms_sold: int
    rooms_ooo: int
    occupancy_rate_percent: float
    room_revenue: Decimal
    service_revenue: Decimal
    tax_revenue: Decimal
    total_revenue: Decimal
    adr: float
    revpar: float
    total_payments_collected: Decimal
    no_shows_marked: int


class NightAuditReportResponse(BaseModel):
    property_id: str
    property_name: str
    from_date: date
    to_date: date
    currency: str
    total_audited_days: int
    items: List[NightAuditSummaryItem]


class GuestHistoryItem(BaseModel):
    guest_id: str
    guest_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    total_bookings: int
    completed_stays: int
    total_nights: int
    total_spent: Decimal
    is_repeat_guest: bool
    last_visit: Optional[datetime] = None


class GuestHistoryReportResponse(BaseModel):
    property_id: str
    property_name: str
    currency: str
    total_guests_tracked: int
    repeat_guests_count: int
    items: List[GuestHistoryItem]
