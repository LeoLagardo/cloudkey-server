from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common / Generic Responses
# ---------------------------------------------------------------------------

class AiosellStandardResponse(BaseModel):
    success: Optional[bool] = None
    status: Optional[bool] = None
    message: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        if self.success is not None:
            return bool(self.success)
        if self.status is not None:
            return bool(self.status)
        return False


# ---------------------------------------------------------------------------
# Property Configuration & Remote Mapping
# ---------------------------------------------------------------------------

class AiosellRatePlanInfo(BaseModel):
    rateplan_id: str
    rateplan_name: str
    occupancy: int = 1
    no_of_meals: int = 0
    extra_adult: Optional[float] = 0.0
    description: Optional[str] = ""


class AiosellRoomInfo(BaseModel):
    room_id: str
    room_name: str
    count: int = 0
    active: bool = True
    type: str = "primary"
    min_occ: int = 1
    max_occ: int = 2
    rateplans: List[AiosellRatePlanInfo] = Field(default_factory=list)


class AiosellConnectedChannel(BaseModel):
    operation: str
    partner_id: str
    hotel_code: str
    rate_multiplier: Optional[float] = 1.0


class AiosellPropertyDetailsResponse(BaseModel):
    hotel_id: str
    hotel_name: str
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    property_category: Optional[str] = "hotel"
    tax_id: Optional[str] = ""
    rooms: List[AiosellRoomInfo] = Field(default_factory=list)
    connected_channels: List[AiosellConnectedChannel] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Outbound: Inventory Push
# ---------------------------------------------------------------------------

class RoomInventoryItem(BaseModel):
    roomCode: str
    available: int = Field(ge=0, description="Available inventory count")


class InventoryUpdateBlock(BaseModel):
    startDate: str = Field(description="Inclusive start date YYYY-MM-DD")
    endDate: str = Field(description="Inclusive end date YYYY-MM-DD")
    rooms: List[RoomInventoryItem]


class InventoryPushRequest(BaseModel):
    hotelCode: str
    updates: List[InventoryUpdateBlock]


# ---------------------------------------------------------------------------
# Outbound: Rate Push
# ---------------------------------------------------------------------------

class RateItem(BaseModel):
    roomCode: str
    rateplanCode: str
    rate: float = Field(ge=0.0, description="Nightly sell rate")
    extra_adult: Optional[float] = Field(None, description="Extra adult charge")
    extra_child: Optional[float] = Field(None, description="Extra child charge")
    occupancy: Optional[int] = Field(None, description="Base occupancy count")


class RateUpdateBlock(BaseModel):
    startDate: str = Field(description="Inclusive start date YYYY-MM-DD")
    endDate: str = Field(description="Inclusive end date YYYY-MM-DD")
    rates: List[RateItem]


class RatePushRequest(BaseModel):
    hotelCode: str
    updates: List[RateUpdateBlock]


# ---------------------------------------------------------------------------
# Outbound: Restrictions Push
# ---------------------------------------------------------------------------

class AiosellRestrictions(BaseModel):
    stopSell: Optional[bool] = False
    minimumStay: Optional[int] = 1
    maximumStay: Optional[int] = None
    closeOnArrival: Optional[bool] = False
    closeOnDeparture: Optional[bool] = False
    minimumStayArrival: Optional[int] = None
    maximumStayArrival: Optional[int] = None
    exactStayArrival: Optional[int] = None
    minimumAdvanceReservation: Optional[int] = None
    maximumAdvanceReservation: Optional[int] = None


class RoomRestrictionItem(BaseModel):
    roomCode: str
    restrictions: AiosellRestrictions


class InventoryRestrictionsUpdateBlock(BaseModel):
    startDate: str
    endDate: str
    rooms: List[RoomRestrictionItem]


class InventoryRestrictionsPushRequest(BaseModel):
    hotelCode: str
    toChannels: List[str] = Field(default_factory=list)
    updates: List[InventoryRestrictionsUpdateBlock]


class RateRestrictionItem(BaseModel):
    roomCode: str
    rateplanCode: str
    restrictions: AiosellRestrictions


class RateRestrictionsUpdateBlock(BaseModel):
    startDate: str
    endDate: str
    rates: List[RateRestrictionItem]


class RateRestrictionsPushRequest(BaseModel):
    hotelCode: str
    toChannels: List[str] = Field(default_factory=list)
    updates: List[RateRestrictionsUpdateBlock]


# ---------------------------------------------------------------------------
# Outbound: Operational Actions (No-Show & Multiplier)
# ---------------------------------------------------------------------------

class NoShowPushRequest(BaseModel):
    hotelCode: str
    bookingId: str
    channel: str = Field(description="e.g. gommt or booking.com")


class ChannelMultiplierPushRequest(BaseModel):
    hotelCode: str
    multiplier: float = Field(description="Factor: 1.2 is +20%, 0.9 is -10%")
    channels: List[str] = Field(min_length=1, description="Target OTA channels")


# ---------------------------------------------------------------------------
# Outbound: Data Query (Fetch API)
# ---------------------------------------------------------------------------

class AiosellDataFetchRequest(BaseModel):
    type: Literal["inventory", "rates", "reservation"]
    hotelCode: str
    startDate: str
    endDate: str


# ---------------------------------------------------------------------------
# Inbound: Reservation Webhook Payload (Aiosell -> CloudKey)
# ---------------------------------------------------------------------------

class AiosellBookingAmount(BaseModel):
    amountAfterTax: float = 0.0
    amountBeforeTax: float = 0.0
    tax: float = 0.0
    currency: str = "INR"
    commission: Optional[float] = None
    tcs: Optional[float] = None
    tds: Optional[float] = None


class AiosellGuestAddress(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zipCode: Optional[str] = None


class AiosellBookingGuest(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[AiosellGuestAddress] = None


class AiosellRoomOccupancy(BaseModel):
    adults: int = 1
    children: int = 0


class AiosellDailyPrice(BaseModel):
    date: str
    sellRate: float


class AiosellRoomBookingItem(BaseModel):
    roomCode: str
    rateplanCode: str
    guestName: Optional[str] = None
    occupancy: AiosellRoomOccupancy = Field(default_factory=AiosellRoomOccupancy)
    prices: List[AiosellDailyPrice] = Field(default_factory=list)


class AiosellEncryptedCreditCard(BaseModel):
    cardNumber: Optional[str] = None
    cvv: Optional[str] = None
    expiry: Optional[str] = None
    cardHolderName: Optional[str] = None
    cardType: Optional[str] = None
    activationDate: Optional[str] = None


class AiosellDecryptedCreditCard(BaseModel):
    cardNumber: Optional[str] = None
    cvv: Optional[str] = None
    expiry: Optional[str] = None
    cardHolderName: Optional[str] = None
    cardType: Optional[str] = None
    activationDate: Optional[str] = None


class AiosellReservationWebhookPayload(BaseModel):
    """
    Incoming webhook payload from Aiosell when an OTA reservation is created,
    modified, or cancelled.
    """
    action: Literal["book", "modify", "cancel"]
    hotelCode: str
    channel: str
    bookingId: str
    cmBookingId: Optional[str] = None
    bookedOn: Optional[str] = None
    checkin: Optional[str] = None
    checkout: Optional[str] = None
    segment: Optional[str] = "OTA"
    specialRequests: Optional[str] = None
    pah: Optional[bool] = False  # Pay at hotel
    amount: Optional[AiosellBookingAmount] = None
    guest: Optional[AiosellBookingGuest] = None
    rooms: Optional[List[AiosellRoomBookingItem]] = None
    creditCard: Optional[AiosellEncryptedCreditCard] = None


class AiosellWebhookResponse(BaseModel):
    success: bool = True
    message: str = "Reservation processed successfully"
