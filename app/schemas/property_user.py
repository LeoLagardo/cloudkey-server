from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.utils.enums import UserMembershipStatus


class PropertyUserBase(BaseModel):
    user_id: str
    role_id: str
    status: UserMembershipStatus = UserMembershipStatus.ACTIVE


class PropertyUserCreate(PropertyUserBase):
    property_id: Optional[str] = None


class PropertyUserUpdate(BaseModel):
    role_id: Optional[str] = None
    status: Optional[UserMembershipStatus] = None


class PropertyUserResponse(PropertyUserBase):
    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
