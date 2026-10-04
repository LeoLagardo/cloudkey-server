import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import (
    BookingType,
    ReservationSource,
    ReservationStatus,
    RoomBlockType,
)

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.folio import FolioTransaction
    from app.models.guest import Guest
    from app.models.property import Property
    from app.models.rate_plan import RatePlan
    from app.models.rate_plan_rate import RatePlanRate
    from app.models.room import Room
    from app.models.room_type import RoomType
    from app.models.user import User


class Reservation(Base):
    __tablename__ = "reservations"

    __table_args__ = (
        UniqueConstraint("property_id", "booking_number", name="uq_reservations_property_booking_no"),
        Index("ix_reservations_dates", "property_id", "status", "check_in_at", "check_out_at"),
        Index("ix_reservations_guest", "guest_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    property_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_number: Mapped[str] = mapped_column(Text, nullable=False)
    guest_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("guests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    booking_type: Mapped[str] = mapped_column(
        Text,
        default=BookingType.NIGHTLY.value,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        Text,
        default=ReservationSource.DIRECT.value,
        nullable=False,
    )
    channel_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel_booking_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        default=ReservationStatus.CONFIRMED.value,
        nullable=False,
    )
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    check_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    special_requests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    guest: Mapped["Guest"] = relationship("Guest")
    company: Mapped[Optional["Company"]] = relationship("Company")
    creator: Mapped[Optional["User"]] = relationship("User")
    rooms: Mapped[List["ReservationRoom"]] = relationship(
        "ReservationRoom",
        back_populates="reservation",
        cascade="all, delete-orphan",
    )


class ReservationRoom(Base):
    __tablename__ = "reservation_rooms"

    __table_args__ = (
        Index("ix_res_rooms_reservation", "reservation_id"),
        Index("ix_res_rooms_room_dates", "room_id", "check_in_at", "check_out_at"),
        Index("ix_res_rooms_type_dates", "room_type_id", "check_in_at", "check_out_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    reservation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room_type_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("room_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    room_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("rooms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rate_plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rate_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Text,
        default=ReservationStatus.CONFIRMED.value,
        nullable=False,
    )
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    check_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_check_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_check_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    children: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    reservation: Mapped["Reservation"] = relationship("Reservation", back_populates="rooms")
    room_type: Mapped["RoomType"] = relationship("RoomType")
    room: Mapped[Optional["Room"]] = relationship("Room")
    rate_plan: Mapped["RatePlan"] = relationship("RatePlan")
    guests: Mapped[List["ReservationGuest"]] = relationship(
        "ReservationGuest",
        back_populates="reservation_room",
        cascade="all, delete-orphan",
    )
    room_rates: Mapped[List["ReservationRoomRate"]] = relationship(
        "ReservationRoomRate",
        back_populates="reservation_room",
        cascade="all, delete-orphan",
    )

    @property
    def room_number(self) -> Optional[str]:
        return self.room.room_number if self.room else None

    @property
    def room_type_name(self) -> Optional[str]:
        return self.room_type.name if self.room_type else None

    @property
    def rate_plan_name(self) -> Optional[str]:
        return self.rate_plan.name if self.rate_plan else None


class ReservationGuest(Base):
    __tablename__ = "reservation_guests"

    __table_args__ = (
        UniqueConstraint("reservation_room_id", "guest_id", name="uq_reservation_room_guest"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    reservation_room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reservation_rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guest_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("guests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    reservation_room: Mapped["ReservationRoom"] = relationship("ReservationRoom", back_populates="guests")
    guest: Mapped["Guest"] = relationship("Guest")


class RoomBlock(Base):
    __tablename__ = "room_blocks"

    __table_args__ = (
        Index("ix_room_blocks_room", "room_id", "start_at", "end_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    property_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_type: Mapped[str] = mapped_column(
        Text,
        default=RoomBlockType.OUT_OF_ORDER.value,
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    room: Mapped["Room"] = relationship("Room")
    creator: Mapped[Optional["User"]] = relationship("User")


class ReservationRoomRate(Base):
    __tablename__ = "reservation_room_rates"

    __table_args__ = (
        UniqueConstraint("reservation_room_id", "stay_date", name="uq_res_room_rates_stay_date"),
        Index("ix_rrr_stay_date", "stay_date", "folio_transaction_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    reservation_room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reservation_rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stay_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate_plan_rate_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("rate_plan_rates.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    extra_person_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    folio_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("folio_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    reservation_room: Mapped["ReservationRoom"] = relationship("ReservationRoom", back_populates="room_rates")
    rate_plan_rate: Mapped[Optional["RatePlanRate"]] = relationship("RatePlanRate")
    folio_transaction: Mapped[Optional["FolioTransaction"]] = relationship("FolioTransaction")
