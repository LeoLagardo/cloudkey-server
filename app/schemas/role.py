from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import RoleScope


# Permission schemas
class PermissionBase(BaseModel):
    code: str = Field(..., min_length=2, examples=["rooms:read"])
    name: str = Field(..., min_length=2, examples=["View Rooms"])
    module: str = Field(..., min_length=2, examples=["ROOMS"])
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionResponse(PermissionBase):
    id: str

    model_config = ConfigDict(from_attributes=True)


# Role schemas
class RoleBase(BaseModel):
    name: str = Field(..., min_length=2, examples=["Property Manager"])
    scope: RoleScope = Field(default=RoleScope.ORGANIZATION)
    is_system: bool = False


class RoleCreate(RoleBase):
    organization_id: Optional[str] = None
    permission_ids: Optional[List[str]] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    scope: Optional[RoleScope] = None
    permission_ids: Optional[List[str]] = None


class RoleResponse(RoleBase):
    id: str
    organization_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    permissions: List[PermissionResponse] = []

    model_config = ConfigDict(from_attributes=True)
