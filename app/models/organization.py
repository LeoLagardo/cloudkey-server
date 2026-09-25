import uuid
from datetime import datetime, timezone
from typing import List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import OrganizationStatus

if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.organization_user import OrganizationUser
    from app.models.role import Role


class Organization(Base):
    __tablename__ = "organizations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'ARCHIVED')",
            name="chk_organization_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=OrganizationStatus.ACTIVE.value,
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
    properties: Mapped[List["Property"]] = relationship(
        "Property",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    users: Mapped[List["OrganizationUser"]] = relationship(
        "OrganizationUser",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
