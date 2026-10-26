import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.room_type import RoomType
    from app.models.rate_plan import RatePlan


class AiosellPropertyConfig(Base):
    __tablename__ = "aiosell_property_configs"

    __table_args__ = (
        UniqueConstraint("property_id", name="uq_aiosell_property_configs_property_id"),
        UniqueConstraint("aiosell_hotel_code", name="uq_aiosell_property_configs_hotel_code"),
        Index("ix_aiosell_hotel_lookup", "aiosell_hotel_code"),
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
    aiosell_hotel_code: Mapped[str] = mapped_column(String(100), nullable=False)
    pms_slug: Mapped[str] = mapped_column(String(100), default="sample-pms", nullable=False)
    api_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    card_decryption_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_rates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_restrictions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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


class AiosellRoomTypeMapping(Base):
    __tablename__ = "aiosell_room_type_mappings"

    __table_args__ = (
        UniqueConstraint("property_id", "room_type_id", name="uq_aiosell_room_mapping_type"),
        UniqueConstraint("property_id", "aiosell_room_code", name="uq_aiosell_room_mapping_code"),
        Index("ix_aiosell_room_mapping_lookup", "property_id", "aiosell_room_code"),
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
    aiosell_room_code: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    room_type: Mapped["RoomType"] = relationship("RoomType")


class AiosellRatePlanMapping(Base):
    __tablename__ = "aiosell_rate_plan_mappings"

    __table_args__ = (
        UniqueConstraint("property_id", "rate_plan_id", name="uq_aiosell_rate_mapping_plan"),
        UniqueConstraint("property_id", "aiosell_rateplan_code", name="uq_aiosell_rate_mapping_code"),
        Index("ix_aiosell_rate_mapping_lookup", "property_id", "aiosell_rateplan_code"),
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
    rate_plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rate_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aiosell_rateplan_code: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    rate_plan: Mapped["RatePlan"] = relationship("RatePlan")
