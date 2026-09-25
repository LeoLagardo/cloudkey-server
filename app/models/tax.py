import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import EntityStatus, TaxAppliesTo, TaxRateType

if TYPE_CHECKING:
    from app.models.organization import Organization


class Tax(Base):
    __tablename__ = "taxes"

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_taxes_org_code"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
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
    organization: Mapped["Organization"] = relationship("Organization")
    rates: Mapped[List["TaxRate"]] = relationship(
        "TaxRate",
        back_populates="tax",
        cascade="all, delete-orphan",
    )
    group_items: Mapped[List["TaxGroupItem"]] = relationship(
        "TaxGroupItem",
        back_populates="tax",
        cascade="all, delete-orphan",
    )


class TaxRate(Base):
    __tablename__ = "tax_rates"

    __table_args__ = (
        Index("ix_tax_rates_lookup", "tax_id", "valid_from", "valid_to"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    tax_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("taxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rate_type: Mapped[str] = mapped_column(
        Text,
        default=TaxRateType.PERCENTAGE.value,
        nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    min_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    max_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

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
    tax: Mapped["Tax"] = relationship("Tax", back_populates="rates")


class TaxGroup(Base):
    __tablename__ = "tax_groups"

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_tax_groups_org_code"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to: Mapped[str] = mapped_column(
        Text,
        default=TaxAppliesTo.ROOM.value,
        nullable=False,
    )
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
    organization: Mapped["Organization"] = relationship("Organization")
    items: Mapped[List["TaxGroupItem"]] = relationship(
        "TaxGroupItem",
        back_populates="tax_group",
        cascade="all, delete-orphan",
        order_by="TaxGroupItem.sequence",
    )


class TaxGroupItem(Base):
    __tablename__ = "tax_group_items"

    __table_args__ = (
        UniqueConstraint("tax_group_id", "tax_id", name="uq_tax_group_items_group_tax"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    tax_group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tax_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tax_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("taxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_compound: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    tax_group: Mapped["TaxGroup"] = relationship("TaxGroup", back_populates="items")
    tax: Mapped["Tax"] = relationship("Tax", back_populates="group_items")
