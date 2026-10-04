from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    room_type_id: str
    stay_date: date
    total_rooms: int
    blocked_rooms: int
    sold_rooms: int
    overbooking_limit: int
    available: int
    stop_sell: bool
    closed_to_arrival: bool
    closed_to_departure: bool
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    version: int
    updated_at: datetime


class InventoryControlsUpdate(BaseModel):
    room_type_ids: List[str]
    start_date: date
    end_date: date
    stop_sell: Optional[bool] = None
    closed_to_arrival: Optional[bool] = None
    closed_to_departure: Optional[bool] = None
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    overbooking_limit: Optional[int] = None


class InventorySyncResponse(BaseModel):
    property_id: str
    synced_days: int
    message: str
