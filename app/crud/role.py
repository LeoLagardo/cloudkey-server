from typing import List, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.role import Role, Permission
from app.schemas.role import RoleCreate, RoleUpdate, PermissionCreate


class CRUDPermission(CRUDBase[Permission, PermissionCreate, PermissionCreate]):
    async def get_by_code(self, db: AsyncSession, *, code: str) -> Optional[Permission]:
        result = await db.execute(select(Permission).where(Permission.code == code))
        return result.scalars().first()

    async def get_by_ids(self, db: AsyncSession, *, ids: List[str]) -> List[Permission]:
        result = await db.execute(select(Permission).where(Permission.id.in_(ids)))
        return list(result.scalars().all())


class CRUDRole(CRUDBase[Role, RoleCreate, RoleUpdate]):
    async def get(self, db: AsyncSession, id: str) -> Optional[Role]:
        result = await db.execute(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == id)
        )
        return result.scalars().first()

    async def get_by_organization(
        self, db: AsyncSession, *, organization_id: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[Role]:
        query = select(Role).options(selectinload(Role.permissions))
        if organization_id:
            query = query.where(
                or_(Role.organization_id == organization_id, Role.is_system == True)  # noqa: E712
            )
        else:
            query = query.where(Role.is_system == True)  # noqa: E712
        result = await db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create_with_permissions(
        self, db: AsyncSession, *, obj_in: RoleCreate, permissions: List[Permission]
    ) -> Role:
        data = obj_in.model_dump(exclude={"permission_ids"}, exclude_unset=True)
        role = Role(**data)
        role.permissions = permissions
        db.add(role)
        await db.flush()
        await db.refresh(role)
        return role


crud_permission = CRUDPermission(Permission)
crud_role = CRUDRole(Role)
