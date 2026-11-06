import socket
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.property import crud_property
from app.crud.property_booking_engine_config import crud_property_booking_engine_config
from app.models.organization import Organization
from app.models.property_booking_engine_config import PropertyBookingEngineConfig
from app.schemas.property_booking_engine_config import (
    PropertyBookingEngineConfigCreate,
    PropertyBookingEngineConfigUpdate,
    PropertyBookingEngineConfigResponse,
    DomainVerifyResponse,
    GatewayTestRequest,
    GatewayTestResponse,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException


class BookingEngineConfigService:
    def _mask_secret(self, secret: Optional[str]) -> Optional[str]:
        if not secret:
            return None
        if len(secret) <= 6:
            return "••••••"
        return f"{secret[:3]}••••{secret[-3:]}"

    def build_response(self, config: PropertyBookingEngineConfig) -> PropertyBookingEngineConfigResponse:
        resp = PropertyBookingEngineConfigResponse.model_validate(config)
        resp.razorpay_key_secret_masked = self._mask_secret(config.razorpay_key_secret)
        resp.stripe_secret_key_masked = self._mask_secret(config.stripe_secret_key)
        # Never leak raw secrets in the response
        resp.razorpay_key_secret = None
        resp.stripe_secret_key = None

        colors = config.custom_colors or {}
        fonts = config.custom_fonts or {}
        resp.primary_color = colors.get("primary") or colors.get("primary_color") or "#064E3B"
        resp.accent_color = colors.get("accent") or colors.get("accent_color") or "#D97706"
        resp.background_color = colors.get("background") or colors.get("background_color") or "#022C22"
        resp.surface_color = colors.get("surface") or colors.get("surface_color") or "#04382C"
        resp.font_family = fonts.get("font_family") or fonts.get("display") or "Inter"
        resp.is_enabled = config.is_active
        resp.public_engine_url = f"http://localhost:5173/{config.slug}"
        return resp

    async def get_or_create_default(
        self, db: AsyncSession, property_id: str
    ) -> PropertyBookingEngineConfig:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        config = await crud_property_booking_engine_config.get_by_property(db, property_id=property_id)
        if not config:
            # Generate clean default slug from property name & code
            slug_candidate = (
                prop.name.lower()
                .replace(" ", "-")
                .replace("&", "and")
                .replace("'", "")
                .replace(".", "")
            )
            # Ensure unique slug
            existing = await crud_property_booking_engine_config.get_by_slug(db, slug_candidate)
            if existing:
                slug_candidate = f"{slug_candidate}-{prop.code.lower()}"

            org = await db.get(Organization, prop.organization_id) if prop.organization_id else None
            new_config = PropertyBookingEngineConfig(
                property_id=property_id,
                slug=slug_candidate,
                custom_domain=None,
                domain_status="UNCONFIGURED",
                domain_verification_token=f"ck-verify-{prop.code.lower()}",
                is_active=True,
                allow_group_switching=True,
                group_display_name=org.name if org else None,
                theme_preset="emerald-azure",
                hero_title=f"Welcome to {prop.name}",
                hero_subtitle="An exceptional sanctuary of timeless elegance, tailored luxury, and bespoke service.",
                hero_banner_images=[
                    "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1600&q=80",
                    "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=1600&q=80",
                ],
                concierge_phone=prop.address_line_1,
                concierge_email=f"reservations@{slug_candidate}.com",
                property_amenities=[
                    {"id": "wifi", "name": "Complimentary Fiber Wi-Fi", "icon": "Wifi"},
                    {"id": "pool", "name": "Heated Infinity Plunge Pools", "icon": "Waves"},
                    {"id": "spa", "name": "Ayurvedic & Holistic Spa", "icon": "Sparkles"},
                    {"id": "butler", "name": "24/7 Dedicated Butler Desk", "icon": "UserCheck"},
                    {"id": "valet", "name": "Valet Parking & EV Charging", "icon": "Car"},
                ],
                gallery_photos=[
                    "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1200&q=80",
                    "https://images.unsplash.com/photo-1533105079780-92b9be482077?auto=format&fit=crop&w=1200&q=80",
                ],
                published_rate_plan_ids=[],
                rate_plan_badges={},
                pay_at_hotel_enabled=True,
                advance_payment_enabled=False,
                deposit_type="FULL",
                deposit_percentage=Decimal("20.00"),
                deposit_fixed_amount=Decimal("0.00"),
                razorpay_enabled=False,
                stripe_enabled=False,
                cancellation_policy_type="FREE",
                cancellation_deadline_hours=48,
                cancellation_policy_text="Free cancellation up to 48 hours prior to check-in. Cancellations within 48 hours are subject to a one-night room charge.",
                terms_and_conditions="Guests must present government-issued photo identification and credit card upon check-in. Special requests are subject to availability upon check-in.",
                privacy_policy="Your personal data is encrypted and used exclusively for your reservation and stay management.",
                house_rules="Check-in from 14:00. Check-out until 11:00. No smoking inside suites. Pet accommodations upon advance request.",
                meta_title=f"{prop.name} | Official Direct Host Booking",
                meta_description=f"Book direct at {prop.name} for the guaranteed best rates, exclusive perks, and flexible cancellation.",
            )
            db.add(new_config)
            await db.commit()
            await db.refresh(new_config)
            config = new_config

        return config

    async def update_config(
        self,
        db: AsyncSession,
        property_id: str,
        config_in: PropertyBookingEngineConfigUpdate,
    ) -> PropertyBookingEngineConfig:
        config = await self.get_or_create_default(db, property_id)

        update_dict = config_in.model_dump(exclude_unset=True)

        # Validate unique slug if changed
        if "slug" in update_dict and update_dict["slug"] != config.slug:
            existing = await crud_property_booking_engine_config.get_by_slug(db, update_dict["slug"])
            if existing and existing.id != config.id:
                raise ValidationException(f"Booking engine slug '{update_dict['slug']}' is already in use.")

        # Validate unique custom domain if changed
        if "custom_domain" in update_dict and update_dict["custom_domain"]:
            clean_domain = update_dict["custom_domain"].lower().strip()
            update_dict["custom_domain"] = clean_domain
            if clean_domain != config.custom_domain:
                existing_domain = await crud_property_booking_engine_config.get_by_custom_domain(db, clean_domain)
                if existing_domain and existing_domain.id != config.id:
                    raise ValidationException(f"Domain '{clean_domain}' is already assigned to another property.")
                update_dict["domain_status"] = "PENDING_DNS"

        # Preserve existing secrets if empty string or placeholder masked value passed
        if "razorpay_key_secret" in update_dict:
            if not update_dict["razorpay_key_secret"] or "••••" in update_dict["razorpay_key_secret"]:
                del update_dict["razorpay_key_secret"]

        if "stripe_secret_key" in update_dict:
            if not update_dict["stripe_secret_key"] or "••••" in update_dict["stripe_secret_key"]:
                del update_dict["stripe_secret_key"]

        # Synchronize color fields into custom_colors dict
        colors = dict(config.custom_colors or {})
        for col_field in ["primary_color", "accent_color", "background_color", "surface_color"]:
            if col_field in update_dict and update_dict[col_field]:
                short_name = col_field.replace("_color", "")
                colors[short_name] = update_dict[col_field]
                colors[col_field] = update_dict[col_field]
                del update_dict[col_field]
        if "custom_colors" in update_dict and isinstance(update_dict["custom_colors"], dict):
            colors.update(update_dict["custom_colors"])
            del update_dict["custom_colors"]
        config.custom_colors = colors

        # Synchronize font fields into custom_fonts dict
        fonts = dict(config.custom_fonts or {})
        if "font_family" in update_dict and update_dict["font_family"]:
            fonts["font_family"] = update_dict["font_family"]
            fonts["display"] = update_dict["font_family"]
            fonts["body"] = update_dict["font_family"]
            del update_dict["font_family"]
        if "custom_fonts" in update_dict and isinstance(update_dict["custom_fonts"], dict):
            fonts.update(update_dict["custom_fonts"])
            del update_dict["custom_fonts"]
        config.custom_fonts = fonts

        if "is_enabled" in update_dict:
            if update_dict["is_enabled"] is not None:
                config.is_active = bool(update_dict["is_enabled"])
            del update_dict["is_enabled"]

        for k, v in update_dict.items():
            if hasattr(config, k):
                setattr(config, k, v)

        config.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(config)
        return config

    async def verify_domain(
        self, db: AsyncSession, property_id: str
    ) -> DomainVerifyResponse:
        config = await self.get_or_create_default(db, property_id)
        if not config.custom_domain:
            raise ValidationException("No custom domain configured for this property.")

        domain = config.custom_domain
        cname_target = "cname.cloudkey.io"

        # Check DNS resolution
        is_verified = False
        current_val = None
        try:
            # Check host resolution
            current_val = socket.gethostbyname(domain)
            is_verified = True
            config.domain_status = "ACTIVE"
            msg = f"Domain {domain} successfully resolved to {current_val}."
        except Exception as e:
            config.domain_status = "PENDING_DNS"
            msg = f"DNS lookup pending or unpropagated: {str(e)}. Point CNAME to {cname_target}."

        await db.commit()
        return DomainVerifyResponse(
            custom_domain=domain,
            domain_status=config.domain_status,
            is_verified=is_verified,
            cname_target=cname_target,
            current_dns_value=current_val,
            message=msg,
        )

    async def test_gateway(
        self, db: AsyncSession, property_id: str, test_in: GatewayTestRequest
    ) -> GatewayTestResponse:
        config = await self.get_or_create_default(db, property_id)
        gateway = test_in.gateway.upper()

        if gateway == "RAZORPAY":
            key_id = test_in.key_id or config.razorpay_key_id
            key_secret = test_in.key_secret or config.razorpay_key_secret
            if not key_id or not key_secret:
                return GatewayTestResponse(gateway="RAZORPAY", success=False, message="Razorpay Key ID and Secret are required.")
            if not key_id.startswith("rzp_"):
                return GatewayTestResponse(gateway="RAZORPAY", success=False, message="Invalid Razorpay Key ID format (must start with rzp_).")
            return GatewayTestResponse(gateway="RAZORPAY", success=True, message="Razorpay credentials format verified successfully.")

        elif gateway == "STRIPE":
            pub_key = test_in.key_id or config.stripe_publishable_key
            sec_key = test_in.key_secret or config.stripe_secret_key
            if not pub_key or not sec_key:
                return GatewayTestResponse(gateway="STRIPE", success=False, message="Stripe Publishable Key and Secret Key are required.")
            if not (pub_key.startswith("pk_") and sec_key.startswith("sk_")):
                return GatewayTestResponse(gateway="STRIPE", success=False, message="Invalid Stripe key format (must start with pk_ and sk_).")
            return GatewayTestResponse(gateway="STRIPE", success=True, message="Stripe credentials format verified successfully.")

        return GatewayTestResponse(gateway=gateway, success=False, message=f"Unsupported gateway '{gateway}'.")


booking_engine_config_service = BookingEngineConfigService()
