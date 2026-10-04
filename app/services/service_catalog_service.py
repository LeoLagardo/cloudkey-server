from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.service import crud_service, crud_service_category
from app.crud.tax import crud_tax_group
from app.models.service import Service, ServiceCategory
from app.schemas.service import (
    ServiceCategoryCreate,
    ServiceCategoryUpdate,
    ServiceCreate,
    ServiceUpdate,
)
from app.utils.enums import EntityStatus, ServiceCategory as ServiceCategoryEnum
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)


class ServiceCatalogService:
    # ─── Category Management ──────────────────────────────────────────────────

    async def list_categories(
        self,
        db: AsyncSession,
        property_id: str,
        parent_id: Optional[str] = None,
        only_roots: bool = True,
        active_only: bool = False,
    ) -> List[ServiceCategory]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        return await crud_service_category.get_by_property(
            db,
            property_id=property_id,
            parent_id=parent_id,
            only_roots=only_roots,
            active_only=active_only,
            limit=200,
        )

    async def get_category(
        self, db: AsyncSession, property_id: str, category_id: str
    ) -> ServiceCategory:
        cat = await crud_service_category.get(db, category_id)
        if not cat or cat.property_id != property_id:
            raise EntityNotFoundException("ServiceCategory", category_id)
        return cat

    async def create_category(
        self, db: AsyncSession, property_id: str, cat_in: ServiceCategoryCreate
    ) -> ServiceCategory:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        normalized_code = cat_in.code.strip().upper()
        existing = await crud_service_category.get_by_code(
            db, property_id=property_id, code=normalized_code
        )
        if existing:
            raise DuplicateEntityException("ServiceCategory", "code", normalized_code)

        # Validate parent_id if provided
        if cat_in.parent_id:
            parent = await self.get_category(db, property_id, cat_in.parent_id)
            if parent.parent_id:
                raise ValidationException("Nesting beyond 2 levels (Category -> Sub-category) is not allowed.")
            # Inherit system_type from parent if set to OTHER
            if cat_in.system_type == ServiceCategoryEnum.OTHER.value and parent.system_type != ServiceCategoryEnum.OTHER.value:
                cat_in.system_type = parent.system_type

        # Validate default TaxGroup if provided
        if cat_in.default_tax_group_id:
            tg = await crud_tax_group.get(db, cat_in.default_tax_group_id)
            if not tg:
                raise EntityNotFoundException("TaxGroup", cat_in.default_tax_group_id)
            if tg.organization_id != prop.organization_id:
                raise ValidationException("TaxGroup does not belong to property organization.")

        create_dict = cat_in.model_dump()
        create_dict["property_id"] = property_id
        create_dict["code"] = normalized_code

        category = await crud_service_category.create(db, obj_in=create_dict)
        return await self.get_category(db, property_id, category.id)

    async def update_category(
        self,
        db: AsyncSession,
        property_id: str,
        category_id: str,
        cat_in: ServiceCategoryUpdate,
    ) -> ServiceCategory:
        category = await self.get_category(db, property_id, category_id)
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        update_dict = cat_in.model_dump(exclude_unset=True)

        if "code" in update_dict and update_dict["code"]:
            normalized_code = update_dict["code"].strip().upper()
            if normalized_code != category.code:
                existing = await crud_service_category.get_by_code(
                    db, property_id=property_id, code=normalized_code
                )
                if existing:
                    raise DuplicateEntityException("ServiceCategory", "code", normalized_code)
            update_dict["code"] = normalized_code

        if "parent_id" in update_dict and update_dict["parent_id"]:
            if update_dict["parent_id"] == category_id:
                raise ValidationException("A category cannot be its own parent.")
            parent = await self.get_category(db, property_id, update_dict["parent_id"])
            if parent.parent_id:
                raise ValidationException("Nesting beyond 2 levels is not allowed.")

        if "default_tax_group_id" in update_dict and update_dict["default_tax_group_id"]:
            tg = await crud_tax_group.get(db, update_dict["default_tax_group_id"])
            if not tg:
                raise EntityNotFoundException("TaxGroup", update_dict["default_tax_group_id"])
            if tg.organization_id != prop.organization_id:
                raise ValidationException("TaxGroup does not belong to property organization.")

        await crud_service_category.update(db, db_obj=category, obj_in=update_dict)
        return await self.get_category(db, property_id, category_id)

    async def deactivate_category(
        self, db: AsyncSession, property_id: str, category_id: str
    ) -> ServiceCategory:
        category = await self.get_category(db, property_id, category_id)
        category.status = EntityStatus.INACTIVE.value
        # Also deactivate sub-categories
        for sub in category.sub_categories:
            sub.status = EntityStatus.INACTIVE.value
        await db.flush()
        await db.refresh(category)
        return category

    async def seed_default_categories(
        self, db: AsyncSession, property_id: str
    ) -> List[ServiceCategory]:
        """Bootstrap hotel industry standard categories and sub-categories."""
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        defaults = [
            {
                "name": "Food & Beverage",
                "code": "FNB",
                "system_type": ServiceCategoryEnum.FOOD.value,
                "description": "Dining, banqueting, and beverage services",
                "default_hsn_sac_code": "996331",
                "sort_order": 1,
                "subs": [
                    {"name": "In-Room Dining", "code": "FNB-IRD", "default_hsn_sac_code": "996331"},
                    {"name": "Restaurant & Buffet", "code": "FNB-REST", "default_hsn_sac_code": "996331"},
                    {"name": "Lounge & Pool Bar", "code": "FNB-BAR", "default_hsn_sac_code": "996332"},
                ],
            },
            {
                "name": "Laundry & Valet",
                "code": "LAU",
                "system_type": ServiceCategoryEnum.LAUNDRY.value,
                "description": "Guest laundry, dry cleaning, and pressing",
                "default_hsn_sac_code": "999721",
                "sort_order": 2,
                "subs": [
                    {"name": "Dry Cleaning", "code": "LAU-DC", "default_hsn_sac_code": "999721"},
                    {"name": "Wash & Fold", "code": "LAU-WF", "default_hsn_sac_code": "999721"},
                    {"name": "Express Ironing", "code": "LAU-EXP", "default_hsn_sac_code": "999721"},
                ],
            },
            {
                "name": "Transportation & Travel",
                "code": "TRN",
                "system_type": ServiceCategoryEnum.TRANSPORT.value,
                "description": "Airport transfers, chauffeur, and local cab hire",
                "default_hsn_sac_code": "996412",
                "sort_order": 3,
                "subs": [
                    {"name": "Airport Transfers", "code": "TRN-AIR", "default_hsn_sac_code": "996412"},
                    {"name": "Local Chauffeur Cab", "code": "TRN-CAB", "default_hsn_sac_code": "996412"},
                ],
            },
            {
                "name": "Spa & Wellness",
                "code": "SPA",
                "system_type": ServiceCategoryEnum.SPA.value,
                "description": "Massage, wellness treatments, and salon",
                "default_hsn_sac_code": "999722",
                "sort_order": 4,
                "subs": [
                    {"name": "Massage & Body Therapies", "code": "SPA-MAS", "default_hsn_sac_code": "999722"},
                    {"name": "Facials & Beauty Salon", "code": "SPA-SAL", "default_hsn_sac_code": "999722"},
                ],
            },
            {
                "name": "In-Room Minibar",
                "code": "MNB",
                "system_type": ServiceCategoryEnum.MINIBAR.value,
                "description": "In-room snacks, confectionery, and refreshments",
                "default_hsn_sac_code": "996331",
                "sort_order": 5,
                "subs": [
                    {"name": "Packaged Snacks", "code": "MNB-SNK", "default_hsn_sac_code": "996331"},
                    {"name": "Soft Drinks & Juices", "code": "MNB-BEV", "default_hsn_sac_code": "996331"},
                ],
            },
            {
                "name": "Front Desk & Incidentals",
                "code": "OTH",
                "system_type": ServiceCategoryEnum.OTHER.value,
                "description": "Extra bed, fees, late check-out, and miscellaneous",
                "default_hsn_sac_code": "996311",
                "sort_order": 6,
                "subs": [
                    {"name": "Extra Bed & Linen", "code": "OTH-BED", "default_hsn_sac_code": "996311"},
                    {"name": "Fees & Surcharges", "code": "OTH-FEE", "default_hsn_sac_code": "996311"},
                ],
            },
        ]

        created_roots = []
        for def_cat in defaults:
            existing = await crud_service_category.get_by_code(
                db, property_id=property_id, code=def_cat["code"]
            )
            if not existing:
                root_obj = await crud_service_category.create(
                    db,
                    obj_in={
                        "property_id": property_id,
                        "name": def_cat["name"],
                        "code": def_cat["code"],
                        "system_type": def_cat["system_type"],
                        "description": def_cat.get("description"),
                        "default_hsn_sac_code": def_cat.get("default_hsn_sac_code"),
                        "sort_order": def_cat.get("sort_order", 0),
                        "status": EntityStatus.ACTIVE.value,
                    },
                )
            else:
                root_obj = existing

            for sub in def_cat.get("subs", []):
                existing_sub = await crud_service_category.get_by_code(
                    db, property_id=property_id, code=sub["code"]
                )
                if not existing_sub:
                    await crud_service_category.create(
                        db,
                        obj_in={
                            "property_id": property_id,
                            "parent_id": root_obj.id,
                            "name": sub["name"],
                            "code": sub["code"],
                            "system_type": def_cat["system_type"],
                            "default_hsn_sac_code": sub.get("default_hsn_sac_code"),
                            "status": EntityStatus.ACTIVE.value,
                        },
                    )

            created_roots.append(await self.get_category(db, property_id, root_obj.id))

        return created_roots

    # ─── Service Management ───────────────────────────────────────────────────

    async def list_services(
        self,
        db: AsyncSession,
        property_id: str,
        category: Optional[str] = None,
        category_id: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Service]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        return await crud_service.get_by_property(
            db,
            property_id=property_id,
            category=category,
            category_id=category_id,
            active_only=active_only,
            skip=skip,
            limit=limit,
        )

    async def get_service(
        self, db: AsyncSession, property_id: str, service_id: str
    ) -> Service:
        service = await crud_service.get(db, service_id)
        if not service or service.property_id != property_id:
            raise EntityNotFoundException("Service", service_id)
        return service

    async def create_service(
        self, db: AsyncSession, property_id: str, service_in: ServiceCreate
    ) -> Service:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        # Check code uniqueness
        normalized_code = service_in.code.strip().upper()
        existing = await crud_service.get_by_code(db, property_id=property_id, code=normalized_code)
        if existing:
            raise DuplicateEntityException("Service", "code", normalized_code)

        create_dict = service_in.model_dump()
        create_dict["property_id"] = property_id
        create_dict["code"] = normalized_code

        # If category_id is set, validate and inherit defaults
        if service_in.category_id:
            cat = await self.get_category(db, property_id, service_in.category_id)
            # Inherit system category enum
            if not service_in.category or service_in.category == ServiceCategoryEnum.OTHER.value:
                create_dict["category"] = cat.system_type
            # Inherit TaxGroup if not specified
            if not service_in.tax_group_id and cat.default_tax_group_id:
                create_dict["tax_group_id"] = cat.default_tax_group_id
            # Inherit HSN/SAC if not specified
            if not service_in.hsn_sac_code and cat.default_hsn_sac_code:
                create_dict["hsn_sac_code"] = cat.default_hsn_sac_code

        # Validate TaxGroup if specified
        if create_dict.get("tax_group_id"):
            tg = await crud_tax_group.get(db, create_dict["tax_group_id"])
            if not tg:
                raise EntityNotFoundException("TaxGroup", create_dict["tax_group_id"])
            if tg.organization_id != prop.organization_id:
                raise ValidationException("TaxGroup does not belong to the property's organization.")

        service = await crud_service.create(db, obj_in=create_dict)
        return await self.get_service(db, property_id, service.id)

    async def update_service(
        self, db: AsyncSession, property_id: str, service_id: str, service_in: ServiceUpdate
    ) -> Service:
        service = await self.get_service(db, property_id, service_id)
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        update_dict = service_in.model_dump(exclude_unset=True)

        if "code" in update_dict and update_dict["code"]:
            normalized_code = update_dict["code"].strip().upper()
            if normalized_code != service.code:
                existing = await crud_service.get_by_code(
                    db, property_id=property_id, code=normalized_code
                )
                if existing:
                    raise DuplicateEntityException("Service", "code", normalized_code)
            update_dict["code"] = normalized_code

        if "category_id" in update_dict and update_dict["category_id"]:
            cat = await self.get_category(db, property_id, update_dict["category_id"])
            if "category" not in update_dict or not update_dict["category"]:
                update_dict["category"] = cat.system_type

        if "tax_group_id" in update_dict and update_dict["tax_group_id"]:
            tg = await crud_tax_group.get(db, update_dict["tax_group_id"])
            if not tg:
                raise EntityNotFoundException("TaxGroup", update_dict["tax_group_id"])
            if tg.organization_id != prop.organization_id:
                raise ValidationException("TaxGroup does not belong to the property's organization.")

        await crud_service.update(db, db_obj=service, obj_in=update_dict)
        return await self.get_service(db, property_id, service_id)

    async def deactivate_service(
        self, db: AsyncSession, property_id: str, service_id: str
    ) -> Service:
        service = await self.get_service(db, property_id, service_id)
        service.status = EntityStatus.INACTIVE.value
        await db.flush()
        await db.refresh(service)
        return service


service_catalog_service = ServiceCatalogService()
