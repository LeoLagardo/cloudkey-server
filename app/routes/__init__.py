from fastapi import APIRouter

from app.routes.organization import router as organization_router
from app.routes.properties import router as properties_router
from app.routes.room_types import router as room_types_router
from app.routes.rooms import router as rooms_router
from app.routes.rate_plans import router as rate_plans_router
from app.routes.taxes import router as taxes_router
from app.routes.property_booking_settings import router as booking_settings_router
from app.routes.property_settings import router as property_settings_router
from app.routes.roles import router as roles_router
from app.routes.organization_users import router as organization_users_router
from app.routes.property_users import router as property_users_router
from app.routes.auth import router as auth_router
from app.routes.property_setup import router as property_setup_router
from app.routes.reservations import router as reservations_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(organization_router)
api_router.include_router(properties_router)
api_router.include_router(property_setup_router)
api_router.include_router(property_settings_router)
api_router.include_router(room_types_router)
api_router.include_router(rooms_router)
api_router.include_router(rate_plans_router)
api_router.include_router(taxes_router)
api_router.include_router(booking_settings_router)
api_router.include_router(roles_router)
api_router.include_router(organization_users_router)
api_router.include_router(property_users_router)
api_router.include_router(reservations_router)

__all__ = ["api_router"]
