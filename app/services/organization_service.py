from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.organization import crud_organization
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.utils.exceptions import DuplicateEntityException, EntityNotFoundException


class OrganizationService:
    async def get_by_id(self, db: AsyncSession, organization_id: str) -> Organization:
        org = await crud_organization.get(db, organization_id)
        if not org:
            raise EntityNotFoundException("Organization", organization_id)
        return org

    async def list_organizations(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Organization]:
        return await crud_organization.get_multi(db, skip=skip, limit=limit)

    async def create_organization(
        self, db: AsyncSession, org_in: OrganizationCreate
    ) -> Organization:
        return await crud_organization.create(db, obj_in=org_in)

    async def update_organization(
        self, db: AsyncSession, organization_id: str, org_in: OrganizationUpdate
    ) -> Organization:
        org = await self.get_by_id(db, organization_id)
        return await crud_organization.update(db, db_obj=org, obj_in=org_in)

    async def delete_organization(
        self, db: AsyncSession, organization_id: str
    ) -> Organization:
        org = await self.get_by_id(db, organization_id)
        await crud_organization.remove(db, id=organization_id)
        return org


organization_service = OrganizationService()
