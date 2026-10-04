from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.utils.enums import RoomBlockType


class RoomBlockBase(BaseModel):
    room_id: str
    block_type: RoomBlockType = RoomBlockType.OUT_OF_ORDER
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None


class RoomBlockCreate(RoomBlockBase):
    pass


class RoomBlockUpdate(BaseModel):
    block_type: Optional[RoomBlockType] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    reason: Optional[str] = None


class RoomBlockResponse(RoomBlockBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    created_by: Optional[str] = None
    created_at: datetime
