import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.guest import crud_guest
from app.crud.property import crud_property
from app.crud.reservation import crud_reservation
from app.crud.service import crud_service
from app.models.guest import Guest
from app.models.folio import Folio, FolioTransaction, Payment, PaymentMethod
from app.models.operation import AuditLog
from app.models.organization import Organization
from app.models.property import Property
from app.models.property_booking_engine_config import PropertyBookingEngineConfig
from app.models.rate_plan import RatePlan
from app.models.rate_plan_rate import RatePlanRate
from app.models.reservation import (
    Reservation,
    ReservationGuest,
    ReservationRoom,
    ReservationRoomRate,
)
from app.models.room_type import RoomType
from app.models.room_type_inventory import RoomTypeInventory
from app.models.service import Service
from app.models.tax import TaxGroup, TaxRate
from app.schemas.property_booking_engine_config import (
    PublicGroupHotelSummary,
    PublicResolvedPropertyResponse,
    PublicBookingEngineConfigResponse,
    PublicRatePlanSummary,
    PublicRoomTypeAvailabilityResponse,
    PublicAvailabilitySearchResponse,
    PublicRateCalendarDay,
    PublicQuoteRequest,
    PublicQuoteResponse,
    PublicBookingCreateRequest,
    PublicBookingConfirmationResponse,
    PublicBookingLookupResponse,
    PublicBookingCancelResponse,
)
from app.services.booking_engine_config_service import booking_engine_config_service
from app.services.inventory_service import inventory_service
from app.services.reservation_service import reservation_service
from app.utils.enums import (
    BookingType,
    EntityStatus,
    FolioEntryType,
    FolioStatus,
    FolioTransactionSource,
    FolioTransactionType,
    FolioType,
    PaymentStatus,
    PaymentType,
    ReservationSource,
    ReservationStatus,
    TaxRateType,
)
from app.utils.exceptions import EntityNotFoundException, ValidationException


class PublicBookingService:
    async def get_or_create_config(self, db: AsyncSession, property_id: str) -> PropertyBookingEngineConfig:
        return await booking_engine_config_service.get_or_create_default(db, property_id)

    async def resolve_property(
        self,
        db: AsyncSession,
        domain: Optional[str] = None,
        slug: Optional[str] = None,
        property_id: Optional[str] = None,
    ) -> PublicResolvedPropertyResponse:
        """
        Resolves property context from custom domain, URL slug, or direct property_id.
        Includes hotel group detection (e.g. Taj Hotels) and sibling properties list.
        """
        config: Optional[PropertyBookingEngineConfig] = None

        if domain:
            clean_domain = domain.lower().strip().split(":")[0]  # strip port if local
            result = await db.execute(
                select(PropertyBookingEngineConfig).where(
                    PropertyBookingEngineConfig.custom_domain == clean_domain
                )
            )
            config = result.scalars().first()

        if not config and property_id:
            try:
                config = await self.get_or_create_config(db, property_id)
            except EntityNotFoundException:
                pass

        if not config and slug:
            clean_slug = slug.lower().strip()
            # 1. Match by slug configured in booking engine config
            result = await db.execute(
                select(PropertyBookingEngineConfig).where(
                    PropertyBookingEngineConfig.slug == clean_slug
                )
            )
            config = result.scalars().first()

            # 2. If no slug matched, check if slug is directly a property UUID or property code
            if not config:
                prop_by_id_or_code = await db.execute(
                    select(Property).where(
                        or_(
                            Property.id == slug.strip(),
                            Property.code == slug.strip().upper(),
                        )
                    )
                )
                matched_prop = prop_by_id_or_code.scalars().first()
                if matched_prop:
                    config = await self.get_or_create_config(db, matched_prop.id)

        # Fallback to the first active property in the database if nothing matched
        if not config:
            first_prop_res = await db.execute(select(Property).limit(1))
            first_prop = first_prop_res.scalars().first()
            if not first_prop:
                raise EntityNotFoundException("Property", "default")
            config = await self.get_or_create_config(db, first_prop.id)

        # Fetch loaded Property entity
        prop = await crud_property.get(db, config.property_id)
        if not prop:
            raise EntityNotFoundException("Property", config.property_id)

        # Hotel Group detection: query all active sibling properties in the same organization
        group_hotels: List[PublicGroupHotelSummary] = []
        is_group = False
        if config.allow_group_switching and prop.organization_id:
            siblings_res = await db.execute(
                select(Property)
                .where(
                    Property.organization_id == prop.organization_id,
                    Property.status == EntityStatus.ACTIVE.value,
                )
                .order_by(Property.name.asc())
            )
            siblings = siblings_res.scalars().all()
            if len(siblings) > 1:
                is_group = True
                for sib in siblings:
                    sib_config = await self.get_or_create_config(db, sib.id)
                    thumb = (
                        sib_config.hero_banner_images[0]
                        if sib_config.hero_banner_images
                        else None
                    )
                    group_hotels.append(
                        PublicGroupHotelSummary(
                            id=sib.id,
                            name=sib.name,
                            code=sib.code,
                            slug=sib_config.slug,
                            city=sib.city,
                            state=sib.state,
                            country=sib.country,
                            currency=sib.currency or "INR",
                            cover_image=thumb,
                        )
                    )

        org = await db.get(Organization, prop.organization_id) if prop.organization_id else None
        org_name = org.name if org else (config.group_display_name or prop.name)

        return PublicResolvedPropertyResponse(
            property_id=prop.id,
            property_name=prop.name,
            property_code=prop.code,
            organization_id=prop.organization_id,
            organization_name=org_name,
            slug=config.slug,
            city=prop.city,
            country=prop.country,
            currency=prop.currency or "INR",
            is_group=is_group,
            group_hotels=group_hotels,
        )

    async def get_public_config(
        self, db: AsyncSession, property_id: str
    ) -> PublicBookingEngineConfigResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        config = await self.get_or_create_config(db, property_id)
        resolved = await self.resolve_property(db, property_id=property_id)

        # Theme defaults & overrides
        preset_name = (config.theme_preset or "EMERALD_LUXURY").upper().replace("-", "_")
        preset_defaults = {
            "EMERALD_LUXURY": ("#064e3b", "#d97706", "#022c22", "#04382c"),
            "ROYAL_HERITAGE": ("#3b1d54", "#d4af37", "#1a0b26", "#2a123d"),
            "OCEAN_BREEZE": ("#0f4c81", "#00a896", "#0a2540", "#133b63"),
            "MINIMAL_DARK": ("#18181b", "#a1a1aa", "#09090b", "#18181b"),
            "SUNSET_TERRACOTTA": ("#7c2d12", "#f97316", "#431407", "#5c1d09"),
        }
        def_p, def_a, def_bg, def_s = preset_defaults.get(preset_name, ("#064e3b", "#d97706", "#022c22", "#04382c"))

        custom_c = config.custom_colors or {}
        custom_f = config.custom_fonts or {}

        theme_dict = {
            "preset": config.theme_preset or "EMERALD_LUXURY",
            "primary_color": custom_c.get("primary") or custom_c.get("primary_color") or def_p,
            "accent_color": custom_c.get("accent") or custom_c.get("accent_color") or def_a,
            "background_color": custom_c.get("background") or custom_c.get("background_color") or def_bg,
            "surface_color": custom_c.get("surface") or custom_c.get("surface_color") or def_s,
            "font_family": custom_f.get("font_family") or custom_f.get("display") or "Plus Jakarta Sans",
            "colors": custom_c,
            "fonts": custom_f,
        }

        # Brand Assets
        brand_dict = {
            "name": prop.name,
            "logo_url": config.logo_url,
            "favicon_url": config.favicon_url,
            "hero_title": config.hero_title or f"Welcome to {prop.name}",
            "hero_subtitle": config.hero_subtitle or "Experience timeless luxury, exquisite dining, and world-class hospitality.",
            "hero_banner_images": config.hero_banner_images or [],
            "concierge_phone": config.concierge_phone,
            "concierge_email": config.concierge_email,
            "location_name": f"{prop.city or ''}, {prop.country or ''}".strip(", "),
        }

        # Payment options (never disclose private gateway secrets)
        payment_dict = {
            "pay_at_hotel_enabled": config.pay_at_hotel_enabled,
            "advance_payment_enabled": config.advance_payment_enabled,
            "deposit_type": config.deposit_type,
            "deposit_percentage": float(config.deposit_percentage),
            "deposit_fixed_amount": float(config.deposit_fixed_amount),
            "gateways": {
                "razorpay": {
                    "enabled": config.razorpay_enabled and bool(config.razorpay_key_id),
                    "key_id": config.razorpay_key_id if config.razorpay_enabled else None,
                },
                "stripe": {
                    "enabled": config.stripe_enabled and bool(config.stripe_publishable_key),
                    "publishable_key": config.stripe_publishable_key if config.stripe_enabled else None,
                },
            },
        }

        policies_dict = {
            "check_in_time": "14:00",
            "check_out_time": "11:00",
            "cancellation_policy_type": config.cancellation_policy_type,
            "cancellation_deadline_hours": config.cancellation_deadline_hours,
            "cancellation_policy_text": config.cancellation_policy_text or "Free cancellation up to 48 hours before check-in.",
            "terms_and_conditions": config.terms_and_conditions or "Valid government ID is required at check-in.",
            "privacy_policy": config.privacy_policy,
            "house_rules": config.house_rules,
        }

        seo_dict = {
            "meta_title": config.meta_title or f"{prop.name} | Official Direct Booking",
            "meta_description": config.meta_description or f"Direct host booking for {prop.name}. Best rates guaranteed.",
            "og_image_url": config.og_image_url or (config.hero_banner_images[0] if config.hero_banner_images else None),
        }

        return PublicBookingEngineConfigResponse(
            property_id=prop.id,
            name=prop.name,
            code=prop.code,
            slug=config.slug,
            tagline=config.hero_subtitle,
            currency=prop.currency or "INR",
            timezone=prop.timezone or "Asia/Kolkata",
            theme=theme_dict,
            brand=brand_dict,
            property_amenities=config.property_amenities or [],
            gallery_photos=config.gallery_photos or [],
            payment_options=payment_dict,
            policies=policies_dict,
            seo=seo_dict,
            allow_group_switching=config.allow_group_switching,
            group_hotels=resolved.group_hotels,
        )

    async def search_availability(
        self,
        db: AsyncSession,
        property_id: str,
        check_in: date,
        check_out: date,
        adults: int = 1,
        children: int = 0,
        rooms_count: int = 1,
        promo_code: Optional[str] = None,
    ) -> PublicAvailabilitySearchResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        config = await self.get_or_create_config(db, property_id)

        if check_in >= check_out:
            raise ValidationException("Check-out date must be after check-in date.")

        nights = max(1, (check_out - check_in).days)
        stay_dates = [check_in + timedelta(days=i) for i in range(nights)]

        # Fetch active room types for this property
        rt_result = await db.execute(
            select(RoomType).where(
                RoomType.property_id == property_id,
                RoomType.status == EntityStatus.ACTIVE.value,
            )
        )
        room_types = rt_result.scalars().all()

        published_ids = set(config.published_rate_plan_ids or [])
        room_type_responses: List[PublicRoomTypeAvailabilityResponse] = []

        for rt in room_types:
            # 1. Compute Inventory Availability over stay_dates
            inv_rows = await inventory_service.ensure_inventory_for_range(
                db, property_id=property_id, room_type_id=rt.id, start_date=check_in, end_date=check_out - timedelta(days=1)
            )
            inv_map = {row.stay_date: row for row in inv_rows}

            min_available = 9999
            is_stop_sell = False
            is_cta = False
            for idx, d in enumerate(stay_dates):
                row = inv_map.get(d)
                if not row:
                    min_available = 0
                    break
                if row.stop_sell:
                    is_stop_sell = True
                if idx == 0 and row.closed_to_arrival:
                    is_cta = True
                avail = max(0, row.total_rooms - row.blocked_rooms - row.sold_rooms + row.overbooking_limit)
                if avail < min_available:
                    min_available = avail

            if min_available == 9999:
                min_available = 0

            # If the property has room types but total physical rooms = 0 (demo/test property without physical rooms configured),
            # allow default 5 units so booking engine is functional for testing
            if min_available == 0 and not is_stop_sell and not is_cta:
                has_physical = await inventory_service.get_active_room_count(db, property_id, rt.id)
                if has_physical == 0:
                    min_available = 5

            sold_out = is_stop_sell or is_cta or (min_available < rooms_count)

            # 2. Query Rate Plans for this room type
            rp_result = await db.execute(
                select(RatePlan)
                .where(
                    RatePlan.room_type_id == rt.id,
                    RatePlan.status == EntityStatus.ACTIVE.value,
                    RatePlan.booking_type == BookingType.NIGHTLY.value,
                )
                .options(selectinload(RatePlan.rates))
            )
            rate_plans = rp_result.scalars().all()

            # Filter by published rate plans if specified in config
            if published_ids:
                rate_plans = [rp for rp in rate_plans if rp.id in published_ids or rp.is_public_booking_engine]
            else:
                rate_plans = [rp for rp in rate_plans if rp.is_public_booking_engine is not False]

            rate_plan_summaries: List[PublicRatePlanSummary] = []
            for rp in rate_plans:
                if not rp.rates:
                    # Provide default price fallback if rate plan child rates haven't been added yet
                    price_per_night = Decimal("2500.00")
                    original_price = Decimal("2950.00")
                else:
                    # Calculate average price per night based on occupancy
                    total_adults = max(1, adults)
                    total_children = max(0, children)
                    exact_match = next((r for r in rp.rates if r.occupancy == total_adults), None)
                    range_match = next((r for r in rp.rates if (r.min_occupancy or 1) <= total_adults <= (r.max_occupancy or 99)), None) if not exact_match else None
                    base_match = next((r for r in rp.rates if r.occupancy == rt.base_occupancy), rp.rates[0])

                    matched_rate = exact_match or range_match or base_match
                    tier_occ = matched_rate.occupancy or matched_rate.max_occupancy or rt.base_occupancy
                    extra_adults = max(0, total_adults - tier_occ)

                    extra_adult_fee = matched_rate.extra_adult_price if matched_rate.extra_adult_price is not None else rp.extra_adult_rate
                    extra_child_fee = matched_rate.extra_child_price if matched_rate.extra_child_price is not None else rp.extra_child_rate
                    extra_person_total = (Decimal(str(extra_adults)) * extra_adult_fee) + (Decimal(str(total_children)) * extra_child_fee)

                    price_per_night = matched_rate.price + extra_person_total
                    original_price = (price_per_night * Decimal("1.18")).quantize(Decimal("1.00"))

                custom_badge = config.rate_plan_badges.get(rp.id) or rp.public_badge
                perks = rp.included_perks or [
                    "High-speed fiber optic Wi-Fi",
                    "Complimentary arrival welcome refreshments",
                    "Daily evening turndown service",
                ]

                deposit_txt = "No advance deposit required · Pay at hotel"
                if config.advance_payment_enabled:
                    if config.deposit_type == "PERCENTAGE":
                        deposit_txt = f"{config.deposit_percentage}% deposit required at booking"
                    elif config.deposit_type == "FIRST_NIGHT":
                        deposit_txt = "1st night deposit required"
                    else:
                        deposit_txt = "Full advance payment required"

                rate_plan_summaries.append(
                    PublicRatePlanSummary(
                        id=rp.id,
                        name=rp.name,
                        tag=custom_badge,
                        description=rp.description or f"Direct host rate for {rp.name}.",
                        meal_plan=rp.meal_plan,
                        cancellation_policy=config.cancellation_policy_type.lower(),
                        cancellation_text=config.cancellation_policy_text or "Free cancellation up to 48 hours prior to check-in",
                        deposit_text=deposit_txt,
                        price_per_night=price_per_night,
                        original_price_per_night=original_price,
                        included_perks=perks,
                    )
                )

            # Amenities & Photos fallbacks
            images = rt.photos if rt.photos else [
                "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=1200&q=80",
                "https://images.unsplash.com/photo-1591088398332-8a7791972843?auto=format&fit=crop&w=1200&q=80",
            ]
            amenities = rt.amenities if rt.amenities else [
                {"id": "balcony", "name": "Private Balcony", "icon": "Sun"},
                {"id": "tub", "name": "Deep Soaking Tub", "icon": "Bath"},
                {"id": "wifi", "name": "Fiber Wi-Fi", "icon": "Wifi"},
                {"id": "coffee", "name": "Nespresso Bar", "icon": "Coffee"},
            ]

            scarcity = None
            if min_available in [1, 2, 3]:
                scarcity = f"⚡ Only {min_available} Suite{'s' if min_available > 1 else ''} Left!"

            room_type_responses.append(
                PublicRoomTypeAvailabilityResponse(
                    id=rt.id,
                    level="PREMIER COLLECTION",
                    title=rt.name,
                    subtitle=rt.subtitle or rt.description,
                    description=rt.description or f"Spacious {rt.name} featuring premium furnishings and bespoke guest amenities.",
                    badge=rt.badge,
                    scarcity_notice=scarcity,
                    sold_out=sold_out,
                    max_adults=rt.max_occupancy,
                    max_children=max(0, rt.max_occupancy - 1),
                    size_sq_ft=rt.size_sq_ft or 540,
                    size_sqm=rt.size_sqm or 50,
                    bed_config=rt.bed_config or "1 King Bed",
                    view=rt.view_type or "Panoramic View",
                    images=images,
                    amenities=amenities,
                    available_units=min_available,
                    rate_plans=rate_plan_summaries,
                )
            )

        return PublicAvailabilitySearchResponse(
            property_id=prop.id,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            adults=adults,
            children=children,
            rooms_count=rooms_count,
            currency=prop.currency or "INR",
            room_types=room_type_responses,
        )

    async def get_rate_calendar(
        self, db: AsyncSession, property_id: str, start_date: date, days: int = 30
    ) -> List[PublicRateCalendarDay]:
        """Returns lowest available daily rates across the property for a 30-day window."""
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        # Query all active rate plan rates
        result = await db.execute(
            select(func.min(RatePlanRate.price))
            .join(RatePlan, RatePlan.id == RatePlanRate.rate_plan_id)
            .where(
                RatePlan.property_id == property_id,
                RatePlan.status == EntityStatus.ACTIVE.value,
            )
        )
        base_min = result.scalar() or Decimal("3500.00")

        calendar_days: List[PublicRateCalendarDay] = []
        for i in range(days):
            cur_date = start_date + timedelta(days=i)
            # Weekend bump simulation
            is_weekend = cur_date.weekday() in [4, 5]
            mult = Decimal("1.20") if is_weekend else Decimal("1.00")
            day_price = (base_min * mult).quantize(Decimal("1.00"))

            calendar_days.append(
                PublicRateCalendarDay(
                    date_str=cur_date.strftime("%Y-%m-%d"),
                    price=day_price,
                    is_available=True,
                    available_units=5,
                )
            )

        return calendar_days

    async def calculate_quote(
        self, db: AsyncSession, property_id: str, quote_in: PublicQuoteRequest
    ) -> PublicQuoteResponse:
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        config = await self.get_or_create_config(db, property_id)

        nights = max(1, (quote_in.check_out - quote_in.check_in).days)
        stay_dates = [quote_in.check_in + timedelta(days=i) for i in range(nights)]

        room_base_total = Decimal("0.00")
        total_taxes = Decimal("0.00")

        for item in quote_in.rooms:
            rt = await db.get(RoomType, item.room_type_id)
            rp = await db.get(RatePlan, item.rate_plan_id)
            if not rt or not rp:
                continue

            # Query candidate rates for each night
            for d in stay_dates:
                rate_q = await db.execute(
                    select(RatePlanRate).where(
                        RatePlanRate.rate_plan_id == rp.id,
                        or_(RatePlanRate.valid_from.is_(None), RatePlanRate.valid_from <= d),
                        or_(RatePlanRate.valid_to.is_(None), RatePlanRate.valid_to >= d),
                    ).order_by(RatePlanRate.created_at.desc())
                )
                rates = rate_q.scalars().all()
                if not rates:
                    rates_fallback = await db.execute(
                        select(RatePlanRate).where(RatePlanRate.rate_plan_id == rp.id)
                    )
                    rates = rates_fallback.scalars().all()

                if not rates:
                    raise ValidationException(f"No rates configured for rate plan '{rp.name}' on {d}.")

                total_adults = max(1, quote_in.adults)
                total_children = max(0, quote_in.children)
                exact_match = next((r for r in rates if r.occupancy == total_adults), None)
                range_match = next((r for r in rates if (r.min_occupancy or 1) <= total_adults <= (r.max_occupancy or 99)), None) if not exact_match else None
                base_match = next((r for r in rates if r.occupancy == rt.base_occupancy), rates[0])

                matched_rate = exact_match or range_match or base_match
                tier_occ = matched_rate.occupancy or matched_rate.max_occupancy or rt.base_occupancy
                extra_adults = max(0, total_adults - tier_occ)

                extra_adult_fee = matched_rate.extra_adult_price if matched_rate.extra_adult_price is not None else rp.extra_adult_rate
                extra_child_fee = matched_rate.extra_child_price if matched_rate.extra_child_price is not None else rp.extra_child_rate
                extra_person = (Decimal(str(extra_adults)) * extra_adult_fee) + (Decimal(str(total_children)) * extra_child_fee)

                night_net = (matched_rate.price + extra_person) * Decimal(str(item.quantity))
                night_tax = (await reservation_service._calculate_taxes_for_rate(
                    db, tax_group_id=rp.tax_group_id, base_amount=night_net, stay_date=d
                ))

                room_base_total += night_net
                total_taxes += night_tax

        # Add-ons calculation
        addons_total = Decimal("0.00")
        for addon_item in quote_in.addons:
            service = await db.get(Service, addon_item.addon_id)
            if service and service.default_price:
                addons_total += service.default_price * Decimal(str(addon_item.quantity))

        # Direct Host Advantage: -$50 or 500 INR direct booking advantage
        direct_discount = Decimal("500.00") if prop.currency == "INR" else Decimal("50.00")
        if room_base_total == Decimal("0.00"):
            direct_discount = Decimal("0.00")

        # Promo code discount
        promo_discount = Decimal("0.00")
        if quote_in.promo_code:
            code = quote_in.promo_code.strip().upper()
            if code in ["AZURE10", "CLOUDKEY10"]:
                promo_discount = (room_base_total * Decimal("0.10")).quantize(Decimal("1.00"))
            elif code == "VIP20":
                promo_discount = (room_base_total * Decimal("0.20")).quantize(Decimal("1.00"))

        subtotal = room_base_total + addons_total
        grand_total = max(Decimal("0.00"), subtotal + total_taxes - direct_discount - promo_discount)

        # Deposit rules
        deposit_due = Decimal("0.00")
        deposit_required = config.advance_payment_enabled
        if deposit_required:
            if config.deposit_type == "PERCENTAGE":
                deposit_due = (grand_total * (config.deposit_percentage / Decimal("100"))).quantize(Decimal("1.00"))
            elif config.deposit_type == "FIRST_NIGHT" and nights > 0:
                deposit_due = (grand_total / Decimal(str(nights))).quantize(Decimal("1.00"))
            else:
                deposit_due = grand_total

        balance_due = grand_total - deposit_due

        return PublicQuoteResponse(
            nights=nights,
            room_base_total=room_base_total,
            addons_total=addons_total,
            subtotal=subtotal,
            tax_amount=total_taxes,
            service_fee=Decimal("0.00"),
            direct_booking_discount=direct_discount,
            promo_discount=promo_discount,
            grand_total=grand_total,
            currency=prop.currency or "INR",
            deposit_required=deposit_required,
            deposit_amount_due=deposit_due,
            balance_due_at_hotel=balance_due,
        )

    async def create_public_booking(
        self,
        db: AsyncSession,
        property_id: str,
        booking_in: PublicBookingCreateRequest,
        client_ip: Optional[str] = None,
    ) -> PublicBookingConfirmationResponse:
        """
        Executes real public reservation creation directly inside CloudKey PMS:
        - Locks and verifies inventory in `room_type_inventory`
        - Creates Guest record
        - Generates collision-free hotel-code-prefixed booking number
        - Creates Reservation with status CONFIRMED and source WEBSITE
        - Creates ReservationRoom and ReservationRoomRates
        - Creates Folio
        - If paid online: logs Payment and FolioTransaction
        """
        prop = await crud_property.get(db, property_id)
        if not prop:
            raise EntityNotFoundException("Property", property_id)

        config = await self.get_or_create_config(db, property_id)

        # 1. Hot-Path Inventory Allocation & Lock
        room_demands: Dict[str, List[date]] = {}
        nights = max(1, (booking_in.check_out - booking_in.check_in).days)
        stay_dates = [booking_in.check_in + timedelta(days=i) for i in range(nights)]

        for room_in in booking_in.rooms:
            rt_id = room_in.room_type_id
            if rt_id not in room_demands:
                room_demands[rt_id] = []
            for _ in range(room_in.quantity):
                room_demands[rt_id].extend(stay_dates)

        await inventory_service.lock_and_reserve(
            db, property_id=property_id, room_demands=room_demands
        )

        # 2. Find or Create Booker in `guests` table
        from app.schemas.reservation import BookerInfoInput
        guest_payload = BookerInfoInput(
            first_name=booking_in.booker.first_name,
            last_name=booking_in.booker.last_name,
            email=booking_in.booker.email,
            phone=booking_in.booker.phone,
        )
        booker = await crud_guest.find_or_create(
            db, organization_id=prop.organization_id, guest_data=guest_payload
        )

        # 3. Generate Unique Booking Number
        booking_number = await reservation_service.generate_booking_number(db, property_code=prop.code)

        check_in_dt = datetime.combine(booking_in.check_in, datetime.strptime("14:00", "%H:%M").time(), tzinfo=timezone.utc)
        check_out_dt = datetime.combine(booking_in.check_out, datetime.strptime("11:00", "%H:%M").time(), tzinfo=timezone.utc)

        # 4. Calculate Authoritative Quote & Financials
        from app.schemas.property_booking_engine_config import PublicQuoteItemInput, PublicAddonItemInput
        quote_req = PublicQuoteRequest(
            check_in=booking_in.check_in,
            check_out=booking_in.check_out,
            adults=booking_in.adults,
            children=booking_in.children,
            rooms=[PublicQuoteItemInput(room_type_id=r.room_type_id, rate_plan_id=r.rate_plan_id, quantity=r.quantity) for r in booking_in.rooms],
            addons=[PublicAddonItemInput(addon_id=a.addon_id, quantity=a.quantity) for a in booking_in.addons],
            promo_code=booking_in.promo_code,
        )
        quote = await self.calculate_quote(db, property_id=property_id, quote_in=quote_req)

        # 5. Insert Reservation
        reservation = Reservation(
            property_id=property_id,
            booking_number=booking_number,
            guest_id=booker.id,
            booking_type=BookingType.NIGHTLY.value,
            source=ReservationSource.WEBSITE.value,
            channel_name="CloudKey Direct Booking Engine",
            status=ReservationStatus.CONFIRMED.value,
            check_in_at=check_in_dt,
            check_out_at=check_out_dt,
            currency=prop.currency or "INR",
            total_amount=quote.grand_total,
            total_tax_amount=quote.tax_amount,
            special_requests=booking_in.booker.special_requests,
        )
        db.add(reservation)
        await db.flush()

        # 6. Insert Reservation Rooms & Rate Snapshots
        for room_in in booking_in.rooms:
            for _ in range(room_in.quantity):
                res_room = ReservationRoom(
                    reservation_id=reservation.id,
                    room_type_id=room_in.room_type_id,
                    room_id=None,  # Front desk assigns physical room at check-in
                    rate_plan_id=room_in.rate_plan_id,
                    status=ReservationStatus.CONFIRMED.value,
                    check_in_at=check_in_dt,
                    check_out_at=check_out_dt,
                    adults=booking_in.adults,
                    children=booking_in.children,
                )
                db.add(res_room)
                await db.flush()

                # Add Primary Guest occupant
                res_guest = ReservationGuest(
                    reservation_room_id=res_room.id,
                    guest_id=booker.id,
                    is_primary=True,
                )
                db.add(res_guest)

                # Snapshot nightly room rates
                rt = await db.get(RoomType, room_in.room_type_id)
                rp = await db.get(RatePlan, room_in.rate_plan_id)
                rates_q = await db.execute(
                    select(RatePlanRate).where(RatePlanRate.rate_plan_id == room_in.rate_plan_id)
                )
                candidate_rates = rates_q.scalars().all()
                matched_rate = candidate_rates[0] if candidate_rates else None

                for d in stay_dates:
                    base_price = matched_rate.price if matched_rate else Decimal("3500.00")
                    tax_val = await reservation_service._calculate_taxes_for_rate(
                        db, tax_group_id=rp.tax_group_id if rp else None, base_amount=base_price, stay_date=d
                    )
                    res_rate = ReservationRoomRate(
                        reservation_room_id=res_room.id,
                        stay_date=d,
                        rate_plan_rate_id=matched_rate.id if matched_rate else None,
                        occupancy=booking_in.adults,
                        base_amount=base_price,
                        extra_person_amount=Decimal("0.00"),
                        discount_amount=Decimal("0.00"),
                        net_amount=base_price,
                        tax_amount=tax_val,
                        total_amount=base_price + tax_val,
                    )
                    db.add(res_rate)

        # 7. Create Guest Master Folio
        folio_number = reservation_service.generate_folio_number(property_code=prop.code)
        folio = Folio(
            property_id=property_id,
            reservation_id=reservation.id,
            guest_id=booker.id,
            folio_number=folio_number,
            folio_type=FolioType.GUEST.value,
            status=FolioStatus.OPEN.value,
            currency=reservation.currency,
            opened_at=datetime.now(timezone.utc),
        )
        db.add(folio)
        await db.flush()

        # 8. Record Payment if paid online
        pay_method_str = booking_in.payment.method.upper()
        payment_status_str = "PENDING"
        if pay_method_str in ["CARD", "UPI", "RAZORPAY", "STRIPE"] and booking_in.payment.gateway_reference:
            payment_status_str = "CAPTURED"
            # Get or create credit card / gateway payment method
            pm_res = await db.execute(
                select(PaymentMethod).where(
                    PaymentMethod.property_id == property_id,
                    PaymentMethod.status == EntityStatus.ACTIVE.value,
                ).limit(1)
            )
            pm = pm_res.scalars().first()
            if not pm:
                pm = PaymentMethod(
                    property_id=property_id,
                    name=f"Online Gateway ({pay_method_str})",
                    code=pay_method_str[:10],
                    method_type="CARD",
                    status="ACTIVE",
                )
                db.add(pm)
                await db.flush()

            amount_paid = quote.deposit_amount_due if quote.deposit_required else quote.grand_total
            payment_rec = Payment(
                property_id=property_id,
                folio_id=folio.id,
                reservation_id=reservation.id,
                payment_method_id=pm.id,
                payment_type=PaymentType.ADVANCE.value,
                status=PaymentStatus.CAPTURED.value,
                amount=amount_paid,
                currency=reservation.currency,
                gateway=pay_method_str,
                gateway_reference=booking_in.payment.gateway_reference,
                received_at=datetime.now(timezone.utc),
            )
            db.add(payment_rec)
            await db.flush()

            # Post double-entry CREDIT in folio_transactions
            bdate = prop.business_date or datetime.now(timezone.utc).date()
            folio_txn = FolioTransaction(
                property_id=property_id,
                folio_id=folio.id,
                business_date=bdate,
                entry_type=FolioEntryType.CREDIT.value,
                transaction_type=FolioTransactionType.PAYMENT.value,
                payment_id=payment_rec.id,
                description=f"Online payment via {pay_method_str} (Ref: {booking_in.payment.gateway_reference})",
                quantity=Decimal("1.00"),
                unit_price=amount_paid,
                amount=amount_paid,
                tax_amount=Decimal("0.00"),
                total_amount=amount_paid,
                source=FolioTransactionSource.SYSTEM.value,
                posted_at=datetime.now(timezone.utc),
            )
            db.add(folio_txn)
            await db.flush()

        # 9. Audit Log
        audit = AuditLog(
            organization_id=prop.organization_id,
            property_id=property_id,
            entity_type="reservations",
            entity_id=reservation.id,
            action="CREATE_PUBLIC",
            new_values={
                "booking_number": booking_number,
                "booker_email": booker.email,
                "source": "WEBSITE",
                "payment_method": pay_method_str,
                "grand_total": str(quote.grand_total),
                "client_ip": client_ip,
            },
        )
        db.add(audit)

        await db.commit()

        return PublicBookingConfirmationResponse(
            booking_number=booking_number,
            property_name=prop.name,
            property_code=prop.code,
            status=reservation.status,
            check_in_at=reservation.check_in_at,
            check_out_at=reservation.check_out_at,
            nights=nights,
            booker_name=f"{booker.first_name} {booker.last_name or ''}".strip(),
            booker_email=booker.email or "",
            total_amount=quote.grand_total,
            currency=reservation.currency,
            payment_status=payment_status_str,
            payment_method=pay_method_str,
            created_at=reservation.created_at,
            message="Your reservation has been confirmed and inventory is guaranteed.",
        )

    async def lookup_booking(
        self, db: AsyncSession, booking_number: str, email: str
    ) -> PublicBookingLookupResponse:
        clean_no = booking_number.strip().upper()
        clean_email = email.strip().lower()

        result = await db.execute(
            select(Reservation)
            .join(Reservation.guest)
            .where(
                Reservation.booking_number == clean_no,
                func.lower(Guest.email) == clean_email,
            )
            .options(
                selectinload(Reservation.property),
                selectinload(Reservation.guest),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.room_type),
                selectinload(Reservation.rooms).selectinload(ReservationRoom.rate_plan),
            )
        )
        res = result.scalar_one_or_none()
        if not res:
            raise EntityNotFoundException("Reservation", f"{clean_no} for {clean_email}")

        prop_config = await self.get_or_create_config(db, res.property_id)

        # Check cancellation eligibility
        now = datetime.now(timezone.utc)
        check_in_dt = res.check_in_at
        if check_in_dt.tzinfo is None:
            check_in_dt = check_in_dt.replace(tzinfo=timezone.utc)
        deadline = check_in_dt - timedelta(hours=prop_config.cancellation_deadline_hours)
        can_cancel = (res.status == ReservationStatus.CONFIRMED.value) and (now <= deadline)

        rooms_summary = []
        for r in res.rooms:
            rooms_summary.append({
                "room_type_name": r.room_type.name if r.room_type else "Suite",
                "rate_plan_name": r.rate_plan.name if r.rate_plan else "Standard Rate",
                "adults": r.adults,
                "children": r.children,
            })

        nights = max(1, (res.check_out_at.date() - res.check_in_at.date()).days)

        return PublicBookingLookupResponse(
            booking_number=res.booking_number,
            property_id=res.property_id,
            property_name=res.property.name,
            property_slug=prop_config.slug,
            status=res.status,
            check_in_at=res.check_in_at,
            check_out_at=res.check_out_at,
            nights=nights,
            booker_name=f"{res.guest.first_name} {res.guest.last_name or ''}".strip(),
            booker_email=res.guest.email or "",
            booker_phone=res.guest.phone,
            special_requests=res.special_requests,
            total_amount=res.total_amount or Decimal("0.00"),
            currency=res.currency,
            payment_status="CONFIRMED",
            can_cancel=can_cancel,
            cancellation_deadline=deadline,
            cancellation_policy_text=prop_config.cancellation_policy_text,
            rooms=rooms_summary,
        )

    async def cancel_public_booking(
        self, db: AsyncSession, booking_number: str, email: str, reason: Optional[str] = None
    ) -> PublicBookingCancelResponse:
        lookup = await self.lookup_booking(db, booking_number=booking_number, email=email)
        if not lookup.can_cancel:
            raise ValidationException(
                f"Booking '{booking_number}' cannot be cancelled online. The cancellation deadline ({lookup.cancellation_deadline}) has passed or the booking is not in CONFIRMED status."
            )

        res_record = await crud_reservation.get_by_booking_number(
            db, property_id="", booking_number=booking_number
        )
        if not res_record:
            res_any = await db.execute(select(Reservation).where(Reservation.booking_number == booking_number))
            res_record = res_any.scalar_one_or_none()

        cancelled_res = await reservation_service.cancel_reservation(
            db,
            property_id=res_record.property_id,
            reservation_id=res_record.id,
            reason=reason or "Guest online cancellation",
        )

        return PublicBookingCancelResponse(
            booking_number=booking_number,
            status=cancelled_res.status,
            cancelled_at=datetime.now(timezone.utc),
            refund_amount=res_record.total_amount or Decimal("0.00"),
            currency=res_record.currency,
            message="Your reservation has been cancelled and inventory has been released.",
        )


public_booking_service = PublicBookingService()
