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
from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiohttp

from .api import REQUEST_TIMEOUT, TOKEN_REFRESH_MARGIN
from .backend import (
    ENERGY_KEYS,
    FORECAST_KEYS,
    LIVE_KEYS,
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

# How stale a live reading may be before the installation counts as offline.
STALE_AFTER = timedelta(minutes=10)


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

    @property
    def device_key(self) -> str:
        """Stable identifier for this installation."""
        return self._require_installation()

    @property
    def provided_keys(self) -> frozenset[str]:
        """Everything but the inverter output, which this API does not report.

        ``energy/current`` carries no AC output figure. It exists on the device
        measurements, which are a separate request this client does not make.
        """
        return (LIVE_KEYS - {"inverter_power"}) | ENERGY_KEYS | FORECAST_KEYS

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

    async def async_get_production_forecast(self, day: str) -> dict[str, Any]:
        """Return the hourly production forecast for one day.

        The backend only serves today and tomorrow; anything else is refused
        with ``must be either today or tomorrow``.
        """
        data = await self._async_get(
            f"/installations/{self._require_installation()}/forecast/production/{day}"
        )
        return data if isinstance(data, dict) else {}

    async def async_get_pv_configuration(self) -> dict[str, Any]:
        """Return the photovoltaic configuration (string layout, peak power)."""
        data = await self._async_get(
            f"/installations/{self._require_installation()}/pv-configuration"
        )
        return data if isinstance(data, dict) else {}


    async def async_get_device_info(self) -> dict[str, Any]:
        """Return static metadata, merging the installation and its hardware."""
        info = dict(await self.async_get_installation())
        try:
            devices = await self._async_get(
                f"/installations/{self._require_installation()}/devices"
            )
        except HagerFlowError:
            # Master data is enough to set the device up; hardware detail is a
            # bonus and must not keep the integration from starting.
            _LOGGER.debug("Could not read device list", exc_info=True)
            return info

        if isinstance(devices, list):
            # A farm can hold several storage devices; the first one carries the
            # serial and product name shown on the device page.
            primary = next((d for d in devices if isinstance(d, dict)), None)
            if primary:
                info["device"] = primary
        return info

    async def async_get_live(self) -> dict[str, Any]:
        """Return the normalised live values."""
        return normalise_live(await self.async_get_energy_current())

    async def async_get_energy(self) -> dict[str, Any]:
        """Return the normalised cumulative counters in kilowatt-hours."""
        return normalise_energy(await self.async_get_energy_total())

    async def async_get_forecast(self) -> dict[str, Any]:
        """Return the normalised forecast for today and tomorrow.

        The two days are separate requests, and a missing tomorrow must not
        cost us today — around midnight the backend has been seen to serve one
        before the other.
        """
        today = date.today()
        forecast: dict[str, Any] = {}
        for key, day in (
            ("pv_forecast_today", today),
            ("pv_forecast_tomorrow", today + timedelta(days=1)),
        ):
            try:
                payload = await self.async_get_production_forecast(day.isoformat())
            except HagerFlowError:
                _LOGGER.debug("No forecast for %s", day, exc_info=True)
                continue
            forecast.update(normalise_forecast_day(payload, key))
        return forecast


def _int(value: Any) -> int | None:
    """Return an integer register value, or None when it is absent."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _kwh(value: Any) -> float | None:
    """Convert a watt-hour counter to kilowatt-hours."""
    if value is None:
        return None
    try:
        return round(float(value) / 1000, 3)
    except (TypeError, ValueError):
        return None


def _is_fresh(timestamp: Any) -> bool:
    """Return whether a reading is recent enough to call the system online.

    ``energy/current`` advances every 10 to 30 seconds while the installation
    is connected, so a reading several minutes old means the cloud has lost
    contact with it. There is no explicit online flag on this endpoint.
    """
    if not isinstance(timestamp, str):
        return False
    try:
        taken = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if taken.tzinfo is None:
        taken = taken.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - taken < STALE_AFTER


def normalise_live(current: dict[str, Any]) -> dict[str, Any]:
    """Turn an ``energy/current`` payload into the shared vocabulary.

    Sign conventions match the shared contract as they stand: ``gridPower`` is
    negative while exporting, and ``batteryChargePower`` is negative while the
    battery is discharging.
    """
    battery = _int(current.get("batteryChargePower"))
    grid = _int(current.get("gridPower"))

    return {
        "soc": _int(current.get("batteryStateOfCharge")),
        "pv_power": _int(current.get("pvProduction")),
        "house_power": _int(current.get("consumption")),
        # The installation-level endpoint reports no inverter output; that
        # lives on the device measurements, which this client does not poll.
        "inverter_power": None,
        "battery_power": battery,
        "battery_charge_power": max(battery, 0) if battery is not None else None,
        "battery_discharge_power": max(-battery, 0) if battery is not None else None,
        "grid_power": grid,
        "grid_import_power": max(grid, 0) if grid is not None else None,
        "grid_export_power": max(-grid, 0) if grid is not None else None,
        "online": _is_fresh(current.get("time")),
    }


def normalise_energy(total: dict[str, Any]) -> dict[str, Any]:
    """Turn an ``energy/total`` payload into kilowatt-hours.

    Unlike the portal backend nothing has to be derived here: the API names
    every counter for what it is, and ``pvProduction`` is the gross DC yield
    rather than the AC balance the portal registers add up to.
    """
    totals = total.get("totals")
    if not isinstance(totals, dict):
        # Older payloads only carry the per-period rows; the last one is the
        # running total when the resolution spans the whole period.
        values = total.get("values")
        totals = values[-1] if isinstance(values, list) and values else {}
    if not isinstance(totals, dict):
        totals = {}

    return {
        "pv_energy": _kwh(totals.get("pvProduction")),
        "house_energy": _kwh(totals.get("consumption")),
        "grid_import_energy": _kwh(totals.get("gridConsumption")),
        "grid_export_energy": _kwh(totals.get("gridFeedIn")),
        "battery_charge_energy": _kwh(totals.get("batteryCharge")),
        "battery_discharge_energy": _kwh(totals.get("batteryDischarge")),
    }


def normalise_forecast_day(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Turn one forecast payload into a total and the profile behind it.

    The backend reports the day as hourly watt-hours. The total is what the
    sensor shows; the hourly profile rides along as an attribute so it can be
    charted without a second request.
    """
    values = payload.get("values")
    if not isinstance(values, list) or not values:
        return {}

    hourly: list[dict[str, Any]] = []
    total = 0.0
    for row in values:
        if not isinstance(row, dict):
            continue
        production = _kwh(row.get("pvProduction"))
        start = row.get("startPeriod")
        if production is None or not isinstance(start, str):
            continue
        total += production
        hourly.append({"start": start, "pv_production": production})

    if not hourly:
        return {}
    return {key: round(total, 3), f"{key}_hourly": hourly}


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
