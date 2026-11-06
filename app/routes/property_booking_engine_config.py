from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.property_booking_engine_config import (
    PropertyBookingEngineConfigUpdate,
    PropertyBookingEngineConfigResponse,
    DomainVerifyResponse,
    GatewayTestRequest,
    GatewayTestResponse,
)
from app.services.booking_engine_config_service import booking_engine_config_service

router = APIRouter(
    prefix="/properties/{property_id}/booking-engine-config",
    tags=["Booking Engine Admin Settings"],
)


@router.get("", response_model=PropertyBookingEngineConfigResponse)
async def get_booking_engine_config(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve booking engine configuration for property (secrets are masked)."""
    config = await booking_engine_config_service.get_or_create_default(db, property_id=property_id)
    return booking_engine_config_service.build_response(config)


@router.put("", response_model=PropertyBookingEngineConfigResponse)
async def update_booking_engine_config(
    property_id: str,
    payload: PropertyBookingEngineConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update booking engine branding, theme, published rate plans, payment gateways, and custom domain."""
    updated = await booking_engine_config_service.update_config(
        db, property_id=property_id, config_in=payload
    )
    return booking_engine_config_service.build_response(updated)


@router.post("/verify-domain", response_model=DomainVerifyResponse)
async def verify_custom_domain(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Trigger DNS lookup to verify custom domain CNAME resolution."""
    return await booking_engine_config_service.verify_domain(db, property_id=property_id)


@router.post("/test-gateway", response_model=GatewayTestResponse)
async def test_payment_gateway(
    property_id: str,
    payload: GatewayTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Test Razorpay or Stripe credentials syntax and connectivity."""
    return await booking_engine_config_service.test_gateway(
        db, property_id=property_id, test_in=payload
    )

