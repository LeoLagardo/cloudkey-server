from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.night_audit import (
    NightAuditResponse,
    NightAuditRunRequest,
    NightAuditStatusResponse,
    PreAuditCheckResponse,
)
from app.services.night_audit_service import night_audit_service

router = APIRouter(prefix="/properties/{property_id}/night-audit", tags=["Night Audit"])


@router.get("/status", response_model=NightAuditStatusResponse)
async def get_night_audit_status(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns current hotel business date, night audit mode (AUTO/MANUAL), scheduled time,
    and whether an audit is currently running or completed for today.
    """
    return await night_audit_service.get_audit_status(db, property_id=property_id)


@router.get("/pre-check", response_model=PreAuditCheckResponse)
async def get_pre_audit_checklist(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns pre-flight checklist for the current business date:
    - Pending un-checked-in arrivals
    - Pending departures (overdue check-outs)
    - Preview of in-house rooms to have nightly charges posted
    - Projected room revenue and tax breakdown
    """
    return await night_audit_service.get_pre_audit_status(db, property_id=property_id)


@router.post("/run", response_model=NightAuditResponse, status_code=status.HTTP_200_OK)
async def run_night_audit(
    property_id: str,
    payload: Optional[NightAuditRunRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Manually triggers the Night Audit procedure for the property:
    - Automatically releases no-shows (if enabled)
    - Posts nightly room debits & taxes to open folios
    - Reconciles housekeeping turnover
    - Snapshots daily trial balance & manager KPIs
    - Advances property business_date by +1 day
    """
    auto_no_show = payload.auto_no_show if payload else None
    allow_pending = payload.allow_pending_departure_rollover if payload else False
    notes = payload.notes if payload else None

    return await night_audit_service.execute_night_audit(
        db=db,
        property_id=property_id,
        run_by=current_user.id,
        trigger_type="MANUAL",
        auto_no_show=auto_no_show,
        allow_pending_departure_rollover=allow_pending,
        notes=notes,
    )


@router.get("/history", response_model=List[NightAuditResponse])
async def get_night_audit_history(
    property_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns paginated history of executed night audits."""
    return await night_audit_service.get_audit_history(
        db, property_id=property_id, skip=skip, limit=limit
    )


@router.get("/{audit_id}/report", response_model=Dict[str, Any])
async def get_night_audit_report(
    property_id: str,
    audit_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns the frozen Daily Manager Report & Trial Balance for an audit."""
    return await night_audit_service.get_audit_report(
        db, property_id=property_id, audit_id=audit_id
    )
