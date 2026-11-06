from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─── ADMIN SETTINGS SCHEMAS ───────────────────────────────────────────────────

class PropertyBookingEngineConfigBase(BaseModel):
    slug: str = Field(..., min_length=2, examples=["carmel-azure", "taj-bangalore"])
    custom_domain: Optional[str] = Field(None, examples=["reservations.tajbangalore.com"])
    is_active: bool = True
    allow_group_switching: bool = True
    group_display_name: Optional[str] = None

    theme_preset: str = Field(default="EMERALD_LUXURY")
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    surface_color: Optional[str] = None
    font_family: Optional[str] = None
    custom_colors: Optional[Dict[str, Any]] = None
    custom_fonts: Optional[Dict[str, Any]] = None

    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    hero_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    hero_banner_images: List[str] = Field(default_factory=list)
    concierge_phone: Optional[str] = None
    concierge_email: Optional[str] = None
    property_amenities: List[Dict[str, Any]] = Field(default_factory=list)
    gallery_photos: List[str] = Field(default_factory=list)

    published_rate_plan_ids: List[str] = Field(default_factory=list)
    rate_plan_badges: Dict[str, str] = Field(default_factory=dict)

    pay_at_hotel_enabled: bool = True
    advance_payment_enabled: bool = False
    deposit_type: str = "FULL"  # FULL, PERCENTAGE, FIRST_NIGHT, FIXED
    deposit_percentage: Decimal = Field(default=Decimal("20.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    deposit_fixed_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))

    razorpay_enabled: bool = False
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None

    stripe_enabled: bool = False
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None

    cancellation_policy_type: str = "FREE"  # FREE, FLEXIBLE, NON_REFUNDABLE, CUSTOM
    cancellation_deadline_hours: int = Field(default=48, ge=0)
    cancellation_policy_text: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    privacy_policy: Optional[str] = None
    house_rules: Optional[str] = None

    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image_url: Optional[str] = None


class PropertyBookingEngineConfigCreate(PropertyBookingEngineConfigBase):
    property_id: Optional[str] = None


class PropertyBookingEngineConfigUpdate(BaseModel):
    slug: Optional[str] = None
    custom_domain: Optional[str] = None
    is_active: Optional[bool] = None
    is_enabled: Optional[bool] = None
    allow_group_switching: Optional[bool] = None
    group_display_name: Optional[str] = None

    theme_preset: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    surface_color: Optional[str] = None
    font_family: Optional[str] = None
    custom_colors: Optional[Dict[str, Any]] = None
    custom_fonts: Optional[Dict[str, Any]] = None

    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    hero_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    hero_banner_images: Optional[List[str]] = None
    concierge_phone: Optional[str] = None
    concierge_email: Optional[str] = None
    property_amenities: Optional[List[Dict[str, Any]]] = None
    gallery_photos: Optional[List[str]] = None

    published_rate_plan_ids: Optional[List[str]] = None
    rate_plan_badges: Optional[Dict[str, str]] = None

    pay_at_hotel_enabled: Optional[bool] = None
    advance_payment_enabled: Optional[bool] = None
    deposit_type: Optional[str] = None
    deposit_percentage: Optional[Decimal] = None
    deposit_fixed_amount: Optional[Decimal] = None

    razorpay_enabled: Optional[bool] = None
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None

    stripe_enabled: Optional[bool] = None
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None

    cancellation_policy_type: Optional[str] = None
    cancellation_deadline_hours: Optional[int] = None
    cancellation_policy_text: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    privacy_policy: Optional[str] = None
    house_rules: Optional[str] = None

    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image_url: Optional[str] = None


class PropertyBookingEngineConfigResponse(PropertyBookingEngineConfigBase):
    id: str
    property_id: str
    domain_status: str
    domain_verification_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Masked credentials for safe UI rendering
    razorpay_key_secret_masked: Optional[str] = None
    stripe_secret_key_masked: Optional[str] = None

    is_enabled: Optional[bool] = None
    public_engine_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DomainVerifyResponse(BaseModel):
    custom_domain: str
    domain_status: str
    is_verified: bool
    cname_target: str
    current_dns_value: Optional[str] = None
    message: str


class GatewayTestRequest(BaseModel):
    gateway: str = Field(..., examples=["RAZORPAY", "STRIPE"])
    key_id: Optional[str] = None
    key_secret: Optional[str] = None


class GatewayTestResponse(BaseModel):
    gateway: str
    success: bool
    message: str


# ─── PUBLIC GUEST API SCHEMAS ─────────────────────────────────────────────────

class PublicGroupHotelSummary(BaseModel):
    id: str
    name: str
    code: str
    slug: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    currency: str = "INR"
    starting_price: Optional[Decimal] = None
    cover_image: Optional[str] = None


class PublicResolvedPropertyResponse(BaseModel):
    property_id: str
    property_name: str
    property_code: str
    organization_id: str
    organization_name: str
    slug: str
    city: Optional[str] = None
    country: Optional[str] = None
    currency: str = "INR"
    is_group: bool = False
    group_hotels: List[PublicGroupHotelSummary] = Field(default_factory=list)


class PublicBookingEngineConfigResponse(BaseModel):
    property_id: str
    name: str
    code: str
    slug: str
    tagline: Optional[str] = None
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    theme: Dict[str, Any]
    brand: Dict[str, Any]
    property_amenities: List[Dict[str, Any]]
    gallery_photos: List[str]
    payment_options: Dict[str, Any]
    policies: Dict[str, Any]
    seo: Dict[str, Any]
    allow_group_switching: bool
    group_hotels: List[PublicGroupHotelSummary] = Field(default_factory=list)


class PublicRatePlanSummary(BaseModel):
    id: str
    name: str
    tag: Optional[str] = None
    description: Optional[str] = None
    meal_plan: str
    cancellation_policy: str
    cancellation_text: str
    deposit_text: Optional[str] = None
    price_per_night: Decimal
    original_price_per_night: Optional[Decimal] = None
    included_perks: List[str] = Field(default_factory=list)


class PublicRoomTypeAvailabilityResponse(BaseModel):
    id: str
    level: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    badge: Optional[str] = None
    scarcity_notice: Optional[str] = None
    sold_out: bool = False
    max_adults: int
    max_children: int
    size_sq_ft: Optional[int] = None
    size_sqm: Optional[int] = None
    bed_config: Optional[str] = None
    view: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    amenities: List[Dict[str, Any]] = Field(default_factory=list)
    available_units: int
    rate_plans: List[PublicRatePlanSummary] = Field(default_factory=list)


class PublicAvailabilitySearchResponse(BaseModel):
    property_id: str
    check_in: date
    check_out: date
    nights: int
    adults: int
    children: int
    rooms_count: int
    currency: str
    room_types: List[PublicRoomTypeAvailabilityResponse]


class PublicRateCalendarDay(BaseModel):
    date_str: str
    price: Decimal
    is_available: bool
    available_units: int


class PublicQuoteItemInput(BaseModel):
    room_type_id: str
    rate_plan_id: str
    quantity: int = Field(default=1, ge=1)


class PublicAddonItemInput(BaseModel):
    addon_id: str
    quantity: int = Field(default=1, ge=1)


class PublicQuoteRequest(BaseModel):
    check_in: date
    check_out: date
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    rooms: List[PublicQuoteItemInput]
    addons: List[PublicAddonItemInput] = Field(default_factory=list)
    promo_code: Optional[str] = None


class PublicQuoteResponse(BaseModel):
    nights: int
    room_base_total: Decimal
    addons_total: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    service_fee: Decimal
    direct_booking_discount: Decimal
    promo_discount: Decimal
    grand_total: Decimal
    currency: str
    deposit_required: bool
    deposit_amount_due: Decimal
    balance_due_at_hotel: Decimal


class PublicRoomGuestInput(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    room_index: int = 1


class PublicSelectedRoomBookingInput(BaseModel):
    room_type_id: str
    rate_plan_id: str
    quantity: int = 1
    guests: List[PublicRoomGuestInput] = Field(default_factory=list)


class PublicBookerInput(BaseModel):
    title: Optional[str] = "Mr"
    first_name: str = Field(..., min_length=1)
    last_name: Optional[str] = None
    email: EmailStr
    phone: str = Field(..., min_length=5)
    special_requests: Optional[str] = None
    estimated_arrival_time: Optional[str] = "15:00"


class PublicPaymentInput(BaseModel):
    method: str = Field(..., examples=["PAY_AT_HOTEL", "CARD", "UPI", "RAZORPAY", "STRIPE"])
    gateway_reference: Optional[str] = None
    signature: Optional[str] = None
    notes: Optional[str] = None


class PublicBookingCreateRequest(BaseModel):
    check_in: date
    check_out: date
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    promo_code: Optional[str] = None
    booker: PublicBookerInput
    rooms: List[PublicSelectedRoomBookingInput] = Field(..., min_length=1)
    addons: List[PublicAddonItemInput] = Field(default_factory=list)
    payment: PublicPaymentInput


class PublicBookingConfirmationResponse(BaseModel):
    booking_number: str
    property_name: str
    property_code: str
    status: str
    check_in_at: datetime
    check_out_at: datetime
    nights: int
    booker_name: str
    booker_email: str
    total_amount: Decimal
    currency: str
    payment_status: str
    payment_method: str
    created_at: datetime
    message: str


class PublicBookingLookupResponse(BaseModel):
    booking_number: str
    property_id: str
    property_name: str
    property_slug: str
    status: str
    check_in_at: datetime
    check_out_at: datetime
    nights: int
    booker_name: str
    booker_email: str
    booker_phone: Optional[str] = None
    special_requests: Optional[str] = None
    total_amount: Decimal
    currency: str
    payment_status: str
    can_cancel: bool
    cancellation_deadline: Optional[datetime] = None
    cancellation_policy_text: Optional[str] = None
    rooms: List[Dict[str, Any]] = Field(default_factory=list)


class PublicBookingCancelRequest(BaseModel):
    booking_number: str
    email: EmailStr
    reason: Optional[str] = None


class PublicBookingCancelResponse(BaseModel):
    booking_number: str
    status: str
    cancelled_at: datetime
    refund_amount: Decimal
    currency: str
    message: str

