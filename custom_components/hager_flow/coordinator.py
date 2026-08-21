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

from .api import HagerFlowApi, HagerFlowAuthError, HagerFlowError
from .const import DOMAIN, ENERGY_UPDATE_INTERVAL, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _phase_sum(raw: dict[str, Any], prefix: str, count: int = 3) -> int:
    """Sum the per-phase or per-string registers sharing a prefix."""
    return sum(int(raw.get(f"{prefix}{i}", 0) or 0) for i in range(1, count + 1))


def _pv_energy(energy: dict[str, Any]) -> float | None:
    """Derive the PV production counter in kilowatt-hours.

    ``Production`` does not hold what its name promises. At every reading it
    equals ``Consumption + NetIn - NetOut`` to the watt-hour, which is the
    energy balance with the battery left out — so the value keeps climbing
    overnight at roughly the house base load. Adding the battery registers back
    restores the real production; cross-checked over a day against the
    integrated live PV power, which it matches to within 0.2 %.
    """
    try:
        derived = (
            float(energy["Production"])
            + float(energy["BatPowerIn"])
            - float(energy["BatPowerOut"])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return round(derived / 1000, 3)


class HagerFlowCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches live values frequently and energy counters on a slower cadence."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: HagerFlowApi
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
        try:
            status = await self.api.async_get_status()

            now = dt_util.utcnow()
            if (
                self._energy_fetched_at is None
                or now - self._energy_fetched_at >= ENERGY_UPDATE_INTERVAL
            ):
                self._energy = await self.api.async_get_energy()
                self._energy_fetched_at = now
        except HagerFlowAuthError as err:
            # Triggers the reauth flow so the user can supply a fresh token.
            raise ConfigEntryAuthFailed(str(err)) from err
        except HagerFlowError as err:
            raise UpdateFailed(str(err)) from err

        return self._parse(status, self._energy)

    @staticmethod
    def _parse(raw: dict[str, Any], energy: dict[str, Any]) -> dict[str, Any]:
        """Turn the raw registers into the values the entities expose.

        Battery, grid and consumption registers are reported per phase and PV per
        string, so each group is summed. Sign convention: positive means charging
        the battery and importing from the grid.
        """
        battery = _phase_sum(raw, "POWER_BAT_")
        grid = _phase_sum(raw, "POWER_ROOTLM_L")

        data: dict[str, Any] = {
            "soc": raw.get("SOC"),
            "pv_power": _phase_sum(raw, "POWER_PV_S"),
            "house_power": _phase_sum(raw, "POWER_C_L"),
            "inverter_power": _phase_sum(raw, "POWER_AC_L"),
            "battery_power": battery,
            "battery_charge_power": max(battery, 0),
            "battery_discharge_power": max(-battery, 0),
            "grid_power": grid,
            "grid_import_power": max(grid, 0),
            "grid_export_power": max(-grid, 0),
            "online": raw.get("offlineLevel") == 0,
        }

        # Cumulative counters in watt-hours; absent until the first energy poll.
        # The grid registers are named from the grid's point of view, not the
        # installation's: ``NetIn`` counts energy going *into* the grid and is
        # therefore the export counter, ``NetOut`` the import one.
        for key, source in (
            ("house_energy", "Consumption"),
            ("grid_import_energy", "NetOut"),
            ("grid_export_energy", "NetIn"),
            ("battery_charge_energy", "BatPowerIn"),
            ("battery_discharge_energy", "BatPowerOut"),
        ):
            value = energy.get(source)
            data[key] = round(float(value) / 1000, 3) if value is not None else None

        data["pv_energy"] = _pv_energy(energy)

        return data
