from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import RoomStatus, OccupancyStatus, HousekeepingStatus
from app.schemas.room_type import RoomTypeResponse


class RoomBase(BaseModel):
    room_number: str = Field(..., min_length=1, examples=["101", "204B"])
    floor: Optional[str] = None
    status: RoomStatus = Field(default=RoomStatus.AVAILABLE)
    occupancy_status: Optional[str] = Field(default=OccupancyStatus.VACANT.value)
    housekeeping_status: Optional[str] = Field(default=HousekeepingStatus.CLEAN.value)


class RoomCreate(RoomBase):
    property_id: Optional[str] = None
    room_type_id: str


class RoomUpdate(BaseModel):
    room_number: Optional[str] = Field(None, min_length=1)
    room_type_id: Optional[str] = None
    floor: Optional[str] = None
    status: Optional[RoomStatus] = None
    occupancy_status: Optional[OccupancyStatus] = None
    housekeeping_status: Optional[HousekeepingStatus] = None


class RoomResponse(RoomBase):
    id: str
    property_id: str
    room_type_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
