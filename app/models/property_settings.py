import uuid
from datetime import datetime, time, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import (
    String,
    DateTime,
    Time,
    ForeignKey,
    Integer,
    UniqueConstraint,
    JSON,
    Text,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.property import Property


class PropertySettings(Base):
    __tablename__ = "property_settings"

    __table_args__ = (
        UniqueConstraint("property_id", name="uq_property_settings_property_id"),
        CheckConstraint(
            "time_format IN ('12H', '24H')",
            name="chk_property_settings_time_format",
        ),
        CheckConstraint(
            "same_day_checkout_rule IN ('FULL_NIGHT', 'PARTIAL', 'DAY_USE')",
            name="chk_property_settings_same_day_checkout_rule",
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
        unique=True,
        nullable=False,
        index=True,
    )
    date_format: Mapped[str] = mapped_column(Text, default="DD/MM/YYYY", nullable=False)
    time_format: Mapped[str] = mapped_column(Text, default="24H", nullable=False)
    language: Mapped[str] = mapped_column(Text, default="en", nullable=False)
    number_format: Mapped[str] = mapped_column(Text, default="en-IN", nullable=False)
    week_start_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    night_audit_time: Mapped[time] = mapped_column(
        Time,
        default=time(2, 0),
        nullable=False,
    )
    same_day_checkout_rule: Mapped[str] = mapped_column(
        Text, default="FULL_NIGHT", nullable=False
    )
    invoice_prefix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

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

    # Relationship
    property: Mapped["Property"] = relationship("Property", back_populates="settings")
