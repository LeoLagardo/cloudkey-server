from typing import List, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reservation import (
    Reservation,
    ReservationRoom,
    ReservationGuest,
    ReservationRoomRate,
)
from app.models.folio import Folio, Payment


class CRUDReservation:
    async def get_by_id(
        self,
        db: AsyncSession,
        reservation_id: str,
        property_id: Optional[str] = None,
    ) -> Optional[Reservation]:
        """Fetch reservation with fully loaded relations."""
        query = (
            select(Reservation)
            .where(or_(Reservation.id == reservation_id, Reservation.booking_number == reservation_id))
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.rate_plan),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_rates),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.guests).selectinload(ReservationGuest.guest),
            )
        )
        if property_id:
            query = query.where(Reservation.property_id == property_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_booking_number(
        self,
        db: AsyncSession,
        property_id: str,
        booking_number: str,
    ) -> Optional[Reservation]:
        """Look up reservation by property ID and unique booking number."""
        result = await db.execute(
            select(Reservation).where(
                Reservation.property_id == property_id,
                Reservation.booking_number == booking_number,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_property(
        self,
        db: AsyncSession,
        property_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Reservation]:
        """List reservations for a property with optional status filtering."""
        query = (
            select(Reservation)
            .where(Reservation.property_id == property_id)
            .options(
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.rate_plan),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_rates),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.guests).selectinload(ReservationGuest.guest),
            )
            .order_by(Reservation.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status:
            query = query.where(Reservation.status == status)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_reservation_folio(
        self,
        db: AsyncSession,
        reservation_id: str,
    ) -> Optional[Folio]:
        """Get the primary open folio for a reservation."""
        result = await db.execute(
            select(Folio)
            .where(Folio.reservation_id == reservation_id)
            .order_by(Folio.created_at.asc())
        )
        return result.scalars().first()

    async def get_reservation_payments(
        self,
        db: AsyncSession,
        reservation_id: str,
    ) -> List[Payment]:
        """Get all payments associated with a reservation."""
        result = await db.execute(
            select(Payment)
            .where(Payment.reservation_id == reservation_id)
            .order_by(Payment.created_at.asc())
        )
        return list(result.scalars().all())


crud_reservation = CRUDReservation()
