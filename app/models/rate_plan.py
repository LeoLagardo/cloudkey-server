import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, String, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Integer, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import BookingType, EntityStatus

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.room_type import RoomType
    from app.models.rate_plan_rate import RatePlanRate
    from app.models.tax import TaxGroup


class RatePlan(Base):
    __tablename__ = "rate_plans"

    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_rate_plans_property_id_code"),
        CheckConstraint(
            "booking_type IN ('NIGHTLY', 'HOURLY')",
            name="chk_rate_plan_booking_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')",
            name="chk_rate_plan_status",
        ),
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
    room_type_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("room_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    booking_type: Mapped[str] = mapped_column(
        Text,
        default=BookingType.NIGHTLY.value,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=EntityStatus.ACTIVE.value,
        nullable=False,
    )
    meal_plan: Mapped[str] = mapped_column(Text, default="EP", nullable=False)
    no_of_meals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color_code: Mapped[str] = mapped_column(String(7), default="#4F46E5", nullable=False)
    extra_adult_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    extra_child_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_group_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("tax_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_tax_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Booking Engine Publishing & Merchandising
    is_public_booking_engine: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    public_badge: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    included_perks: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    photos: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    public_sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    property: Mapped["Property"] = relationship("Property", back_populates="rate_plans")
    room_type: Mapped["RoomType"] = relationship("RoomType", back_populates="rate_plans")
    tax_group: Mapped[Optional["TaxGroup"]] = relationship("TaxGroup")
    rates: Mapped[List["RatePlanRate"]] = relationship(
        "RatePlanRate",
        back_populates="rate_plan",
        cascade="all, delete-orphan",
    )
