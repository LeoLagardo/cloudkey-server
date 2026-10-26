from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.integrations.aiosell.auth import verify_basic_auth
from app.integrations.aiosell.exceptions import (
    AiosellConfigError,
    AiosellError,
    AiosellMappingError,
)
from app.integrations.aiosell.inventory import push_property_inventory
from app.integrations.aiosell.mappings import (
    get_aiosell_client_for_property,
    get_property_config,
    set_rate_plan_mapping,
    set_room_type_mapping,
)
from app.integrations.aiosell.rates import push_property_rates
from app.integrations.aiosell.reservations import (
    handle_webhook_reservation,
    mark_reservation_noshow,
)
from app.integrations.aiosell.schemas import (
    AiosellPropertyDetailsResponse,
    AiosellReservationWebhookPayload,
    AiosellStandardResponse,
    AiosellWebhookResponse,
)
from app.models.channel_manager import AiosellPropertyConfig

router = APIRouter(tags=["Channel Manager (Aiosell)"])


# ---------------------------------------------------------------------------
# Schemas for Configuration
# ---------------------------------------------------------------------------

class ConfigureAiosellRequest(BaseModel):
    aiosell_hotel_code: str
    pms_slug: Optional[str] = "sample-pms"
    api_username: Optional[str] = None
    api_password: Optional[str] = None
    card_decryption_key: Optional[str] = None
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_restrictions: bool = True


class MappingItem(BaseModel):
    cloudkey_id: str
    aiosell_code: str


class ConfigureMappingsRequest(BaseModel):
    room_mappings: List[MappingItem] = []
    rateplan_mappings: List[MappingItem] = []


class ManualSyncRequest(BaseModel):
    start_date: date
    end_date: date


# ---------------------------------------------------------------------------
# Inbound Webhook (Aiosell -> CloudKey PMS)
# ---------------------------------------------------------------------------

@router.post(
    "/webhooks/aiosell/reservations",
    response_model=AiosellWebhookResponse,
    summary="Aiosell Inbound Reservation Webhook",
    description="Endpoint registered with Aiosell to receive real-time OTA book, modify, and cancel actions.",
)
async def aiosell_reservation_webhook(
    payload: AiosellReservationWebhookPayload,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    # Optional basic auth verification if configured
    if settings.AIOSELL_WEBHOOK_USERNAME and settings.AIOSELL_WEBHOOK_PASSWORD:
        if not verify_basic_auth(
            authorization,
            settings.AIOSELL_WEBHOOK_USERNAME,
            settings.AIOSELL_WEBHOOK_PASSWORD,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook authentication credentials",
            )

    try:
        return await handle_webhook_reservation(db, payload)
    except AiosellConfigError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AiosellMappingError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {e}",
        )


# ---------------------------------------------------------------------------
# Outbound Management Endpoints (Staff/Admin)
# ---------------------------------------------------------------------------

@router.post(
    "/properties/{property_id}/channel-manager/aiosell/configure",
    summary="Configure Aiosell integration credentials for property",
)
async def configure_aiosell(
    property_id: str,
    payload: ConfigureAiosellRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    config = await get_property_config(db, property_id)
    if config:
        config.aiosell_hotel_code = payload.aiosell_hotel_code
        config.pms_slug = payload.pms_slug or config.pms_slug
        if payload.api_username is not None:
            config.api_username = payload.api_username
        if payload.api_password is not None:
            config.api_password = payload.api_password
        if payload.card_decryption_key is not None:
            config.card_decryption_key = payload.card_decryption_key
        config.sync_inventory = payload.sync_inventory
        config.sync_rates = payload.sync_rates
        config.sync_restrictions = payload.sync_restrictions
    else:
        config = AiosellPropertyConfig(
            property_id=property_id,
            aiosell_hotel_code=payload.aiosell_hotel_code,
            pms_slug=payload.pms_slug or "sample-pms",
            api_username=payload.api_username,
            api_password=payload.api_password,
            card_decryption_key=payload.card_decryption_key,
            sync_inventory=payload.sync_inventory,
            sync_rates=payload.sync_rates,
            sync_restrictions=payload.sync_restrictions,
        )
        db.add(config)

    await db.commit()
    return {"message": "Aiosell configuration saved successfully"}


@router.post(
    "/properties/{property_id}/channel-manager/aiosell/mappings",
    summary="Save room type and rate plan code mappings",
)
async def save_mappings(
    property_id: str,
    payload: ConfigureMappingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    for rm in payload.room_mappings:
        await set_room_type_mapping(db, property_id, rm.cloudkey_id, rm.aiosell_code)
    for rpm in payload.rateplan_mappings:
        await set_rate_plan_mapping(db, property_id, rpm.cloudkey_id, rpm.aiosell_code)
    await db.commit()
    return {"message": "Mappings saved successfully"}


@router.get(
    "/properties/{property_id}/channel-manager/aiosell/remote-details",
    response_model=AiosellPropertyDetailsResponse,
    summary="Query remote property configuration from Aiosell API",
)
async def get_remote_details(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    client, config = await get_aiosell_client_for_property(db, property_id)
    return await client.get_property_details(config.aiosell_hotel_code, config.pms_slug)


@router.post(
    "/properties/{property_id}/channel-manager/aiosell/sync-inventory",
    summary="Trigger manual inventory push to Aiosell",
)
async def manual_sync_inventory(
    property_id: str,
    payload: ManualSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    resp = await push_property_inventory(db, property_id, payload.start_date, payload.end_date)
    return resp or {"message": "No inventory records were pushed or sync is disabled"}


@router.post(
    "/properties/{property_id}/channel-manager/aiosell/sync-rates",
    summary="Trigger manual rates push to Aiosell",
)
async def manual_sync_rates(
    property_id: str,
    payload: ManualSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    resp = await push_property_rates(db, property_id, payload.start_date, payload.end_date)
    return resp or {"message": "No rates were pushed or sync is disabled"}


@router.post(
    "/reservations/{reservation_id}/mark-noshow",
    response_model=AiosellStandardResponse,
    summary="Mark reservation as no-show and notify Aiosell/OTAs",
)
async def reservation_mark_noshow(
    reservation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await mark_reservation_noshow(db, reservation_id)
