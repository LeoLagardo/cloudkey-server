import uuid
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Time, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.property import Property


class PropertyBookingSettings(Base):
    __tablename__ = "property_booking_settings"

    __table_args__ = (
        UniqueConstraint("property_id", name="uq_property_booking_settings_property_id"),
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
        unique=True,
        nullable=False,
        index=True,
    )
    nightly_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hourly_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimum_hourly_duration: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_hourly_duration: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    hourly_booking_buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    same_day_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_in_time: Mapped[time] = mapped_column(
        Time,
        default=time(14, 0),
        nullable=False,
    )
    check_out_time: Mapped[time] = mapped_column(
        Time,
        default=time(11, 0),
        nullable=False,
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
    property: Mapped["Property"] = relationship("Property", back_populates="booking_settings")
