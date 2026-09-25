import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import HousekeepingStatus, OccupancyStatus, RoomStatus

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.room_type import RoomType


class Room(Base):
    __tablename__ = "rooms"

    __table_args__ = (
        UniqueConstraint("property_id", "room_number", name="uq_rooms_property_id_room_number"),
        CheckConstraint(
            "status IN ('AVAILABLE', 'OUT_OF_SERVICE', 'MAINTENANCE', 'INACTIVE')",
            name="chk_room_status",
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
        ForeignKey("room_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    room_number: Mapped[str] = mapped_column(Text, nullable=False)
    floor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        default=RoomStatus.AVAILABLE.value,
        nullable=False,
    )
    occupancy_status: Mapped[str] = mapped_column(
        Text,
        default=OccupancyStatus.VACANT.value,
        nullable=False,
    )
    housekeeping_status: Mapped[str] = mapped_column(
        Text,
        default=HousekeepingStatus.CLEAN.value,
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
    property: Mapped["Property"] = relationship("Property", back_populates="rooms")
    room_type: Mapped["RoomType"] = relationship("RoomType", back_populates="rooms")
