from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.utils.enums import UserMembershipStatus


class OrganizationUserBase(BaseModel):
    user_id: str
    role_id: str
    status: UserMembershipStatus = UserMembershipStatus.ACTIVE


class OrganizationUserCreate(OrganizationUserBase):
    organization_id: Optional[str] = None


class OrganizationUserUpdate(BaseModel):
    role_id: Optional[str] = None
    status: Optional[UserMembershipStatus] = None


class OrganizationUserResponse(OrganizationUserBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
