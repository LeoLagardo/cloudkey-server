from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.organization import OrganizationResponse
from app.schemas.property import PropertyResponse
from app.schemas.user import UserResponse


class SignupAccountData(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)


class SignupOrganizationData(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)


class SignupPropertyData(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class SignupRequest(BaseModel):
    """
    Onboarding Signup Request.
    Accepts either nested structure:
      {
        "account": { ... },
        "organization": { ... },
        "property": { ... }
      }
    Or flat payload:
      {
        "email": "...",
        "password": "...",
        "full_name": "...",
        "organization_name": "...",
        "property_name": "...",
        ...
      }
    """
    account: SignupAccountData
    organization: SignupOrganizationData
    property: SignupPropertyData

    @model_validator(mode="before")
    @classmethod
    def assemble_signup_data(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # If already nested, return as-is
        if "account" in data and "organization" in data and "property" in data:
            return data

        # Build nested from flat if keys provided at top level
        payload = dict(data)
        account_dict = payload.get("account") or {
            "email": payload.get("email"),
            "password": payload.get("password"),
            "full_name": payload.get("full_name") or payload.get("name"),
            "phone": payload.get("phone"),
        }

        org_name = (
            payload.get("organization_name")
            or payload.get("org_name")
            or (payload.get("organization", {}).get("name") if isinstance(payload.get("organization"), dict) else None)
        )
        org_slug = (
            payload.get("organization_slug")
            or payload.get("org_slug")
            or (payload.get("organization", {}).get("slug") if isinstance(payload.get("organization"), dict) else None)
        )
        org_dict = payload.get("organization") if isinstance(payload.get("organization"), dict) else {
            "name": org_name,
            "slug": org_slug,
        }

        prop_dict = payload.get("property") if isinstance(payload.get("property"), dict) else {
            "name": payload.get("property_name") or payload.get("hotel_name"),
            "code": payload.get("property_code"),
            "address_line_1": payload.get("address_line_1"),
            "address_line_2": payload.get("address_line_2"),
            "city": payload.get("city"),
            "state": payload.get("state"),
            "country": payload.get("country"),
            "postal_code": payload.get("postal_code"),
            "timezone": payload.get("timezone", "Asia/Kolkata"),
            "currency": payload.get("currency", "INR"),
        }

        return {
            "account": account_dict,
            "organization": org_dict,
            "property": prop_dict,
        }


class SignupResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: OrganizationResponse
    property: PropertyResponse
    message: str = "Sign up and initial onboarding completed successfully."

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class AuthMeResponse(BaseModel):
    user: UserResponse
    organizations: List[Dict[str, Any]] = []
    properties: List[Dict[str, Any]] = []
