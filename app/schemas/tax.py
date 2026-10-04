from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import EntityStatus, TaxAppliesTo, TaxRateType


# ─── Tax Rate Schemas ────────────────────────────────────────────────────────

class TaxRateBase(BaseModel):
    rate_type: TaxRateType = TaxRateType.PERCENTAGE
    rate: Decimal = Field(..., ge=0, examples=[6.0000])
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, ge=0)
    valid_from: date = Field(default_factory=date.today)
    valid_to: Optional[date] = None


class TaxRateCreate(TaxRateBase):
    tax_id: Optional[str] = None


class TaxRateResponse(TaxRateBase):
    id: str
    tax_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Tax Schemas ─────────────────────────────────────────────────────────────

class TaxBase(BaseModel):
    name: str = Field(..., min_length=1, examples=["CGST"])
    code: str = Field(..., min_length=1, examples=["CGST"])
    status: EntityStatus = EntityStatus.ACTIVE


class TaxCreate(TaxBase):
    organization_id: Optional[str] = None
    rate: Optional[Decimal] = Field(None, ge=0, examples=[6.0000])
    rate_type: TaxRateType = TaxRateType.PERCENTAGE
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class TaxUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[EntityStatus] = None
    rate: Optional[Decimal] = Field(None, ge=0)
    rate_type: Optional[TaxRateType] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class TaxResponse(TaxBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime
    rates: List[TaxRateResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ─── Tax Group Item Schemas ──────────────────────────────────────────────────

class TaxGroupItemCreate(BaseModel):
    tax_id: str
    sequence: int = 1
    is_compound: bool = False


class TaxGroupItemResponse(BaseModel):
    id: str
    tax_group_id: str
    tax_id: str
    sequence: int
    is_compound: bool
    tax: Optional[TaxResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Tax Group Schemas ───────────────────────────────────────────────────────

class TaxGroupBase(BaseModel):
    name: str = Field(..., min_length=1, examples=["GST - Room 12%"])
    code: str = Field(..., min_length=1, examples=["GST_ROOM_12"])
    applies_to: TaxAppliesTo = TaxAppliesTo.ROOM
    status: EntityStatus = EntityStatus.ACTIVE


class TaxGroupCreate(TaxGroupBase):
    organization_id: Optional[str] = None
    items: List[TaxGroupItemCreate] = []


class TaxGroupUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    applies_to: Optional[TaxAppliesTo] = None
    status: Optional[EntityStatus] = None
    items: Optional[List[TaxGroupItemCreate]] = None


class TaxGroupSimpleResponse(TaxGroupBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaxGroupResponse(TaxGroupBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime
    items: List[TaxGroupItemResponse] = []

    model_config = ConfigDict(from_attributes=True)

