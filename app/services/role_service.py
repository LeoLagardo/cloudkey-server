from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.role import crud_role, crud_permission
from app.models.role import Role, Permission
from app.schemas.role import RoleCreate, RoleUpdate, PermissionCreate
from app.utils.exceptions import EntityNotFoundException, DuplicateEntityException


class RoleService:
    # Permissions
    async def list_permissions(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Permission]:
        return await crud_permission.get_multi(db, skip=skip, limit=limit)

    async def create_permission(
        self, db: AsyncSession, perm_in: PermissionCreate
    ) -> Permission:
        existing = await crud_permission.get_by_code(db, code=perm_in.code)
        if existing:
            raise DuplicateEntityException("Permission", "code", perm_in.code)
        return await crud_permission.create(db, obj_in=perm_in)

    # Roles
    async def get_by_id(self, db: AsyncSession, role_id: str) -> Role:
        role = await crud_role.get(db, role_id)
        if not role:
            raise EntityNotFoundException("Role", role_id)
        return role

    async def list_roles(
        self, db: AsyncSession, organization_id: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[Role]:
        return await crud_role.get_by_organization(
            db, organization_id=organization_id, skip=skip, limit=limit
        )

    async def create_role(
        self, db: AsyncSession, role_in: RoleCreate, organization_id: Optional[str] = None
    ) -> Role:
        if organization_id and not role_in.organization_id:
            role_in.organization_id = organization_id

        permissions = []
        if role_in.permission_ids:
            permissions = await crud_permission.get_by_ids(db, ids=role_in.permission_ids)

        return await crud_role.create_with_permissions(
            db, obj_in=role_in, permissions=permissions
        )

    async def update_role(
        self, db: AsyncSession, role_id: str, role_in: RoleUpdate
    ) -> Role:
        role = await self.get_by_id(db, role_id)
        if role_in.permission_ids is not None:
            permissions = await crud_permission.get_by_ids(db, ids=role_in.permission_ids)
            role.permissions = permissions

        update_data = role_in.model_dump(exclude={"permission_ids"}, exclude_unset=True)
        return await crud_role.update(db, db_obj=role, obj_in=update_data)

    async def delete_role(self, db: AsyncSession, role_id: str) -> Role:
        role = await self.get_by_id(db, role_id)
        await crud_role.remove(db, id=role_id)
        return role


role_service = RoleService()
