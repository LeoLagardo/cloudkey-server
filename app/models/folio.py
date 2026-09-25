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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import (
    EntityStatus,
    FolioEntryType,
    FolioStatus,
    FolioTransactionSource,
    FolioTransactionType,
    FolioType,
    PaymentMethodType,
    PaymentStatus,
    PaymentType,
)

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.guest import Guest
    from app.models.property import Property
    from app.models.reservation import Reservation, ReservationRoom
    from app.models.service import Service
    from app.models.tax import Tax, TaxGroup, TaxRate
    from app.models.user import User


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_payment_methods_property_code"),
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
    method_type: Mapped[str] = mapped_column(
        Text,
        default=PaymentMethodType.CASH.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        default=EntityStatus.ACTIVE.value,
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")


class Folio(Base):
    __tablename__ = "folios"

    __table_args__ = (
        UniqueConstraint("property_id", "folio_number", name="uq_folios_property_number"),
        Index("ix_folios_reservation", "reservation_id"),
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
    reservation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reservations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reservation_room_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reservation_rooms.id", ondelete="SET NULL"),
        nullable=True,
    )
    guest_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("guests.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    folio_number: Mapped[str] = mapped_column(Text, nullable=False)
    folio_type: Mapped[str] = mapped_column(
        Text,
        default=FolioType.GUEST.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        default=FolioStatus.OPEN.value,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
    reservation: Mapped[Optional["Reservation"]] = relationship("Reservation")
    reservation_room: Mapped[Optional["ReservationRoom"]] = relationship("ReservationRoom")
    guest: Mapped[Optional["Guest"]] = relationship("Guest")
    company: Mapped[Optional["Company"]] = relationship("Company")
    closer: Mapped[Optional["User"]] = relationship("User")
    transactions: Mapped[List["FolioTransaction"]] = relationship(
        "FolioTransaction",
        back_populates="folio",
        cascade="all, delete-orphan",
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="folio",
        cascade="all, delete-orphan",
    )


class Payment(Base):
    __tablename__ = "payments"

    __table_args__ = (
        Index("ix_payments_folio", "folio_id"),
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
    folio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("folios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reservations.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_method_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("payment_methods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_type: Mapped[str] = mapped_column(
        Text,
        default=PaymentType.SETTLEMENT.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        default=PaymentStatus.CAPTURED.value,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    gateway: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gateway_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    card_last4: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
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
    folio: Mapped["Folio"] = relationship("Folio", back_populates="payments")
    reservation: Mapped[Optional["Reservation"]] = relationship("Reservation")
    payment_method: Mapped["PaymentMethod"] = relationship("PaymentMethod")
    receiver: Mapped[Optional["User"]] = relationship("User")


class FolioTransaction(Base):
    __tablename__ = "folio_transactions"

    __table_args__ = (
        Index("ix_folio_txn_folio", "folio_id"),
        Index("ix_folio_txn_bdate", "property_id", "business_date"),
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
    folio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("folios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        Text,
        default=FolioEntryType.DEBIT.value,
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(
        Text,
        default=FolioTransactionType.ROOM_CHARGE.value,
        nullable=False,
    )
    service_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_group_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("tax_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_tax_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hsn_sac_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        Text,
        default=FolioTransactionSource.MANUAL.value,
        nullable=False,
    )
    reverses_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("folio_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    folio: Mapped["Folio"] = relationship("Folio", back_populates="transactions")
    service: Mapped[Optional["Service"]] = relationship("Service")
    payment: Mapped[Optional["Payment"]] = relationship("Payment")
    tax_group: Mapped[Optional["TaxGroup"]] = relationship("TaxGroup")
    poster: Mapped[Optional["User"]] = relationship("User")
    taxes: Mapped[List["FolioTransactionTax"]] = relationship(
        "FolioTransactionTax",
        back_populates="folio_transaction",
        cascade="all, delete-orphan",
    )


class FolioTransactionTax(Base):
    __tablename__ = "folio_transaction_taxes"

    __table_args__ = (
        Index("ix_folio_txn_taxes_txn", "folio_transaction_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    folio_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("folio_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tax_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("taxes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tax_rate_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("tax_rates.id", ondelete="SET NULL"),
        nullable=True,
    )
    tax_name: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    folio_transaction: Mapped["FolioTransaction"] = relationship("FolioTransaction", back_populates="taxes")
    tax: Mapped["Tax"] = relationship("Tax")
    tax_rate: Mapped[Optional["TaxRate"]] = relationship("TaxRate")
