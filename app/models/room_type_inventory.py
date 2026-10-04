import uuid
from datetime import date, datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from app.database import Base

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.room_type import RoomType


class RoomTypeInventory(Base):
    __tablename__ = "room_type_inventory"

    __table_args__ = (
        UniqueConstraint("property_id", "room_type_id", "stay_date", name="uq_rti_property_room_type_date"),
        Index("ix_rti_lookup", "property_id", "room_type_id", "stay_date"),
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
    stay_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    total_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_rooms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sold_rooms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overbooking_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    stop_sell: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_to_arrival: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_to_departure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_stay: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_stay: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    room_type: Mapped["RoomType"] = relationship("RoomType")

    @hybrid_property
    def available(self) -> int:
        """
        Computed available rooms:
        available = total_rooms - blocked_rooms - sold_rooms + overbooking_limit
        """
        return self.total_rooms - self.blocked_rooms - self.sold_rooms + self.overbooking_limit

    @available.expression
    def available(cls):
        return cls.total_rooms - cls.blocked_rooms - cls.sold_rooms + cls.overbooking_limit
