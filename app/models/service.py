import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import EntityStatus, PricingType, ServiceCategory

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.tax import TaxGroup


class Service(Base):
    __tablename__ = "services"

    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_services_property_id_code"),
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
    category: Mapped[str] = mapped_column(
        Text,
        default=ServiceCategory.OTHER.value,
        nullable=False,
    )
    pricing_type: Mapped[str] = mapped_column(
        Text,
        default=PricingType.FIXED.value,
        nullable=False,
    )
    default_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    tax_group_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("tax_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_tax_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hsn_sac_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    property: Mapped["Property"] = relationship("Property")
    tax_group: Mapped[Optional["TaxGroup"]] = relationship("TaxGroup")
