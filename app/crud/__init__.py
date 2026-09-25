from app.crud.base import CRUDBase
from app.crud.organization import crud_organization, CRUDOrganization
from app.crud.property import crud_property, CRUDProperty
from app.crud.room_type import crud_room_type, CRUDRoomType
from app.crud.room import crud_room, CRUDRoom
from app.crud.rate_plan import crud_rate_plan, CRUDRatePlan
from app.crud.rate_plan_rate import crud_rate_plan_rate, CRUDRatePlanRate
from app.crud.property_booking_settings import (
    crud_property_booking_settings,
    CRUDPropertyBookingSettings,
)
from app.crud.property_settings import (
    crud_property_settings,
    CRUDPropertySettings,
)
from app.crud.role import crud_role, CRUDRole, crud_permission, CRUDPermission
from app.crud.organization_user import crud_organization_user, CRUDOrganizationUser
from app.crud.property_user import crud_property_user, CRUDPropertyUser
from app.crud.user import crud_user, CRUDUser
from app.crud.tax import (
    crud_tax,
    CRUDTax,
    crud_tax_rate,
    CRUDTaxRate,
    crud_tax_group,
    CRUDTaxGroup,
    crud_tax_group_item,
    CRUDTaxGroupItem,
)

__all__ = [
    "CRUDBase",
    "crud_organization",
    "CRUDOrganization",
    "crud_property",
    "CRUDProperty",
    "crud_room_type",
    "CRUDRoomType",
    "crud_room",
    "CRUDRoom",
    "crud_rate_plan",
    "CRUDRatePlan",
    "crud_rate_plan_rate",
    "CRUDRatePlanRate",
    "crud_property_booking_settings",
    "CRUDPropertyBookingSettings",
    "crud_property_settings",
    "CRUDPropertySettings",
    "crud_role",
    "CRUDRole",
    "crud_permission",
    "CRUDPermission",
    "crud_organization_user",
    "CRUDOrganizationUser",
    "crud_property_user",
    "CRUDPropertyUser",
    "crud_user",
    "CRUDUser",
    "crud_tax",
    "CRUDTax",
    "crud_tax_rate",
    "CRUDTaxRate",
    "crud_tax_group",
    "CRUDTaxGroup",
    "crud_tax_group_item",
    "CRUDTaxGroupItem",
]
