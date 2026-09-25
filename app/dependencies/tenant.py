from typing import Optional
from fastapi import Header, HTTPException, Query, status


async def get_current_organization_id(
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    organization_id: Optional[str] = Query(None, alias="organization_id"),
) -> Optional[str]:
    """
    Extracts the current tenant / organization ID from either the
    'X-Organization-ID' HTTP header or query parameter 'organization_id'.
    """
    return x_organization_id or organization_id


async def require_organization_id(
    org_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    org_param: Optional[str] = Query(None, alias="organization_id"),
) -> str:
    """
    Requires an organization context for tenant-scoped endpoints.
    """
    tenant_id = org_id or org_param
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'X-Organization-ID' or query parameter 'organization_id' is required for this operation.",
        )
    return tenant_id
