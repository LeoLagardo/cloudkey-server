from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthenticatedUser, get_current_user
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardSummaryResponse, summary="PMS Live Operational Dashboard")
async def get_dashboard(
    property_id: str = Query(..., description="Property ID to fetch dashboard summary for"),
    business_date: Optional[date] = Query(None, description="Optional override date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DashboardSummaryResponse:
    """
    Retrieve live operational dashboard for a property:
    - Real KPIs (Arrivals, Departures, In-House, Available Rooms, Occupancy %, Revenue)
    - Real today's arrivals roster with room status & payment settlement CTA
    - Real today's departures roster with folio balances & check-out status
    - Real room inventory counts & fast tape chart preview
    - Real housekeeping priority alert
    - Real 7-day occupancy trend curve
    """
    return await dashboard_service.get_dashboard_summary(
        db=db,
        property_id=property_id,
        business_date=business_date,
    )
