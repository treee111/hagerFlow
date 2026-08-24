"""Data coordinator for the Hager flow integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .backend import (
    FORECAST_KEYS,
    HagerFlowAuthError,
    HagerFlowBackend,
    HagerFlowError,
)
from .const import (
    DOMAIN,
    ENERGY_UPDATE_INTERVAL,
    FORECAST_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class HagerFlowCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches live values frequently and energy counters on a slower cadence.

    Which backend is behind ``api`` — the flow portal or the official API — is
    invisible here: both hand back the same normalised vocabulary.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: HagerFlowBackend
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.api = api
        self.device_info_raw: dict[str, Any] = {}
        self._energy: dict[str, Any] = {}
        self._energy_fetched_at: datetime | None = None
        self._forecast: dict[str, Any] = {}
        self._forecast_fetched_at: datetime | None = None

    async def _async_setup(self) -> None:
        """Fetch static device metadata once, before the first refresh."""
        try:
            self.device_info_raw = await self.api.async_get_device_info()
        except HagerFlowAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HagerFlowError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the current state of the installation."""
        now = dt_util.utcnow()
        try:
            live = await self.api.async_get_live()

            if (
                self._energy_fetched_at is None
                or now - self._energy_fetched_at >= ENERGY_UPDATE_INTERVAL
            ):
                self._energy = await self.api.async_get_energy()
                self._energy_fetched_at = now
        except HagerFlowAuthError as err:
            # Triggers the reauth flow so the user can supply fresh credentials.
            raise ConfigEntryAuthFailed(str(err)) from err
        except HagerFlowError as err:
            raise UpdateFailed(str(err)) from err

        await self._async_refresh_forecast(now)

        # The counters and the forecast are polled on slower cadences, so they
        # are carried over and are absent until their first poll lands.
        return {**live, **self._energy, **self._forecast}

    async def _async_refresh_forecast(self, now: datetime) -> None:
        """Refresh the production forecast, if the backend has one.

        Deliberately outside the block above: the forecast is a nice-to-have,
        and losing it must not take the live readings down with it.
        """
        if not FORECAST_KEYS & self.api.provided_keys:
            return
        if (
            self._forecast_fetched_at is not None
            and now - self._forecast_fetched_at < FORECAST_UPDATE_INTERVAL
        ):
            return

        try:
            forecast = await self.api.async_get_forecast()
        except HagerFlowError as err:
            _LOGGER.debug("Forecast unavailable: %s", err)
            return

        # An empty answer keeps the previous forecast rather than blanking the
        # sensors, but is not treated as a successful poll.
        if forecast:
            self._forecast = forecast
            self._forecast_fetched_at = now
