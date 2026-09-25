from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PropertyBookingSettingsBase(BaseModel):
    nightly_booking_enabled: bool = True
    hourly_booking_enabled: bool = False
    minimum_hourly_duration: int = Field(default=1, ge=1)
    maximum_hourly_duration: int = Field(default=24, ge=1)
    hourly_booking_buffer_minutes: int = Field(default=0, ge=0)
    same_day_booking_enabled: bool = True
    check_in_time: time = Field(default=time(14, 0), examples=["14:00:00"])
    check_out_time: time = Field(default=time(11, 0), examples=["11:00:00"])


class PropertyBookingSettingsCreate(PropertyBookingSettingsBase):
    property_id: Optional[str] = None


class PropertyBookingSettingsUpdate(BaseModel):
    nightly_booking_enabled: Optional[bool] = None
    hourly_booking_enabled: Optional[bool] = None
    minimum_hourly_duration: Optional[int] = Field(None, ge=1)
    maximum_hourly_duration: Optional[int] = Field(None, ge=1)
    hourly_booking_buffer_minutes: Optional[int] = Field(None, ge=0)
    same_day_booking_enabled: Optional[bool] = None
    check_in_time: Optional[time] = None
    check_out_time: Optional[time] = None


class PropertyBookingSettingsResponse(PropertyBookingSettingsBase):
    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
