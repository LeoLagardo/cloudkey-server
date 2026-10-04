from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.room_type import crud_room_type
from app.models.room_type import RoomType
from app.schemas.room_type import RoomTypeCreate, RoomTypeUpdate
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)


class RoomTypeService:
    async def get_by_id(self, db: AsyncSession, room_type_id: str) -> RoomType:
        rt = await crud_room_type.get(db, room_type_id)
        if not rt:
            raise EntityNotFoundException("RoomType", room_type_id)
        return rt

    async def list_by_property(
        self, db: AsyncSession, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[RoomType]:
        return await crud_room_type.get_by_property(
            db, property_id=property_id, skip=skip, limit=limit
        )

    async def create_room_type(
        self, db: AsyncSession, property_id: str, rt_in: RoomTypeCreate
    ) -> RoomType:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        if rt_in.base_occupancy > rt_in.max_occupancy:
            raise ValidationException("base_occupancy cannot exceed max_occupancy.")

        existing = await crud_room_type.get_by_code(
            db, property_id=property_id, code=rt_in.code
        )
        if existing:
            raise DuplicateEntityException("RoomType", "code", rt_in.code)

        data = rt_in.model_dump(exclude_unset=True)
        data["property_id"] = property_id
        new_rt = await crud_room_type.create(db, obj_in=data)

        # Initialize 365-day rolling inventory for newly created room type
        from app.services.inventory_service import inventory_service
        await inventory_service.generate_rolling_window(db, property_id=property_id, room_type_id=new_rt.id, days=365)

        return new_rt

    async def update_room_type(
        self, db: AsyncSession, room_type_id: str, rt_in: RoomTypeUpdate
    ) -> RoomType:
        rt = await self.get_by_id(db, room_type_id)

        base_occ = rt_in.base_occupancy if rt_in.base_occupancy is not None else rt.base_occupancy
        max_occ = rt_in.max_occupancy if rt_in.max_occupancy is not None else rt.max_occupancy
        if base_occ > max_occ:
            raise ValidationException("base_occupancy cannot exceed max_occupancy.")

        if rt_in.code and rt_in.code != rt.code:
            existing = await crud_room_type.get_by_code(
                db, property_id=rt.property_id, code=rt_in.code
            )
            if existing:
                raise DuplicateEntityException("RoomType", "code", rt_in.code)

        return await crud_room_type.update(db, db_obj=rt, obj_in=rt_in)

    async def delete_room_type(self, db: AsyncSession, room_type_id: str) -> RoomType:
        rt = await self.get_by_id(db, room_type_id)
        await crud_room_type.remove(db, id=room_type_id)
        return rt


room_type_service = RoomTypeService()
