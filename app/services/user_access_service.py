from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.organization import crud_organization
from app.crud.property import crud_property
from app.crud.role import crud_role
from app.crud.organization_user import crud_organization_user
from app.crud.property_user import crud_property_user
from app.models.organization_user import OrganizationUser
from app.models.property_user import PropertyUser
from app.schemas.organization_user import OrganizationUserCreate, OrganizationUserUpdate
from app.schemas.property_user import PropertyUserCreate, PropertyUserUpdate
from app.utils.exceptions import (
    EntityNotFoundException,
    DuplicateEntityException,
    ValidationException,
)


class UserAccessService:
    # Organization Users
    async def list_organization_users(
        self, db: AsyncSession, organization_id: str, skip: int = 0, limit: int = 100
    ) -> List[OrganizationUser]:
        org = await crud_organization.get(db, organization_id)
        if not org:
            raise EntityNotFoundException("Organization", organization_id)
        return await crud_organization_user.get_by_organization(
            db, organization_id=organization_id, skip=skip, limit=limit
        )

    async def assign_organization_user(
        self, db: AsyncSession, organization_id: str, obj_in: OrganizationUserCreate
    ) -> OrganizationUser:
        org = await crud_organization.get(db, organization_id)
        if not org:
            raise EntityNotFoundException("Organization", organization_id)

        role = await crud_role.get(db, obj_in.role_id)
        if not role:
            raise EntityNotFoundException("Role", obj_in.role_id)

        existing = await crud_organization_user.get_by_org_and_user(
            db, organization_id=organization_id, user_id=obj_in.user_id
        )
        if existing:
            raise DuplicateEntityException("OrganizationUser", "user_id", obj_in.user_id)

        data = obj_in.model_dump(exclude_unset=True)
        data["organization_id"] = organization_id
        return await crud_organization_user.create(db, obj_in=data)

    async def update_organization_user(
        self, db: AsyncSession, org_user_id: str, obj_in: OrganizationUserUpdate
    ) -> OrganizationUser:
        org_user = await crud_organization_user.get(db, org_user_id)
        if not org_user:
            raise EntityNotFoundException("OrganizationUser", org_user_id)

        if obj_in.role_id:
            role = await crud_role.get(db, obj_in.role_id)
            if not role:
                raise EntityNotFoundException("Role", obj_in.role_id)

        return await crud_organization_user.update(db, db_obj=org_user, obj_in=obj_in)

    async def remove_organization_user(
        self, db: AsyncSession, org_user_id: str
    ) -> OrganizationUser:
        org_user = await crud_organization_user.get(db, org_user_id)
        if not org_user:
            raise EntityNotFoundException("OrganizationUser", org_user_id)
        await crud_organization_user.remove(db, id=org_user_id)
        return org_user

    # Property Users
    async def list_property_users(
        self, db: AsyncSession, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[PropertyUser]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)
        return await crud_property_user.get_by_property(
            db, property_id=property_id, skip=skip, limit=limit
        )

    async def assign_property_user(
        self, db: AsyncSession, property_id: str, obj_in: PropertyUserCreate
    ) -> PropertyUser:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        role = await crud_role.get(db, obj_in.role_id)
        if not role:
            raise EntityNotFoundException("Role", obj_in.role_id)

        existing = await crud_property_user.get_by_property_and_user(
            db, property_id=property_id, user_id=obj_in.user_id
        )
        if existing:
            raise DuplicateEntityException("PropertyUser", "user_id", obj_in.user_id)

        data = obj_in.model_dump(exclude_unset=True)
        data["property_id"] = property_id
        return await crud_property_user.create(db, obj_in=data)

    async def update_property_user(
        self, db: AsyncSession, prop_user_id: str, obj_in: PropertyUserUpdate
    ) -> PropertyUser:
        prop_user = await crud_property_user.get(db, prop_user_id)
        if not prop_user:
            raise EntityNotFoundException("PropertyUser", prop_user_id)

        if obj_in.role_id:
            role = await crud_role.get(db, obj_in.role_id)
            if not role:
                raise EntityNotFoundException("Role", obj_in.role_id)

        return await crud_property_user.update(db, db_obj=prop_user, obj_in=obj_in)

    async def remove_property_user(
        self, db: AsyncSession, prop_user_id: str
    ) -> PropertyUser:
        prop_user = await crud_property_user.get(db, prop_user_id)
        if not prop_user:
            raise EntityNotFoundException("PropertyUser", prop_user_id)
        await crud_property_user.remove(db, id=prop_user_id)
        return prop_user


user_access_service = UserAccessService()
