import logging
from typing import Any, Dict, Optional
import httpx

from app.config import settings
from app.integrations.aiosell.auth import generate_basic_auth_header
from app.integrations.aiosell.exceptions import (
    AiosellApiError,
    AiosellAuthError,
    AiosellConfigError,
)
from app.integrations.aiosell.schemas import (
    AiosellDataFetchRequest,
    AiosellPropertyDetailsResponse,
    AiosellStandardResponse,
    ChannelMultiplierPushRequest,
    InventoryPushRequest,
    InventoryRestrictionsPushRequest,
    NoShowPushRequest,
    RatePushRequest,
    RateRestrictionsPushRequest,
)

logger = logging.getLogger(__name__)


class AiosellClient:
    """
    Asynchronous API Client for Aiosell Channel Manager.
    Docs: https://apidocs.aiosell.com
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        pms_slug: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.AIOSELL_BASE_URL).rstrip("/")
        self.pms_slug = pms_slug or settings.AIOSELL_DEFAULT_PMS_SLUG
        self.username = username or settings.AIOSELL_USERNAME
        self.password = password or settings.AIOSELL_PASSWORD
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.username:
            headers["Authorization"] = generate_basic_auth_header(self.username, self.password)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        close_after = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_after = True

        try:
            logger.debug(f"[Aiosell] Request: {method} {url} | params={params}")
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
            )

            if response.status_code == 401 or response.status_code == 403:
                raise AiosellAuthError(
                    f"Authentication failed with Aiosell API: {response.text}",
                    details=response.text,
                )

            if not (200 <= response.status_code < 300):
                raise AiosellApiError(
                    message=f"Aiosell API responded with error status {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )

            try:
                return response.json()
            except Exception:
                return response.text

        except httpx.RequestError as exc:
            logger.error(f"[Aiosell] Connection error during {method} {url}: {exc}")
            raise AiosellApiError(
                message=f"HTTP request error communicating with Aiosell: {exc}",
                status_code=500,
            ) from exc
        finally:
            if close_after:
                await client.aclose()

    # -----------------------------------------------------------------------
    # Property & Mapping Endpoints
    # -----------------------------------------------------------------------

    async def get_property_details(
        self,
        hotel_code: str,
        partner_id: Optional[str] = None,
    ) -> AiosellPropertyDetailsResponse:
        """
        Fetch full property configuration: rooms, rate plans, and connected channels.
        Endpoint: GET /property_details/{hotelCode}?partnerId={pms}
        """
        pid = partner_id or self.pms_slug
        path = f"/property_details/{hotel_code}"
        params = {"partnerId": pid}
        data = await self._request("GET", path, params=params)
        return AiosellPropertyDetailsResponse.model_validate(data)

    # -----------------------------------------------------------------------
    # Push Endpoints (PMS -> Aiosell)
    # -----------------------------------------------------------------------

    async def push_inventory(
        self,
        payload: InventoryPushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Push room availability from PMS to Aiosell.
        Endpoint: POST /update/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/update/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    async def push_rates(
        self,
        payload: RatePushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Send rate updates per room type and rate plan.
        Endpoint: POST /update-rates/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/update-rates/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    async def push_inventory_restrictions(
        self,
        payload: InventoryRestrictionsPushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Push room-level restrictions (stop-sell, min/max stay, CTA/CTD).
        Endpoint: POST /update/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/update/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    async def push_rate_restrictions(
        self,
        payload: RateRestrictionsPushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Push rate-plan-level restrictions.
        Endpoint: POST /update-rates/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/update-rates/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    async def mark_noshow(
        self,
        payload: NoShowPushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Mark a booking as a no-show (supports booking.com and gommt).
        Endpoint: POST /marknoshow/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/marknoshow/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    async def set_channel_multiplier(
        self,
        payload: ChannelMultiplierPushRequest,
        pms_slug: Optional[str] = None,
    ) -> AiosellStandardResponse:
        """
        Apply a rate multiplier factor to selected channels for a property.
        Endpoint: POST /channel_multiplier/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/channel_multiplier/{slug}"
        data = await self._request("POST", path, json_data=payload.model_dump())
        return AiosellStandardResponse.model_validate(data)

    # -----------------------------------------------------------------------
    # Fetch / Polling Endpoints (PMS -> Aiosell)
    # -----------------------------------------------------------------------

    async def fetch_data(
        self,
        payload: AiosellDataFetchRequest,
        pms_slug: Optional[str] = None,
    ) -> Any:
        """
        Fetch inventory, rates, or reservations from Aiosell.
        Endpoint: POST /data/{pms}
        """
        slug = pms_slug or self.pms_slug
        path = f"/data/{slug}"
        return await self._request("POST", path, json_data=payload.model_dump())
