import uuid
from datetime import datetime, date, timezone
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import String, Text, DateTime, Date, Integer, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.rate_plan import RatePlan


class RatePlanRate(Base):
    __tablename__ = "rate_plan_rates"

    __table_args__ = (
        CheckConstraint(
            "duration_unit IN ('HOUR', 'NIGHT')",
            name="chk_rate_plan_rate_duration_unit",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    rate_plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rate_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_occupancy: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_occupancy: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
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
    rate_plan: Mapped["RatePlan"] = relationship("RatePlan", back_populates="rates")
