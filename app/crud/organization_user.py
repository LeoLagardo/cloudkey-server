from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.organization_user import OrganizationUser
from app.schemas.organization_user import OrganizationUserCreate, OrganizationUserUpdate


class CRUDOrganizationUser(
    CRUDBase[OrganizationUser, OrganizationUserCreate, OrganizationUserUpdate]
):
    async def get_by_org_and_user(
        self, db: AsyncSession, *, organization_id: str, user_id: str
    ) -> Optional[OrganizationUser]:
        result = await db.execute(
            select(OrganizationUser).where(
                OrganizationUser.organization_id == organization_id,
                OrganizationUser.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_by_organization(
        self, db: AsyncSession, *, organization_id: str, skip: int = 0, limit: int = 100
    ) -> List[OrganizationUser]:
        result = await db.execute(
            select(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_organization_user = CRUDOrganizationUser(OrganizationUser)
