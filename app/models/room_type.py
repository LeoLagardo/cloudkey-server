import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import EntityStatus

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.room import Room
    from app.models.rate_plan import RatePlan


class RoomType(Base):
    __tablename__ = "room_types"

    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_room_types_property_id_code"),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')",
            name="chk_room_type_status",
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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_occupancy: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    base_occupancy: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=EntityStatus.ACTIVE.value,
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
    property: Mapped["Property"] = relationship("Property", back_populates="room_types")
    rooms: Mapped[List["Room"]] = relationship(
        "Room",
        back_populates="room_type",
    )
    rate_plans: Mapped[List["RatePlan"]] = relationship(
        "RatePlan",
        back_populates="room_type",
        cascade="all, delete-orphan",
    )
