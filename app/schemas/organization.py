from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import OrganizationStatus


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Grand Palace Hospitality"])
    slug: str = Field(..., min_length=2, examples=["grand-palace"])
    status: OrganizationStatus = Field(default=OrganizationStatus.ACTIVE)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    slug: Optional[str] = Field(None, min_length=2)
    status: Optional[OrganizationStatus] = None


class OrganizationResponse(OrganizationBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
