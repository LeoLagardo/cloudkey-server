from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.room_type import crud_room_type
from app.crud.room import crud_room
from app.models.room import Room
from app.schemas.room import RoomCreate, RoomUpdate
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)


class RoomService:
    async def get_by_id(self, db: AsyncSession, room_id: str) -> Room:
        room = await crud_room.get(db, room_id)
        if not room:
            raise EntityNotFoundException("Room", room_id)
        return room

    async def list_by_property(
        self, db: AsyncSession, property_id: str, skip: int = 0, limit: int = 100
    ) -> List[Room]:
        return await crud_room.get_by_property(
            db, property_id=property_id, skip=skip, limit=limit
        )

    async def create_room(
        self, db: AsyncSession, property_id: str, room_in: RoomCreate
    ) -> Room:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        # Validate room type belongs to property
        room_type = await crud_room_type.get(db, room_in.room_type_id)
        if not room_type or room_type.property_id != property_id:
            raise ValidationException("Room type does not belong to the specified property.")

        existing = await crud_room.get_by_number(
            db, property_id=property_id, room_number=room_in.room_number
        )
        if existing:
            raise DuplicateEntityException("Room", "room_number", room_in.room_number)

        data = room_in.model_dump(exclude_unset=True)
        data["property_id"] = property_id
        created_room = await crud_room.create(db, obj_in=data)

        from app.services.inventory_service import inventory_service
        await inventory_service.recompute_total_rooms(db, property_id, created_room.room_type_id)

        return created_room

    async def update_room(
        self, db: AsyncSession, room_id: str, room_in: RoomUpdate
    ) -> Room:
        room = await self.get_by_id(db, room_id)
        old_rt_id = room.room_type_id

        if room_in.room_type_id:
            room_type = await crud_room_type.get(db, room_in.room_type_id)
            if not room_type or room_type.property_id != room.property_id:
                raise ValidationException("Room type does not belong to the property.")

        if room_in.room_number and room_in.room_number != room.room_number:
            existing = await crud_room.get_by_number(
                db, property_id=room.property_id, room_number=room_in.room_number
            )
            if existing:
                raise DuplicateEntityException("Room", "room_number", room_in.room_number)

        updated_room = await crud_room.update(db, db_obj=room, obj_in=room_in)

        from app.services.inventory_service import inventory_service
        await inventory_service.recompute_total_rooms(db, updated_room.property_id, updated_room.room_type_id)
        if old_rt_id != updated_room.room_type_id:
            await inventory_service.recompute_total_rooms(db, updated_room.property_id, old_rt_id)

        return updated_room

    async def delete_room(self, db: AsyncSession, room_id: str) -> Room:
        room = await self.get_by_id(db, room_id)
        prop_id = room.property_id
        rt_id = room.room_type_id
        await crud_room.remove(db, id=room_id)

        from app.services.inventory_service import inventory_service
        await inventory_service.recompute_total_rooms(db, prop_id, rt_id)

        return room


room_service = RoomService()
