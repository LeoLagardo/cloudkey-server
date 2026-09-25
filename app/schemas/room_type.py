from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import EntityStatus


class RoomTypeBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Deluxe Ocean View"])
    code: str = Field(..., min_length=1, examples=["DOV"])
    description: Optional[str] = None
    max_occupancy: int = Field(default=1, ge=1)
    base_occupancy: int = Field(default=1, ge=1)
    status: EntityStatus = Field(default=EntityStatus.ACTIVE)


class RoomTypeCreate(RoomTypeBase):
    property_id: Optional[str] = None


class RoomTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    code: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    max_occupancy: Optional[int] = Field(None, ge=1)
    base_occupancy: Optional[int] = Field(None, ge=1)
    status: Optional[EntityStatus] = None


class RoomTypeResponse(RoomTypeBase):
    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
