from datetime import date, time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.property import PropertyResponse
from app.schemas.property_booking_settings import PropertyBookingSettingsResponse
from app.schemas.room import RoomCreate, RoomResponse
from app.schemas.room_type import RoomTypeCreate, RoomTypeResponse
from app.schemas.tax import TaxGroupResponse
from app.utils.enums import BookingType, DurationUnit


class StepProgress(BaseModel):
    name: str
    title: str
    is_completed: bool
    count: int = 0
    details: Optional[Any] = None


class SetupStatusResponse(BaseModel):
    property_id: str
    property_name: str
    property_code: str
    is_setup_completed: bool
    current_step: str
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    classification: Optional[str] = None
    business_date: Optional[date] = None
    gstin: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    steps: Dict[str, StepProgress]


class SetupRoomTypesRequest(BaseModel):
    room_types: List[RoomTypeCreate] = Field(..., min_length=1)


class BulkRoomGroup(BaseModel):
    room_type_id: str
    room_numbers: Optional[List[str]] = None
    prefix: Optional[str] = None
    start_number: Optional[int] = Field(None, ge=1)
    count: Optional[int] = Field(None, ge=1, le=100)
    floor: Optional[str] = None


class SetupRoomsRequest(BaseModel):
    rooms: Optional[List[RoomCreate]] = None
    bulk_groups: Optional[List[BulkRoomGroup]] = None


class SetupRateItem(BaseModel):
    room_type_id: str
    price: float = Field(..., gt=0)
    duration: int = Field(default=1, ge=1)
    duration_unit: DurationUnit = DurationUnit.NIGHT
    min_occupancy: Optional[int] = None
    max_occupancy: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def handle_price_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "price" not in payload and "base_rate" in payload:
                payload["price"] = payload["base_rate"]
            if "occupancy" in payload:
                payload.setdefault("min_occupancy", payload["occupancy"])
                payload.setdefault("max_occupancy", payload["occupancy"])
            return payload
        return data


class SetupRatePlanItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = None
    room_type_id: Optional[str] = None
    booking_type: BookingType = BookingType.NIGHTLY
    description: Optional[str] = None
    currency: str = "INR"
    price: Optional[float] = None
    duration: int = 1
    duration_unit: DurationUnit = DurationUnit.NIGHT
    tax_group_id: Optional[str] = None
    is_tax_inclusive: bool = False
    rates: List[SetupRateItem] = Field(default_factory=list)


class SetupRatePlansRequest(BaseModel):
    rate_plans: List[SetupRatePlanItem] = Field(..., min_length=1)


class TaxSetupItem(BaseModel):
    name: str = Field(..., min_length=1, examples=["CGST"])
    code: str = Field(..., min_length=1, examples=["CGST"])
    rate: float = Field(..., ge=0, examples=[6.0])
    rate_type: str = "PERCENTAGE"


class TaxGroupSetupItem(BaseModel):
    name: str = Field(..., min_length=1, examples=["GST - Room 12%"])
    code: str = Field(..., min_length=1, examples=["GST_ROOM_12"])
    applies_to: str = "ROOM"
    tax_codes: List[str] = Field(..., min_length=1, examples=[["CGST", "SGST"]])
    is_compound: bool = False


class SetupTaxesRequest(BaseModel):
    taxes: List[TaxSetupItem] = Field(default_factory=list)
    tax_groups: List[TaxGroupSetupItem] = Field(default_factory=list)
    apply_to_rate_plans: bool = True
    is_tax_inclusive: bool = False


class SetupBookingSettingsRequest(BaseModel):
    nightly_booking_enabled: bool = True
    hourly_booking_enabled: bool = False
    minimum_hourly_duration: int = Field(default=1, ge=1)
    maximum_hourly_duration: int = Field(default=24, ge=1)
    hourly_booking_buffer_minutes: int = Field(default=0, ge=0)
    same_day_booking_enabled: bool = True
    check_in_time: time = Field(default=time(14, 0))
    check_out_time: time = Field(default=time(11, 0))


class SetupCompleteResponse(BaseModel):
    property_id: str
    is_setup_completed: bool
    current_step: str = "COMPLETED"
    message: str = "Property setup has been successfully completed! PMS Dashboard is now fully operational."
    summary: Dict[str, Any]


class PropertyDashboardResponse(BaseModel):
    property: PropertyResponse
    metrics: Dict[str, Any]
    policies: Dict[str, Any]
    readiness: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)
