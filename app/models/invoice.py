import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import InvoiceStatus, InvoiceType

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.folio import Folio, FolioTransaction
    from app.models.guest import Guest
    from app.models.property import Property


class Invoice(Base):
    __tablename__ = "invoices"

    __table_args__ = (
        UniqueConstraint("property_id", "invoice_number", name="uq_invoices_property_number"),
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
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_type: Mapped[str] = mapped_column(
        Text,
        default=InvoiceType.TAX_INVOICE.value,
        nullable=False,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
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
    bill_to_name: Mapped[str] = mapped_column(Text, nullable=False)
    bill_to_gstin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bill_to_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=InvoiceStatus.ISSUED.value,
        nullable=False,
    )
    original_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    folio: Mapped["Folio"] = relationship("Folio")
    guest: Mapped[Optional["Guest"]] = relationship("Guest")
    company: Mapped[Optional["Company"]] = relationship("Company")
    original_invoice: Mapped[Optional["Invoice"]] = relationship("Invoice", remote_side=[id])
    lines: Mapped[List["InvoiceLine"]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    invoice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folio_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("folio_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hsn_sac_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_breakdown: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
    folio_transaction: Mapped[Optional["FolioTransaction"]] = relationship("FolioTransaction")
