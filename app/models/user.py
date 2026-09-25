import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign

from app.database import Base

if TYPE_CHECKING:
    from app.models.organization_user import OrganizationUser
    from app.models.property_user import PropertyUser


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    # Memberships
    organization_memberships: Mapped[List["OrganizationUser"]] = relationship(
        "OrganizationUser",
        primaryjoin="User.id == foreign(OrganizationUser.user_id)",
        cascade="all, delete-orphan",
        lazy="selectin",
        viewonly=True,
    )
    property_memberships: Mapped[List["PropertyUser"]] = relationship(
        "PropertyUser",
        primaryjoin="User.id == foreign(PropertyUser.user_id)",
        cascade="all, delete-orphan",
        lazy="selectin",
        viewonly=True,
    )
