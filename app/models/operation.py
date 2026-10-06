import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import DocType, NightAuditStatus

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.property import Property
    from app.models.user import User


class NightAudit(Base):
    __tablename__ = "night_audits"

    __table_args__ = (
        UniqueConstraint("property_id", "business_date", name="uq_night_audits_property_date"),
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
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=NightAuditStatus.RUNNING.value,
        nullable=False,
    )
    rooms_posted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_shows_marked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(Text, default="MANUAL", nullable=False)
    summary_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    run_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    property: Mapped["Property"] = relationship("Property")
    runner: Mapped[Optional["User"]] = relationship("User")


class DocumentSequence(Base):
    __tablename__ = "document_sequences"

    __table_args__ = (
        UniqueConstraint("property_id", "doc_type", "period_key", name="uq_doc_sequences_property_type_period"),
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
    doc_type: Mapped[str] = mapped_column(
        Text,
        default=DocType.BOOKING.value,
        nullable=False,
    )
    period_key: Mapped[str] = mapped_column(Text, default="ALL", nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    property: Mapped["Property"] = relationship("Property")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
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
    property_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("properties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_values: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    property: Mapped[Optional["Property"]] = relationship("Property")
    user: Mapped[Optional["User"]] = relationship("User")
