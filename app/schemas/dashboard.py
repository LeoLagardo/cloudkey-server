from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class PropertyBrief(BaseModel):
    id: str
    name: str
    code: str
    city: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"
    business_date: date

    model_config = ConfigDict(from_attributes=True)


class ShiftSessionInfo(BaseModel):
    shift_name: str
    date_formatted: str
    business_date: date
    audit_status: str
    temperature_celsius: int = 28
    weather_condition: str = "Pleasant"


class DashboardKPIs(BaseModel):
    arrivals_total: int
    arrivals_checked_in: int
    arrivals_pending: int
    arrivals_subtext: str

    departures_total: int
    departures_checked_out: int
    departures_pending: int
    departures_subtext: str

    in_house_count: int
    in_house_rooms_count: int
    in_house_subtext: str

    available_rooms_count: int
    total_rooms_count: int
    available_subtext: str

    occupancy_rate: float
    occupancy_subtext: str
    occupancy_trend_up: bool

    revenue_today: str
    revenue_paid_today: str
    revenue_pending_today: str
    revenue_subtext: str


class ArrivalGuestItem(BaseModel):
    id: str
    booking_number: str
    guest_id: str
    name: str
    is_verified: bool
    is_vip: bool
    res_code: str
    adults: int
    children: int
    room_reservation_id: Optional[str] = None
    room_id: Optional[str] = None
    room_number: str
    room_category: str
    room_status_note: str
    room_status_type: str  # 'dirty' | 'ready' | 'vip'
    eta: str
    eta_note: str
    folio_total: str
    folio_id: Optional[str] = None
    payment_status: str  # 'paid' | 'partial' | 'unpaid'
    payment_text: str
    action_text: str  # 'Check In' | 'Collect & In'
    action_type: str  # 'checkin' | 'collect'
    reservation_status: str


class DepartureGuestItem(BaseModel):
    id: str
    booking_number: str
    guest_id: str
    name: str
    keycards_count: int
    late_checkout_time: Optional[str] = None
    room_number: str
    status_note_primary: str
    status_note_secondary: str
    folio_balance: str
    folio_id: Optional[str] = None
    status: str  # 'zero' | 'pending'
    status_text: str
    action_text: str  # 'Check Out' | 'Settle & Out'
    action_type: str  # 'checkout' | 'settle'
    reservation_status: str


class RoomInventorySummary(BaseModel):
    available: int
    occupied: int
    dirty: int
    out_of_service: int
    total: int


class TapeRoomItem(BaseModel):
    id: str
    number: str
    floor: Optional[str] = None
    type: str
    room_type_name: str
    status: str
    dot_color: str  # 'ready' | 'occ' | 'dirty' | 'vip' | 'oos'
    is_alert: bool = False


class HousekeepingPriorityAlert(BaseModel):
    room_id: str
    room_number: str
    guest_name: str
    reservation_id: str
    room_reservation_id: Optional[str] = None
    eta: str
    message: str


class OccupancyDayTrend(BaseModel):
    day: str
    date: str
    occupied_count: int
    total_count: int
    percentage: int
    is_today: bool = False
    is_peak: bool = False


class DashboardSummaryResponse(BaseModel):
    property: PropertyBrief
    session: ShiftSessionInfo
    kpis: DashboardKPIs
    arrivals: List[ArrivalGuestItem]
    departures: List[DepartureGuestItem]
    room_inventory: RoomInventorySummary
    tape_rooms: List[TapeRoomItem]
    housekeeping_alert: Optional[HousekeepingPriorityAlert] = None
    occupancy_trend: List[OccupancyDayTrend]
    occupancy_average: float

    model_config = ConfigDict(from_attributes=True)
