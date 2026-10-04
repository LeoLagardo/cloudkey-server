from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.property import crud_property
from app.models.guest import Guest
from app.models.reservation import Reservation, ReservationRoom
from app.schemas.guest import (
    GuestCreate,
    GuestUpdate,
    GuestResponse,
    GuestDetailResponse,
    GuestReservationSummary,
)
from app.utils.exceptions import (
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)


class GuestService:
    async def resolve_organization_id(
        self,
        db: AsyncSession,
        property_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> str:
        if organization_id:
            return organization_id
        if property_id:
            prop = await crud_property.get(db, property_id)
            if prop:
                return prop.organization_id
            raise EntityNotFoundException("Property", property_id)
        raise ValidationException("Either property_id or organization_id must be provided.")

    async def list_guests(
        self,
        db: AsyncSession,
        property_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[GuestResponse]:
        org_id = await self.resolve_organization_id(db, property_id, organization_id)

        query = select(Guest).where(Guest.organization_id == org_id)

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Guest.first_name.ilike(search_pattern),
                    Guest.last_name.ilike(search_pattern),
                    Guest.email.ilike(search_pattern),
                    Guest.phone.ilike(search_pattern),
                    Guest.id_number.ilike(search_pattern),
                    Guest.city.ilike(search_pattern),
                )
            )

        query = query.order_by(Guest.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        guests = result.scalars().all()

        responses = []
        for g in guests:
            # Aggregate stays and spent
            agg_query = select(
                func.count(Reservation.id).label("total_stays"),
                func.coalesce(func.sum(Reservation.total_amount), 0).label("total_spent"),
                func.max(Reservation.check_in_at).label("last_stay_at"),
            ).where(
                Reservation.guest_id == g.id,
                Reservation.status.not_in(["CANCELLED", "NO_SHOW"]),
            )
            agg_result = await db.execute(agg_query)
            agg_row = agg_result.one()

            responses.append(
                GuestResponse(
                    id=g.id,
                    organization_id=g.organization_id,
                    first_name=g.first_name,
                    last_name=g.last_name,
                    email=g.email,
                    phone=g.phone,
                    date_of_birth=g.date_of_birth,
                    nationality=g.nationality,
                    id_type=g.id_type,
                    id_number=g.id_number,
                    address_line_1=g.address_line_1,
                    address_line_2=g.address_line_2,
                    city=g.city,
                    state=g.state,
                    country=g.country,
                    postal_code=g.postal_code,
                    gstin=g.gstin,
                    notes=g.notes,
                    total_stays=agg_row.total_stays or 0,
                    total_spent=Decimal(str(agg_row.total_spent or 0)),
                    last_stay_at=agg_row.last_stay_at,
                    created_at=g.created_at,
                    updated_at=g.updated_at,
                )
            )

        return responses

    async def get_guest_by_id(self, db: AsyncSession, guest_id: str) -> GuestDetailResponse:
        res = await db.execute(select(Guest).where(Guest.id == guest_id))
        guest = res.scalar_one_or_none()
        if not guest:
            raise EntityNotFoundException("Guest", guest_id)

        # Get reservations
        res_query = (
            select(Reservation)
            .options(
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
            )
            .where(Reservation.guest_id == guest_id)
            .order_by(Reservation.check_in_at.desc())
        )
        res_result = await db.execute(res_query)
        reservations = res_result.scalars().all()

        reservation_summaries = []
        total_stays = 0
        total_spent = Decimal("0.00")
        last_stay_at = None

        for r in reservations:
            if r.status not in ["CANCELLED", "NO_SHOW"]:
                total_stays += 1
                if r.total_amount:
                    total_spent += Decimal(str(r.total_amount))
                if last_stay_at is None or r.check_in_at > last_stay_at:
                    last_stay_at = r.check_in_at

            room_no = None
            room_type = None
            if r.rooms:
                primary_room = r.rooms[0]
                room_no = primary_room.room.room_number if primary_room.room else None
                room_type = primary_room.room_type.name if primary_room.room_type else None

            reservation_summaries.append(
                GuestReservationSummary(
                    id=r.id,
                    booking_number=r.booking_number,
                    status=r.status,
                    check_in_at=r.check_in_at,
                    check_out_at=r.check_out_at,
                    currency=r.currency or "INR",
                    total_amount=r.total_amount,
                    total_tax_amount=r.total_tax_amount,
                    room_number=room_no,
                    room_type_name=room_type,
                )
            )

        return GuestDetailResponse(
            id=guest.id,
            organization_id=guest.organization_id,
            first_name=guest.first_name,
            last_name=guest.last_name,
            email=guest.email,
            phone=guest.phone,
            date_of_birth=guest.date_of_birth,
            nationality=guest.nationality,
            id_type=guest.id_type,
            id_number=guest.id_number,
            address_line_1=guest.address_line_1,
            address_line_2=guest.address_line_2,
            city=guest.city,
            state=guest.state,
            country=guest.country,
            postal_code=guest.postal_code,
            gstin=guest.gstin,
            notes=guest.notes,
            total_stays=total_stays,
            total_spent=total_spent,
            last_stay_at=last_stay_at,
            created_at=guest.created_at,
            updated_at=guest.updated_at,
            reservations=reservation_summaries,
        )

    async def create_guest(
        self,
        db: AsyncSession,
        guest_in: GuestCreate,
        property_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> GuestResponse:
        org_id = await self.resolve_organization_id(db, property_id, organization_id)

        # Check for duplicate by phone or email within this organization
        conditions = []
        if guest_in.phone:
            conditions.append(Guest.phone == guest_in.phone)
        if guest_in.email:
            conditions.append(Guest.email == str(guest_in.email))

        if conditions:
            dup_query = select(Guest).where(
                Guest.organization_id == org_id,
                or_(*conditions),
            )
            dup_res = await db.execute(dup_query)
            existing = dup_res.scalars().first()
            if existing:
                match_field = "phone" if (guest_in.phone and existing.phone == guest_in.phone) else "email"
                match_val = guest_in.phone if match_field == "phone" else str(guest_in.email)
                raise DuplicateEntityException("Guest", match_field, match_val)

        guest_dict = guest_in.model_dump(exclude_unset=True)
        if "email" in guest_dict and guest_dict["email"] is not None:
            guest_dict["email"] = str(guest_dict["email"])
        guest_dict["organization_id"] = org_id

        guest = Guest(**guest_dict)
        db.add(guest)
        await db.commit()
        await db.refresh(guest)

        return GuestResponse(
            id=guest.id,
            organization_id=guest.organization_id,
            first_name=guest.first_name,
            last_name=guest.last_name,
            email=guest.email,
            phone=guest.phone,
            date_of_birth=guest.date_of_birth,
            nationality=guest.nationality,
            id_type=guest.id_type,
            id_number=guest.id_number,
            address_line_1=guest.address_line_1,
            address_line_2=guest.address_line_2,
            city=guest.city,
            state=guest.state,
            country=guest.country,
            postal_code=guest.postal_code,
            gstin=guest.gstin,
            notes=guest.notes,
            total_stays=0,
            total_spent=Decimal("0.00"),
            last_stay_at=None,
            created_at=guest.created_at,
            updated_at=guest.updated_at,
        )

    async def update_guest(
        self,
        db: AsyncSession,
        guest_id: str,
        guest_in: GuestUpdate,
    ) -> GuestResponse:
        res = await db.execute(select(Guest).where(Guest.id == guest_id))
        guest = res.scalar_one_or_none()
        if not guest:
            raise EntityNotFoundException("Guest", guest_id)

        update_data = guest_in.model_dump(exclude_unset=True)
        if "email" in update_data and update_data["email"] is not None:
            update_data["email"] = str(update_data["email"])

        # Check duplicate if phone/email changed
        if "phone" in update_data and update_data["phone"] != guest.phone:
            dup_res = await db.execute(
                select(Guest).where(
                    Guest.organization_id == guest.organization_id,
                    Guest.phone == update_data["phone"],
                    Guest.id != guest_id,
                )
            )
            if dup_res.scalars().first():
                raise DuplicateEntityException("Guest", "phone", update_data["phone"])

        if "email" in update_data and update_data["email"] != guest.email:
            dup_res = await db.execute(
                select(Guest).where(
                    Guest.organization_id == guest.organization_id,
                    Guest.email == update_data["email"],
                    Guest.id != guest_id,
                )
            )
            if dup_res.scalars().first():
                raise DuplicateEntityException("Guest", "email", update_data["email"])

        for key, val in update_data.items():
            setattr(guest, key, val)

        await db.commit()
        await db.refresh(guest)

        # Get stats
        agg_query = select(
            func.count(Reservation.id).label("total_stays"),
            func.coalesce(func.sum(Reservation.total_amount), 0).label("total_spent"),
            func.max(Reservation.check_in_at).label("last_stay_at"),
        ).where(
            Reservation.guest_id == guest.id,
            Reservation.status.not_in(["CANCELLED", "NO_SHOW"]),
        )
        agg_result = await db.execute(agg_query)
        agg_row = agg_result.one()

        return GuestResponse(
            id=guest.id,
            organization_id=guest.organization_id,
            first_name=guest.first_name,
            last_name=guest.last_name,
            email=guest.email,
            phone=guest.phone,
            date_of_birth=guest.date_of_birth,
            nationality=guest.nationality,
            id_type=guest.id_type,
            id_number=guest.id_number,
            address_line_1=guest.address_line_1,
            address_line_2=guest.address_line_2,
            city=guest.city,
            state=guest.state,
            country=guest.country,
            postal_code=guest.postal_code,
            gstin=guest.gstin,
            notes=guest.notes,
            total_stays=agg_row.total_stays or 0,
            total_spent=Decimal(str(agg_row.total_spent or 0)),
            last_stay_at=agg_row.last_stay_at,
            created_at=guest.created_at,
            updated_at=guest.updated_at,
        )

    async def delete_guest(self, db: AsyncSession, guest_id: str) -> bool:
        res = await db.execute(select(Guest).where(Guest.id == guest_id))
        guest = res.scalar_one_or_none()
        if not guest:
            raise EntityNotFoundException("Guest", guest_id)

        # Check for active reservations
        act_res = await db.execute(
            select(Reservation).where(
                Reservation.guest_id == guest_id,
                Reservation.status.in_(["CONFIRMED", "CHECKED_IN"]),
            )
        )
        if act_res.scalars().first():
            raise ValidationException("Cannot delete guest profile with active or confirmed reservations.")

        await db.delete(guest)
        await db.commit()
        return True


guest_service = GuestService()
