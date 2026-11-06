import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.property import Property


class PropertyBookingEngineConfig(Base):
    __tablename__ = "property_booking_engine_configs"

    __table_args__ = (
        UniqueConstraint("property_id", name="uq_pbec_property_id"),
        UniqueConstraint("slug", name="uq_pbec_slug"),
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
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    domain_status: Mapped[str] = mapped_column(String(50), default="UNCONFIGURED", nullable=False)
    domain_verification_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Hotel Group Switching (e.g., Taj Hotels)
    allow_group_switching: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    group_display_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Theme & Visual Identity
    theme_preset: Mapped[str] = mapped_column(String(50), default="emerald-azure", nullable=False)
    custom_colors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    custom_fonts: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Branding & Media Assets
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hero_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hero_subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hero_banner_images: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    concierge_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    concierge_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_amenities: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    gallery_photos: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Rate Plan Online Distribution & Badges
    published_rate_plan_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    rate_plan_badges: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)

    # Payment Settings & Gateways
    pay_at_hotel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    advance_payment_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deposit_type: Mapped[str] = mapped_column(String(50), default="FULL", nullable=False)
    deposit_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("20.00"), nullable=False)
    deposit_fixed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    razorpay_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    razorpay_key_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    razorpay_key_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    razorpay_webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    stripe_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stripe_publishable_key: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    stripe_secret_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Policies & Legal
    cancellation_policy_type: Mapped[str] = mapped_column(String(50), default="FREE", nullable=False)
    cancellation_deadline_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    cancellation_policy_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    terms_and_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    privacy_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    house_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SEO & Metadata
    meta_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    og_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    property: Mapped["Property"] = relationship("Property", back_populates="booking_engine_config")

