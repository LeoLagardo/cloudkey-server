import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Date, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import EntityStatus

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.room_type import RoomType
    from app.models.room import Room
    from app.models.rate_plan import RatePlan
    from app.models.property_booking_settings import PropertyBookingSettings
    from app.models.property_settings import PropertySettings
    from app.models.property_user import PropertyUser


class Property(Base):
    __tablename__ = "properties"

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_properties_organization_id_code"),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')",
            name="chk_property_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    address_line_1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Kolkata", nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=EntityStatus.ACTIVE.value,
        nullable=False,
    )
    is_setup_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    setup_step: Mapped[str] = mapped_column(
        Text,
        default="ROOM_TYPES",
        nullable=False,
    )
    business_date: Mapped[Optional[date]] = mapped_column(
        Date,
        default=lambda: datetime.now(timezone.utc).date(),
        nullable=True,
    )
    gstin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classification: Mapped[Optional[str]] = mapped_column(
        Text,
        default="HOTEL",
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
    organization: Mapped["Organization"] = relationship("Organization", back_populates="properties")
    room_types: Mapped[List["RoomType"]] = relationship(
        "RoomType",
        back_populates="property",
        cascade="all, delete-orphan",
    )
    rooms: Mapped[List["Room"]] = relationship(
        "Room",
        back_populates="property",
        cascade="all, delete-orphan",
    )
    rate_plans: Mapped[List["RatePlan"]] = relationship(
        "RatePlan",
        back_populates="property",
        cascade="all, delete-orphan",
    )
    booking_settings: Mapped[Optional["PropertyBookingSettings"]] = relationship(
        "PropertyBookingSettings",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan",
    )
    settings: Mapped[Optional["PropertySettings"]] = relationship(
        "PropertySettings",
        back_populates="property",
        uselist=False,
        cascade="all, delete-orphan",
    )
    users: Mapped[List["PropertyUser"]] = relationship(
        "PropertyUser",
        back_populates="property",
        cascade="all, delete-orphan",
    )
