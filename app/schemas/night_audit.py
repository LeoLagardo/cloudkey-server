from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NightAuditConfig(BaseModel):
    auto_no_show: bool = Field(default=True, description="Auto-mark unarrived confirmed bookings as NO_SHOW")
    auto_checkout: bool = Field(default=False, description="Auto-checkout zero-balance departures")
    auto_checkout_unsettled_action: str = Field(
        default="ROLLOVER",
        description="Action for departures with outstanding balance: 'ROLLOVER' (carry stay charges) or 'BLOCK' (block audit)",
    )
    require_cashier_closure: bool = Field(default=False, description="Require all cashier shifts to be closed before audit")
    post_room_charges: bool = Field(default=True, description="Post daily room rate and taxes to guest folios")
    notification_emails: List[str] = Field(default_factory=list, description="Emails to send daily manager report to")

    model_config = ConfigDict(from_attributes=True)


class PreAuditArrivalItem(BaseModel):
    reservation_id: str
    booking_number: str
    guest_name: str
    check_in_at: datetime
    check_out_at: datetime
    room_type_name: Optional[str] = None
    room_number: Optional[str] = None


class PreAuditDepartureItem(BaseModel):
    reservation_id: str
    booking_number: str
    guest_name: str
    check_in_at: datetime
    check_out_at: datetime
    room_number: Optional[str] = None
    balance_due: Decimal = Decimal("0.00")


class PreAuditRoomPostingItem(BaseModel):
    reservation_id: str
    reservation_room_id: str
    room_number: Optional[str] = None
    guest_name: str
    rate_plan_name: Optional[str] = None
    net_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class PreAuditCheckResponse(BaseModel):
    property_id: str
    business_date: date
    next_business_date: date
    scheduled_time: str
    night_audit_mode: str
    pending_arrivals: List[PreAuditArrivalItem] = []
    pending_departures: List[PreAuditDepartureItem] = []
    rooms_to_post: List[PreAuditRoomPostingItem] = []
    total_projected_room_revenue: Decimal = Decimal("0.00")
    total_projected_tax: Decimal = Decimal("0.00")
    can_run: bool = True
    warnings: List[str] = []


class NightAuditRunRequest(BaseModel):
    auto_no_show: Optional[bool] = Field(
        None, description="If None, defaults to property setting night_audit_auto_no_show"
    )
    allow_pending_departure_rollover: bool = Field(
        default=False,
        description="Allow proceeding even if overdue departures exist by carrying stayover charges",
    )
    notes: Optional[str] = None


class NightAuditResponse(BaseModel):
    id: str
    property_id: str
    business_date: date
    status: str
    rooms_posted: int = 0
    no_shows_marked: int = 0
    trigger_type: str = "MANUAL"
    error_message: Optional[str] = None
    run_by: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    summary_data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class NightAuditStatusResponse(BaseModel):
    property_id: str
    business_date: date
    night_audit_mode: str
    night_audit_time: str
    timezone: str
    is_audit_running: bool = False
    last_audit: Optional[NightAuditResponse] = None
    can_run_audit: bool = True
    next_scheduled_run: Optional[str] = None
