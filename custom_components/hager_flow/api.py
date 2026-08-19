"""Client for the E3/DC cloud backend used by the Hager flow portal.

The portal at flow.hager.com is a frontend for the E3/DC cloud API. Requests are
authenticated with a short-lived bearer token (10 minutes) which is obtained from
a long-lived refresh token (roughly 30 days).

This is an undocumented API. Hager offers an official one at
https://developer.hagerenergy.com/ which requires onboarding via api-team@e3dc.com;
once available it should be preferred over this client.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

# Renew the access token this many seconds before it actually expires.
TOKEN_REFRESH_MARGIN = 60


class HagerFlowError(Exception):
    """Base error for this client."""


class HagerFlowAuthError(HagerFlowError):
    """The refresh token was rejected and the user has to supply a new one."""


class HagerFlowConnectionError(HagerFlowError):
    """The backend could not be reached or returned an unexpected status."""


def _jwt_expiry(token: str) -> float | None:
    """Return the ``exp`` claim of a JWT, or None if it cannot be read.

    The signature is not verified — we only need to know when to renew, and the
    server remains the authority on whether a token is actually valid.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, ValueError, KeyError, binascii.Error, UnicodeDecodeError):
        _LOGGER.debug("Could not read expiry from access token")
        return None


class HagerFlowApi:
    """Talks to the E3/DC cloud and keeps the access token fresh."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        serial: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._refresh_token = refresh_token
        self._serial = serial
        self._base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def serial(self) -> str:
        """Serial number of the storage system."""
        return self._serial

    async def _async_token(self, force_refresh: bool = False) -> str:
        """Return a valid access token, renewing it when necessary."""
        async with self._lock:
            if not force_refresh and self._access_token and time.time() < self._expires_at:
                return self._access_token

            try:
                resp = await self._session.post(
                    f"{self._base_url}/auth-saml/re-auth",
                    json={"reAuthToken": self._refresh_token},
                    timeout=REQUEST_TIMEOUT,
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise HagerFlowConnectionError(f"Token refresh failed: {err}") from err

            if resp.status in (400, 401, 403):
                raise HagerFlowAuthError(
                    "Refresh token rejected. It is valid for about 30 days — "
                    "sign in at flow.hager.com and supply a new one."
                )
            if resp.status != 200:
                raise HagerFlowConnectionError(
                    f"Token refresh returned HTTP {resp.status}"
                )

            try:
                token = (await resp.json())["token"]
            except (aiohttp.ContentTypeError, ValueError, KeyError) as err:
                raise HagerFlowConnectionError(
                    "Token refresh returned an unexpected payload"
                ) from err

            self._access_token = token
            expiry = _jwt_expiry(token)
            # Without a readable expiry, fall back to a conservative lifetime.
            self._expires_at = (
                expiry - TOKEN_REFRESH_MARGIN if expiry else time.time() + 300
            )
            _LOGGER.debug("Renewed access token")
            return token

    async def _async_get(self, path: str) -> Any:
        """GET a path, refreshing the token once if it is rejected."""
        for force_refresh in (False, True):
            token = await self._async_token(force_refresh)
            try:
                resp = await self._session.get(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=REQUEST_TIMEOUT,
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise HagerFlowConnectionError(f"Request to {path} failed: {err}") from err

            if resp.status == 401 and not force_refresh:
                # Token may have expired early; retry once with a fresh one.
                continue
            if resp.status == 401:
                raise HagerFlowAuthError("Access token rejected by the backend")
            if resp.status in (403, 404):
                # The token is only scoped to the user's own installations, so a
                # serial that is not theirs comes back as 403 "Insufficient scope"
                # rather than 404.
                raise HagerFlowError(
                    f"No access to serial {self._serial}. Is the serial number correct?"
                )
            if resp.status != 200:
                raise HagerFlowConnectionError(f"{path} returned HTTP {resp.status}")

            try:
                return await resp.json()
            except (aiohttp.ContentTypeError, ValueError) as err:
                raise HagerFlowConnectionError(
                    f"{path} returned a non-JSON payload"
                ) from err

        raise HagerFlowAuthError("Access token rejected by the backend")

    async def async_get_status(self) -> dict[str, Any]:
        """Return the current live values."""
        return await self._async_get(f"/storages/{self._serial}/status")

    async def async_get_energy(self) -> dict[str, Any]:
        """Return cumulative energy counters in watt-hours.

        The endpoint reports a ``from``/``to`` pair; ``to`` holds the most recent
        counter reading, which lags real time by up to ~15 minutes.
        """
        now = int(time.time() * 1000)
        window_start = now - 2 * 3600 * 1000
        data = await self._async_get(
            f"/storages/{self._serial}/history-values/difference"
            f"?from={window_start}&to={now}&approach=true"
        )
        latest = data.get("to") if isinstance(data, dict) else None
        return latest if isinstance(latest, dict) else {}

    async def async_get_device_info(self) -> dict[str, Any]:
        """Return static metadata about the storage system."""
        data = await self._async_get(f"/storages/{self._serial}")
        return data if isinstance(data, dict) else {}
