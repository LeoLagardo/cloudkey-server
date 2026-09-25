from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import date
from app.crud.property import crud_property
from app.crud.property_booking_settings import crud_property_booking_settings
from app.crud.rate_plan import crud_rate_plan
from app.crud.rate_plan_rate import crud_rate_plan_rate
from app.crud.room import crud_room
from app.crud.room_type import crud_room_type
from app.crud.tax import (
    crud_tax,
    crud_tax_group,
    crud_tax_group_item,
    crud_tax_rate,
)
from app.models.property import Property
from app.schemas.property import PropertyResponse
from app.schemas.property_booking_settings import (
    PropertyBookingSettingsCreate,
    PropertyBookingSettingsResponse,
    PropertyBookingSettingsUpdate,
)
from app.services.property_settings_service import property_settings_service
from app.schemas.property_setup import (
    BulkRoomGroup,
    PropertyDashboardResponse,
    SetupBookingSettingsRequest,
    SetupCompleteResponse,
    SetupRatePlansRequest,
    SetupRoomTypesRequest,
    SetupRoomsRequest,
    SetupStatusResponse,
    SetupTaxesRequest,
    StepProgress,
)
from app.schemas.rate_plan import RatePlanCreate, RatePlanResponse
from app.schemas.tax import TaxGroupResponse
from app.schemas.rate_plan_rate import RatePlanRateCreate
from app.schemas.room import RoomCreate, RoomResponse
from app.schemas.room_type import RoomTypeCreate, RoomTypeResponse
from app.utils.enums import EntityStatus, RoomStatus
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)
from app.utils.validators import slugify


class PropertySetupService:
    async def get_setup_status(
        self, db: AsyncSession, property_id: str
    ) -> SetupStatusResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        room_types = await crud_room_type.get_by_property(db, property_id=property_id)
        rooms = await crud_room.get_by_property(db, property_id=property_id)
        rate_plans = await crud_rate_plan.get_by_property(db, property_id=property_id)
        tax_groups = await crud_tax_group.get_by_organization(
            db, organization_id=prop.organization_id
        )
        booking_settings = await crud_property_booking_settings.get_by_property(
            db, property_id=property_id
        )
        settings = await property_settings_service.get_by_property(
            db, property_id=property_id
        )
        settings_dict = {
            "id": settings.id,
            "property_id": settings.property_id,
            "date_format": settings.date_format,
            "time_format": settings.time_format,
            "language": settings.language,
            "number_format": settings.number_format,
            "week_start_day": settings.week_start_day,
            "night_audit_time": str(settings.night_audit_time),
            "same_day_checkout_rule": settings.same_day_checkout_rule,
            "invoice_prefix": settings.invoice_prefix,
            "extra": settings.extra,
        }

        rt_completed = len(room_types) > 0
        rooms_completed = len(rooms) > 0
        rate_plans_completed = len(rate_plans) > 0
        taxes_completed = len(tax_groups) > 0
        booking_completed = booking_settings is not None

        steps: Dict[str, StepProgress] = {
            "property_details": StepProgress(
                name="property_details",
                title="Property Details",
                is_completed=True,
                count=1,
                details={
                    "name": prop.name,
                    "code": prop.code,
                    "address_line_1": prop.address_line_1,
                    "address_line_2": prop.address_line_2,
                    "city": prop.city,
                    "state": prop.state,
                    "country": prop.country,
                    "postal_code": prop.postal_code,
                    "timezone": prop.timezone,
                    "currency": prop.currency,
                    "classification": prop.classification,
                    "business_date": prop.business_date.isoformat() if prop.business_date else None,
                    "gstin": prop.gstin,
                    "settings": settings_dict,
                },
            ),
            "room_types": StepProgress(
                name="room_types",
                title="Room Types",
                is_completed=rt_completed,
                count=len(room_types),
                details=[{"id": rt.id, "name": rt.name, "code": rt.code} for rt in room_types],
            ),
            "rooms": StepProgress(
                name="rooms",
                title="Rooms",
                is_completed=rooms_completed,
                count=len(rooms),
                details=[{"id": r.id, "room_number": r.room_number, "room_type_id": r.room_type_id, "floor": r.floor} for r in rooms],
            ),
            "rate_plans": StepProgress(
                name="rate_plans",
                title="Rate Plans",
                is_completed=rate_plans_completed,
                count=len(rate_plans),
                details=[{"id": rp.id, "name": rp.name, "booking_type": rp.booking_type} for rp in rate_plans],
            ),
            "taxes": StepProgress(
                name="taxes",
                title="Taxes & Surcharges",
                is_completed=taxes_completed,
                count=len(tax_groups),
                details=[{"id": tg.id, "name": tg.name, "code": tg.code} for tg in tax_groups],
            ),
            "booking_settings": StepProgress(
                name="booking_settings",
                title="Booking Settings",
                is_completed=booking_completed,
                count=1 if booking_completed else 0,
                details={
                    "check_in_time": str(booking_settings.check_in_time) if booking_settings else None,
                    "check_out_time": str(booking_settings.check_out_time) if booking_settings else None,
                },
            ),
        }

        # Calculate current wizard step
        if not rt_completed:
            current_step = "ROOM_TYPES"
        elif not rooms_completed:
            current_step = "ROOMS"
        elif not rate_plans_completed:
            current_step = "RATE_PLANS"
        elif not taxes_completed:
            current_step = "TAXES"
        elif not booking_completed:
            current_step = "BOOKING_SETTINGS"
        elif not prop.is_setup_completed:
            current_step = "SETUP_COMPLETE"
        else:
            current_step = "COMPLETED"

        if prop.setup_step != current_step:
            prop.setup_step = current_step
            await db.flush()

        return SetupStatusResponse(
            property_id=prop.id,
            property_name=prop.name,
            property_code=prop.code,
            is_setup_completed=prop.is_setup_completed,
            current_step=current_step,
            address_line_1=prop.address_line_1,
            address_line_2=prop.address_line_2,
            city=prop.city,
            state=prop.state,
            country=prop.country,
            postal_code=prop.postal_code,
            timezone=prop.timezone,
            currency=prop.currency,
            classification=prop.classification,
            business_date=prop.business_date,
            gstin=prop.gstin,
            settings=settings_dict,
            steps=steps,
        )

    async def setup_room_types(
        self, db: AsyncSession, property_id: str, data: SetupRoomTypesRequest
    ) -> List[RoomTypeResponse]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        created_room_types: List[RoomTypeResponse] = []
        for rt_in in data.room_types:
            existing = await crud_room_type.get_by_code(
                db, property_id=property_id, code=rt_in.code
            )
            if existing:
                created_room_types.append(RoomTypeResponse.model_validate(existing))
                continue

            rt_data = rt_in.model_dump(exclude_unset=True)
            rt_data["property_id"] = property_id
            created = await crud_room_type.create(db, obj_in=rt_data)
            created_room_types.append(RoomTypeResponse.model_validate(created))

        prop.setup_step = "ROOMS"
        await db.commit()
        return created_room_types

    async def setup_rooms(
        self, db: AsyncSession, property_id: str, data: SetupRoomsRequest
    ) -> List[RoomResponse]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        created_rooms: List[RoomResponse] = []

        # 1. Process explicit individual rooms
        if data.rooms:
            for r_in in data.rooms:
                existing = await crud_room.get_by_number(
                    db, property_id=property_id, room_number=r_in.room_number
                )
                if existing:
                    created_rooms.append(RoomResponse.model_validate(existing))
                    continue

                r_data = r_in.model_dump(exclude_unset=True)
                r_data["property_id"] = property_id
                created = await crud_room.create(db, obj_in=r_data)
                created_rooms.append(RoomResponse.model_validate(created))

        # 2. Process bulk room groups
        if data.bulk_groups:
            for group in data.bulk_groups:
                # Check room type belongs to property
                rt = await crud_room_type.get(db, group.room_type_id)
                if not rt or rt.property_id != property_id:
                    raise EntityNotFoundException("RoomType", group.room_type_id)

                numbers_to_create: List[str] = []
                if group.room_numbers:
                    numbers_to_create.extend(group.room_numbers)
                elif group.start_number and group.count:
                    prefix = group.prefix or ""
                    for i in range(group.count):
                        numbers_to_create.append(f"{prefix}{group.start_number + i}")

                for num in numbers_to_create:
                    cleaned_num = num.strip()
                    existing = await crud_room.get_by_number(
                        db, property_id=property_id, room_number=cleaned_num
                    )
                    if existing:
                        created_rooms.append(RoomResponse.model_validate(existing))
                        continue

                    created = await crud_room.create(
                        db,
                        obj_in={
                            "property_id": property_id,
                            "room_type_id": group.room_type_id,
                            "room_number": cleaned_num,
                            "floor": group.floor,
                            "status": RoomStatus.AVAILABLE.value,
                        },
                    )
                    created_rooms.append(RoomResponse.model_validate(created))

        prop.setup_step = "RATE_PLANS"
        await db.commit()
        return created_rooms

    async def setup_rate_plans(
        self, db: AsyncSession, property_id: str, data: SetupRatePlansRequest
    ) -> List[RatePlanResponse]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        created_plans: List[RatePlanResponse] = []
        for plan_in in data.rate_plans:
            # Case 1: multiple rates for multiple room types
            if plan_in.rates:
                for idx, r_item in enumerate(plan_in.rates):
                    rt = await crud_room_type.get(db, r_item.room_type_id)
                    if not rt or rt.property_id != property_id:
                        raise EntityNotFoundException("RoomType", r_item.room_type_id)

                    code_prefix = slugify(plan_in.name).upper().replace("-", "")[:6]
                    rt_prefix = rt.code.upper().replace("-", "")[:4]
                    rate_code = f"{code_prefix}-{rt_prefix}"

                    # Check duplicate code in property
                    existing = await crud_rate_plan.get_by_code(
                        db, property_id=property_id, code=rate_code
                    )
                    if existing:
                        rate_code = f"{rate_code}-{idx + 1}"

                    plan_obj = await crud_rate_plan.create(
                        db,
                        obj_in={
                            "property_id": property_id,
                            "room_type_id": r_item.room_type_id,
                            "name": f"{plan_in.name} ({rt.name})",
                            "code": rate_code,
                            "booking_type": plan_in.booking_type.value,
                            "description": plan_in.description,
                            "currency": plan_in.currency,
                            "status": EntityStatus.ACTIVE.value,
                        },
                    )

                    await crud_rate_plan_rate.create(
                        db,
                        obj_in={
                            "rate_plan_id": plan_obj.id,
                            "duration": r_item.duration,
                            "duration_unit": r_item.duration_unit.value,
                            "price": r_item.price,
                            "min_occupancy": r_item.min_occupancy or rt.base_occupancy,
                            "max_occupancy": r_item.max_occupancy or rt.max_occupancy,
                        },
                    )
                    created_plans.append(RatePlanResponse.model_validate(plan_obj))

            # Case 2: single room_type_id and price on the plan itself
            elif plan_in.room_type_id and plan_in.price is not None:
                rt = await crud_room_type.get(db, plan_in.room_type_id)
                if not rt or rt.property_id != property_id:
                    raise EntityNotFoundException("RoomType", plan_in.room_type_id)

                rate_code = plan_in.code or f"{slugify(plan_in.name).upper()[:8]}-{rt.code.upper()[:4]}"
                plan_obj = await crud_rate_plan.create(
                    db,
                    obj_in={
                        "property_id": property_id,
                        "room_type_id": plan_in.room_type_id,
                        "name": plan_in.name,
                        "code": rate_code,
                        "booking_type": plan_in.booking_type.value,
                        "description": plan_in.description,
                        "currency": plan_in.currency,
                        "status": EntityStatus.ACTIVE.value,
                    },
                )
                await crud_rate_plan_rate.create(
                    db,
                    obj_in={
                        "rate_plan_id": plan_obj.id,
                        "duration": plan_in.duration,
                        "duration_unit": plan_in.duration_unit.value,
                        "price": plan_in.price,
                        "min_occupancy": rt.base_occupancy,
                        "max_occupancy": rt.max_occupancy,
                    },
                )
                created_plans.append(RatePlanResponse.model_validate(plan_obj))

        prop.setup_step = "TAXES"
        await db.commit()
        return created_plans

    async def setup_taxes(
        self, db: AsyncSession, property_id: str, data: SetupTaxesRequest
    ) -> List[TaxGroupResponse]:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        created_taxes: Dict[str, Any] = {}
        for t_in in data.taxes:
            existing = await crud_tax.get_by_code(
                db, organization_id=prop.organization_id, code=t_in.code
            )
            if not existing:
                tax_obj = await crud_tax.create(
                    db,
                    obj_in={
                        "organization_id": prop.organization_id,
                        "name": t_in.name,
                        "code": t_in.code,
                        "status": EntityStatus.ACTIVE.value,
                    },
                )
                await crud_tax_rate.create(
                    db,
                    obj_in={
                        "tax_id": tax_obj.id,
                        "rate": t_in.rate,
                        "rate_type": t_in.rate_type,
                        "valid_from": date.today(),
                    },
                )
                created_taxes[t_in.code] = tax_obj
            else:
                created_taxes[t_in.code] = existing

        created_groups: List[TaxGroupResponse] = []
        for tg_in in data.tax_groups:
            existing_group = await crud_tax_group.get_by_code(
                db, organization_id=prop.organization_id, code=tg_in.code
            )
            if not existing_group:
                group_obj = await crud_tax_group.create(
                    db,
                    obj_in={
                        "organization_id": prop.organization_id,
                        "name": tg_in.name,
                        "code": tg_in.code,
                        "applies_to": tg_in.applies_to,
                        "status": EntityStatus.ACTIVE.value,
                    },
                )
                seq = 1
                for tax_code in tg_in.tax_codes:
                    tax_entity = created_taxes.get(tax_code)
                    if not tax_entity:
                        tax_entity = await crud_tax.get_by_code(
                            db, organization_id=prop.organization_id, code=tax_code
                        )
                    if tax_entity:
                        await crud_tax_group_item.create(
                            db,
                            obj_in={
                                "tax_group_id": group_obj.id,
                                "tax_id": tax_entity.id,
                                "sequence": seq,
                                "is_compound": tg_in.is_compound,
                            },
                        )
                        seq += 1
                loaded = await crud_tax_group.get_by_code(
                    db, organization_id=prop.organization_id, code=group_obj.code
                )
                if loaded:
                    created_groups.append(TaxGroupResponse.model_validate(loaded))
            else:
                created_groups.append(TaxGroupResponse.model_validate(existing_group))

        if data.apply_to_rate_plans and created_groups:
            primary_group_id = created_groups[0].id
            rate_plans = await crud_rate_plan.get_by_property(db, property_id=property_id)
            for rp in rate_plans:
                rp.tax_group_id = primary_group_id
                rp.is_tax_inclusive = data.is_tax_inclusive

        prop.setup_step = "BOOKING_SETTINGS"
        await db.commit()
        return created_groups

    async def setup_booking_settings(
        self, db: AsyncSession, property_id: str, data: SetupBookingSettingsRequest
    ) -> PropertyBookingSettingsResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        existing = await crud_property_booking_settings.get_by_property(
            db, property_id=property_id
        )

        update_dict = data.model_dump(exclude_unset=True)
        if existing:
            updated = await crud_property_booking_settings.update(
                db, db_obj=existing, obj_in=update_dict
            )
        else:
            update_dict["property_id"] = property_id
            updated = await crud_property_booking_settings.create(db, obj_in=update_dict)

        prop.setup_step = "SETUP_COMPLETE"
        await db.commit()
        return PropertyBookingSettingsResponse.model_validate(updated)

    async def complete_setup(
        self, db: AsyncSession, property_id: str
    ) -> SetupCompleteResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        room_types = await crud_room_type.get_by_property(db, property_id=property_id)
        if not room_types:
            raise ValidationException("Property must have at least one Room Type before completing setup.")

        rooms = await crud_room.get_by_property(db, property_id=property_id)
        if not rooms:
            raise ValidationException("Property must have at least one Room configured before completing setup.")

        rate_plans = await crud_rate_plan.get_by_property(db, property_id=property_id)
        if not rate_plans:
            raise ValidationException("Property must have at least one Rate Plan configured before completing setup.")

        tax_groups = await crud_tax_group.get_by_organization(
            db, organization_id=prop.organization_id
        )

        if not prop.business_date:
            from datetime import date
            prop.business_date = date.today()

        prop.is_setup_completed = True
        prop.setup_step = "COMPLETED"
        prop.status = EntityStatus.ACTIVE.value
        await db.commit()
        await db.refresh(prop)

        return SetupCompleteResponse(
            property_id=prop.id,
            is_setup_completed=True,
            current_step="COMPLETED",
            message="Property setup has been successfully completed! PMS Dashboard is now fully operational.",
            summary={
                "room_types_count": len(room_types),
                "rooms_count": len(rooms),
                "rate_plans_count": len(rate_plans),
                "tax_groups_count": len(tax_groups),
                "status": prop.status,
            },
        )

    async def get_dashboard(
        self, db: AsyncSession, property_id: str
    ) -> PropertyDashboardResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        rooms = await crud_room.get_by_property(db, property_id=property_id)
        room_types = await crud_room_type.get_by_property(db, property_id=property_id)
        rate_plans = await crud_rate_plan.get_by_property(db, property_id=property_id)
        tax_groups = await crud_tax_group.get_by_organization(
            db, organization_id=prop.organization_id
        )
        booking_settings = await crud_property_booking_settings.get_by_property(
            db, property_id=property_id
        )

        available_count = sum(1 for r in rooms if r.status == RoomStatus.AVAILABLE.value)
        maintenance_count = sum(1 for r in rooms if r.status == RoomStatus.MAINTENANCE.value)
        active_rate_plans_count = sum(1 for rp in rate_plans if rp.status == EntityStatus.ACTIVE.value)

        metrics = {
            "total_rooms": len(rooms),
            "available_rooms": available_count,
            "occupied_rooms": 0,
            "maintenance_rooms": maintenance_count,
            "total_room_types": len(room_types),
            "active_rate_plans": active_rate_plans_count,
            "total_tax_groups": len(tax_groups),
        }

        policies = {
            "check_in_time": str(booking_settings.check_in_time) if booking_settings else "14:00:00",
            "check_out_time": str(booking_settings.check_out_time) if booking_settings else "11:00:00",
            "nightly_booking_enabled": booking_settings.nightly_booking_enabled if booking_settings else True,
            "hourly_booking_enabled": booking_settings.hourly_booking_enabled if booking_settings else False,
            "same_day_booking_enabled": booking_settings.same_day_booking_enabled if booking_settings else True,
        }

        readiness = {
            "inventory_ready": len(rooms) > 0 and len(room_types) > 0,
            "pricing_ready": active_rate_plans_count > 0,
            "policies_ready": booking_settings is not None,
            "setup_completed": prop.is_setup_completed,
            "is_operational": prop.is_setup_completed and len(rooms) > 0,
        }

        return PropertyDashboardResponse(
            property=PropertyResponse.model_validate(prop),
            metrics=metrics,
            policies=policies,
            readiness=readiness,
        )


property_setup_service = PropertySetupService()
