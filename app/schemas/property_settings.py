from datetime import datetime, time
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


from app.schemas.night_audit import NightAuditConfig


class PropertySettingsBase(BaseModel):
    date_format: str = Field(default="DD/MM/YYYY", description="Date display format")
    time_format: str = Field(default="24H", description="12H or 24H")
    language: str = Field(default="en", description="Default language code")
    number_format: str = Field(default="en-IN", description="Number/currency formatting style")
    week_start_day: int = Field(default=1, ge=0, le=6, description="0 = Sunday, 1 = Monday, etc.")
    night_audit_mode: str = Field(default="MANUAL", description="AUTO or MANUAL")
    night_audit_time: time = Field(default=time(2, 0), description="Local time the day rolls over")
    night_audit_config: Optional[NightAuditConfig] = Field(
        default_factory=NightAuditConfig, description="Detailed night audit execution rules"
    )
    same_day_checkout_rule: str = Field(default="FULL_NIGHT", description="FULL_NIGHT, PARTIAL, or DAY_USE")
    invoice_prefix: Optional[str] = Field(None, description="Prefix for generated invoices (e.g. INV-)")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Unstructured extra settings")


class PropertySettingsCreate(PropertySettingsBase):
    property_id: Optional[str] = None


class PropertySettingsUpdate(BaseModel):
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    language: Optional[str] = None
    number_format: Optional[str] = None
    week_start_day: Optional[int] = Field(None, ge=0, le=6)
    night_audit_mode: Optional[str] = Field(None, description="AUTO or MANUAL")
    night_audit_time: Optional[time] = None
    night_audit_config: Optional[NightAuditConfig] = None
    same_day_checkout_rule: Optional[str] = None
    invoice_prefix: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class PropertySettingsResponse(PropertySettingsBase):
    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
