from enum import Enum


class OrganizationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class EntityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class RoomStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"


class BookingType(str, Enum):
    NIGHTLY = "NIGHTLY"
    HOURLY = "HOURLY"


class DurationUnit(str, Enum):
    HOUR = "HOUR"
    NIGHT = "NIGHT"


class RoleScope(str, Enum):
    ORGANIZATION = "ORGANIZATION"
    PROPERTY = "PROPERTY"


class UserMembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"

class PropertyClassificationType(str, Enum):
    HOTEL = "HOTEL"
    RESORT = "RESORT"
    HOSTEL = "HOSTEL"
    BNB = "BNB"
    HOMESTAY = "HOMESTAY"
    BOUTIQUE = "BOUTIQUE"
    VILLA = "VILLA"
    APARTMENT = "APARTMENT"
    MOTEL = "MOTEL"
    OTHER = "OTHER"


# ─── PMS Extended Enums ────────────────────────────────────────────────────────

class GuestIdType(str, Enum):
    AADHAAR = "AADHAAR"
    PASSPORT = "PASSPORT"
    DRIVING_LICENSE = "DRIVING_LICENSE"
    VOTER_ID = "VOTER_ID"
    OTHER = "OTHER"


class CompanyType(str, Enum):
    CORPORATE = "CORPORATE"
    TRAVEL_AGENT = "TRAVEL_AGENT"
    OTA = "OTA"


class TaxRateType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FLAT = "FLAT"


class TaxAppliesTo(str, Enum):
    ROOM = "ROOM"
    SERVICE = "SERVICE"


class ServiceCategory(str, Enum):
    FOOD = "FOOD"
    BEVERAGE = "BEVERAGE"
    LAUNDRY = "LAUNDRY"
    SPA = "SPA"
    TRANSPORT = "TRANSPORT"
    MINIBAR = "MINIBAR"
    EXTRA_BED = "EXTRA_BED"
    FEE = "FEE"
    OTHER = "OTHER"


class PricingType(str, Enum):
    FIXED = "FIXED"
    OPEN = "OPEN"


class OccupancyStatus(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"


class HousekeepingStatus(str, Enum):
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    INSPECTED = "INSPECTED"


class ReservationStatus(str, Enum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class ReservationSource(str, Enum):
    DIRECT = "DIRECT"
    WALK_IN = "WALK_IN"
    PHONE = "PHONE"
    WEBSITE = "WEBSITE"
    OTA = "OTA"
    CHANNEL_MANAGER = "CHANNEL_MANAGER"


class RoomBlockType(str, Enum):
    OUT_OF_ORDER = "OUT_OF_ORDER"
    MAINTENANCE = "MAINTENANCE"
    HOLD = "HOLD"


class PaymentMethodType(str, Enum):
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CITY_LEDGER = "CITY_LEDGER"
    OTA_PREPAID = "OTA_PREPAID"


class PaymentType(str, Enum):
    ADVANCE = "ADVANCE"
    SETTLEMENT = "SETTLEMENT"
    REFUND = "REFUND"
    AUTHORIZATION = "AUTHORIZATION"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class FolioType(str, Enum):
    GUEST = "GUEST"
    MASTER = "MASTER"
    CITY_LEDGER = "CITY_LEDGER"
    HOUSE = "HOUSE"


class FolioStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    VOID = "VOID"


class FolioEntryType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class FolioTransactionType(str, Enum):
    ROOM_CHARGE = "ROOM_CHARGE"
    SERVICE_CHARGE = "SERVICE_CHARGE"
    FEE = "FEE"
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    DISCOUNT = "DISCOUNT"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER = "TRANSFER"


class FolioTransactionSource(str, Enum):
    NIGHT_AUDIT = "NIGHT_AUDIT"
    MANUAL = "MANUAL"
    POS = "POS"
    SYSTEM = "SYSTEM"


class InvoiceType(str, Enum):
    PROFORMA = "PROFORMA"
    TAX_INVOICE = "TAX_INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"


class NightAuditStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocType(str, Enum):
    BOOKING = "BOOKING"
    FOLIO = "FOLIO"
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
