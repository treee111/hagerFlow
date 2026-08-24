"""Client for the official Hager Energy / E3/DC API.

Documented at https://developer.hagerenergy.com/. Unlike the portal client in
``api.py`` this one authenticates with an OAuth 2 client credentials grant
(RFC 6749), so there is no token that expires after a month and has to be
copied out of a browser: the client id and secret are permanent and the
integration derives short-lived access tokens from them on its own.

Access is requested through the developer portal; until self-service lands in
the MyE3/DC portal, Hager creates the OAuth client manually on request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .api import (
    REQUEST_TIMEOUT,
    TOKEN_REFRESH_MARGIN,
    HagerFlowAuthError,
    HagerFlowConnectionError,
    HagerFlowError,
)
from .const import OFFICIAL_API_BASE_URL, OFFICIAL_TOKEN_URL

_LOGGER = logging.getLogger(__name__)

# The token response advertises expires_in: 300 and refresh_expires_in: 0 — the
# client credentials flow has no refresh token, so an expired token is simply
# requested again with the same call.
DEFAULT_TOKEN_LIFETIME = 300


class HagerFlowOfficialApi:
    """Talks to api.hagerenergy.com and keeps the access token fresh."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        installation_id: str | int | None = None,
        base_url: str = OFFICIAL_API_BASE_URL,
        token_url: str = OFFICIAL_TOKEN_URL,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._installation_id = str(installation_id) if installation_id else None
        self._base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def installation_id(self) -> str | None:
        """Installation the client is bound to, once it is known."""
        return self._installation_id

    async def _async_token(self, force_refresh: bool = False) -> str:
        """Return a valid access token, requesting a new one when necessary."""
        async with self._lock:
            if (
                not force_refresh
                and self._access_token
                and time.time() < self._expires_at
            ):
                return self._access_token

            try:
                resp = await self._session.post(
                    self._token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise HagerFlowConnectionError(f"Token request failed: {err}") from err

            if resp.status in (400, 401, 403):
                raise HagerFlowAuthError(
                    "Client id or client secret rejected by the token endpoint"
                )
            if resp.status != 200:
                raise HagerFlowConnectionError(
                    f"Token request returned HTTP {resp.status}"
                )

            try:
                payload = await resp.json()
                token = payload["access_token"]
            except (aiohttp.ContentTypeError, ValueError, KeyError) as err:
                raise HagerFlowConnectionError(
                    "Token request returned an unexpected payload"
                ) from err

            lifetime = payload.get("expires_in") or DEFAULT_TOKEN_LIFETIME
            try:
                lifetime = int(lifetime)
            except (TypeError, ValueError):
                lifetime = DEFAULT_TOKEN_LIFETIME

            self._access_token = token
            # Renew a little early so a request never travels with a token that
            # expires in flight. Short lifetimes must not end up negative.
            self._expires_at = time.time() + max(lifetime - TOKEN_REFRESH_MARGIN, 30)
            _LOGGER.debug("Obtained access token, valid for %s s", lifetime)
            return token

    async def _async_get(self, path: str) -> Any:
        """GET a path and unwrap the response envelope.

        Responses follow a JSend-style wrapper: a ``status`` field next to the
        payload in ``data``.
        """
        for force_refresh in (False, True):
            token = await self._async_token(force_refresh)
            try:
                resp = await self._session.get(
                    f"{self._base_url}{path}",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout=REQUEST_TIMEOUT,
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise HagerFlowConnectionError(
                    f"Request to {path} failed: {err}"
                ) from err

            if resp.status == 401 and not force_refresh:
                # The 5 minute token may have expired early; retry once.
                continue
            if resp.status == 401:
                raise HagerFlowAuthError("Access token rejected by the API")
            if resp.status == 404:
                raise HagerFlowError(f"{path} not found — is the installation id right?")
            if resp.status != 200:
                raise HagerFlowConnectionError(f"{path} returned HTTP {resp.status}")

            try:
                payload = await resp.json()
            except (aiohttp.ContentTypeError, ValueError) as err:
                raise HagerFlowConnectionError(
                    f"{path} returned a non-JSON payload"
                ) from err

            return _unwrap(payload, path)

        raise HagerFlowAuthError("Access token rejected by the API")

    async def async_get_installations(self) -> list[dict[str, Any]]:
        """Return every installation the credentials have access to."""
        data = await self._async_get("/installations")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        # Paginated collections wrap the rows one level deeper.
        if isinstance(data, dict):
            for key in ("items", "installations", "content"):
                rows = data.get(key)
                if isinstance(rows, list):
                    return [item for item in rows if isinstance(item, dict)]
        raise HagerFlowConnectionError("Unexpected payload for /installations")

    def _require_installation(self) -> str:
        """Return the configured installation id or fail loudly."""
        if not self._installation_id:
            raise HagerFlowError("No installation id configured")
        return self._installation_id

    async def async_get_installation(self) -> dict[str, Any]:
        """Return master data for the configured installation."""
        data = await self._async_get(f"/installations/{self._require_installation()}")
        return data if isinstance(data, dict) else {}

    async def async_get_energy_current(self) -> dict[str, Any]:
        """Return the most recent energy flows in watts."""
        data = await self._async_get(
            f"/installations/{self._require_installation()}/energy/current"
        )
        return data if isinstance(data, dict) else {}

    async def async_get_energy_total(self) -> dict[str, Any]:
        """Return the cumulative counters in watt-hours since installation."""
        data = await self._async_get(
            f"/installations/{self._require_installation()}/energy/total"
        )
        return data if isinstance(data, dict) else {}

    async def async_get_energy_daily(self, day: str) -> dict[str, Any]:
        """Return the hourly energy values for one day (``YYYY-MM-DD``)."""
        data = await self._async_get(
            f"/installations/{self._require_installation()}/energy/daily/{day}"
        )
        return data if isinstance(data, dict) else {}

    async def async_get_pv_configuration(self) -> dict[str, Any]:
        """Return the photovoltaic configuration (string layout, peak power)."""
        data = await self._async_get(
            f"/installations/{self._require_installation()}/pv-configuration"
        )
        return data if isinstance(data, dict) else {}


def _unwrap(payload: Any, path: str) -> Any:
    """Return the ``data`` member of an envelope, raising on a failure status."""
    if not isinstance(payload, dict) or "status" not in payload:
        # Not enveloped — hand the body through unchanged.
        return payload

    status = payload.get("status")
    if status == "success":
        return payload.get("data")
    # "fail" means the request was wrong, "error" that the backend broke; both
    # carry a message worth surfacing rather than a bare status code.
    message = payload.get("message") or f"{path} returned status {status!r}"
    if status == "fail":
        raise HagerFlowError(message)
    raise HagerFlowConnectionError(message)
