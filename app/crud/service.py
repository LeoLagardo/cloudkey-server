from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.service import Service, ServiceCategory
from app.schemas.service import (
    ServiceCategoryCreate,
    ServiceCategoryUpdate,
    ServiceCreate,
    ServiceUpdate,
)
from app.utils.enums import EntityStatus


class CRUDServiceCategory(
    CRUDBase[ServiceCategory, ServiceCategoryCreate, ServiceCategoryUpdate]
):
    async def get(self, db: AsyncSession, id: str) -> Optional[ServiceCategory]:
        result = await db.execute(
            select(ServiceCategory)
            .options(
                selectinload(ServiceCategory.sub_categories).selectinload(
                    ServiceCategory.default_tax_group
                ),
                selectinload(ServiceCategory.default_tax_group),
            )
            .where(ServiceCategory.id == id)
        )
        return result.scalars().first()

    async def get_by_property(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        parent_id: Optional[str] = None,
        only_roots: bool = False,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ServiceCategory]:
        query = (
            select(ServiceCategory)
            .options(
                selectinload(ServiceCategory.sub_categories).selectinload(
                    ServiceCategory.default_tax_group
                ),
                selectinload(ServiceCategory.default_tax_group),
            )
            .where(ServiceCategory.property_id == property_id)
        )

        if only_roots:
            query = query.where(ServiceCategory.parent_id.is_(None))
        elif parent_id is not None:
            query = query.where(ServiceCategory.parent_id == parent_id)

        if active_only:
            query = query.where(ServiceCategory.status == EntityStatus.ACTIVE.value)

        query = (
            query.order_by(ServiceCategory.sort_order.asc(), ServiceCategory.name.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, property_id: str, code: str
    ) -> Optional[ServiceCategory]:
        result = await db.execute(
            select(ServiceCategory)
            .options(
                selectinload(ServiceCategory.sub_categories),
                selectinload(ServiceCategory.default_tax_group),
            )
            .where(
                ServiceCategory.property_id == property_id,
                ServiceCategory.code == code,
            )
        )
        return result.scalars().first()


class CRUDService(CRUDBase[Service, ServiceCreate, ServiceUpdate]):
    async def get(self, db: AsyncSession, id: str) -> Optional[Service]:
        result = await db.execute(
            select(Service)
            .options(
                selectinload(Service.tax_group),
                selectinload(Service.service_category),
            )
            .where(Service.id == id)
        )
        return result.scalars().first()

    async def get_by_property(
        self,
        db: AsyncSession,
        *,
        property_id: str,
        category: Optional[str] = None,
        category_id: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Service]:
        query = (
            select(Service)
            .options(
                selectinload(Service.tax_group),
                selectinload(Service.service_category),
            )
            .where(Service.property_id == property_id)
        )
        if active_only:
            query = query.where(Service.status == EntityStatus.ACTIVE.value)
        if category_id:
            query = query.where(Service.category_id == category_id)
        elif category:
            query = query.where(Service.category == category)

        query = query.order_by(Service.name.asc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_code(
        self, db: AsyncSession, *, property_id: str, code: str
    ) -> Optional[Service]:
        result = await db.execute(
            select(Service)
            .options(
                selectinload(Service.tax_group),
                selectinload(Service.service_category),
            )
            .where(
                Service.property_id == property_id,
                Service.code == code,
            )
        )
        return result.scalars().first()


crud_service_category = CRUDServiceCategory(ServiceCategory)
crud_service = CRUDService(Service)
