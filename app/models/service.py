import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import EntityStatus, PricingType, ServiceCategory as ServiceCategoryEnum

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.tax import TaxGroup


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_service_categories_property_code"),
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
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("service_categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    system_type: Mapped[str] = mapped_column(
        Text,
        default=ServiceCategoryEnum.OTHER.value,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_tax_group_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("tax_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_hsn_sac_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    parent: Mapped[Optional["ServiceCategory"]] = relationship(
        "ServiceCategory",
        remote_side=[id],
        back_populates="sub_categories",
    )
    sub_categories: Mapped[List["ServiceCategory"]] = relationship(
        "ServiceCategory",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="ServiceCategory.sort_order",
    )
    default_tax_group: Mapped[Optional["TaxGroup"]] = relationship("TaxGroup")
    services: Mapped[List["Service"]] = relationship("Service", back_populates="service_category")


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
    category_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("service_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        Text,
        default=ServiceCategoryEnum.OTHER.value,
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
    service_category: Mapped[Optional["ServiceCategory"]] = relationship(
        "ServiceCategory", back_populates="services"
    )
