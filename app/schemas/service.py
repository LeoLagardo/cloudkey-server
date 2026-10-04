from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import EntityStatus, PricingType, ServiceCategory


class TaxGroupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    applies_to: str
    status: str


class ServiceCategorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    system_type: str
    parent_id: Optional[str] = None
    default_tax_group_id: Optional[str] = None
    default_hsn_sac_code: Optional[str] = None


class ServiceCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    parent_id: Optional[str] = None
    system_type: str = Field(default=ServiceCategory.OTHER.value)
    description: Optional[str] = None
    default_tax_group_id: Optional[str] = None
    default_hsn_sac_code: Optional[str] = None
    sort_order: int = 0
    status: str = Field(default=EntityStatus.ACTIVE.value)


class ServiceCategoryCreate(ServiceCategoryBase):
    pass


class ServiceCategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    parent_id: Optional[str] = None
    system_type: Optional[str] = None
    description: Optional[str] = None
    default_tax_group_id: Optional[str] = None
    default_hsn_sac_code: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class ServiceSubCategoryResponse(ServiceCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime
    default_tax_group: Optional[TaxGroupSummary] = None


class ServiceCategoryResponse(ServiceCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime
    default_tax_group: Optional[TaxGroupSummary] = None
    sub_categories: List[ServiceSubCategoryResponse] = []


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    category_id: Optional[str] = None
    category: str = Field(default=ServiceCategory.OTHER.value)
    pricing_type: str = Field(default=PricingType.FIXED.value)
    default_price: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    tax_group_id: Optional[str] = None
    is_tax_inclusive: bool = False
    hsn_sac_code: Optional[str] = None
    status: str = Field(default=EntityStatus.ACTIVE.value)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    category_id: Optional[str] = None
    category: Optional[str] = None
    pricing_type: Optional[str] = None
    default_price: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    tax_group_id: Optional[str] = None
    is_tax_inclusive: Optional[bool] = None
    hsn_sac_code: Optional[str] = None
    status: Optional[str] = None


class ServiceResponse(ServiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    created_at: datetime
    updated_at: datetime
    tax_group: Optional[TaxGroupSummary] = None
    service_category: Optional[ServiceCategorySummary] = None
