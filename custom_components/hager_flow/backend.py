"""Shared contract for the backends this integration can talk to.

There are two of them: the undocumented API behind the flow portal (``api.py``)
and the official one at developer.hagerenergy.com (``api_official.py``). They
report entirely different field names, so each client normalises its own
registers and the coordinator and entities never see backend-specific names.

Signs follow the installation's point of view: positive means charging the
battery and importing from the grid. A value a backend cannot supply for one
reading is ``None`` rather than zero, so an unavailable entity never
masquerades as a real reading of nought.

Neither backend covers the whole vocabulary, and they miss different parts of
it: the portal has no forecast, the official API reports no inverter output.
Each declares what it can supply in :attr:`HagerFlowBackend.provided_keys` and
the platforms register only those entities, because an entity that could never
hold anything is worse than an absent one.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Live readings, refreshed on every coordinator cycle.
LIVE_KEYS = frozenset(
    {
        "soc",
        "pv_power",
        "house_power",
        "inverter_power",
        "battery_power",
        "battery_charge_power",
        "battery_discharge_power",
        "grid_power",
        "grid_import_power",
        "grid_export_power",
        "online",
    }
)

# Cumulative counters in kilowatt-hours, refreshed on a slower cadence.
ENERGY_KEYS = frozenset(
    {
        "pv_energy",
        "house_energy",
        "grid_import_energy",
        "grid_export_energy",
        "battery_charge_energy",
        "battery_discharge_energy",
    }
)

# Expected production in kilowatt-hours. Each total carries the hourly profile
# it was summed from as ``<key>_hourly``, a list of
# ``{"start": iso8601, "pv_production": kWh}``.
FORECAST_KEYS = frozenset({"pv_forecast_today", "pv_forecast_tomorrow"})

ALL_KEYS = LIVE_KEYS | ENERGY_KEYS | FORECAST_KEYS


class HagerFlowError(Exception):
    """Base error for both backends."""


class HagerFlowAuthError(HagerFlowError):
    """Credentials were rejected and the user has to supply new ones."""


class HagerFlowConnectionError(HagerFlowError):
    """The backend could not be reached or returned an unexpected status."""


@runtime_checkable
class HagerFlowBackend(Protocol):
    """What the coordinator needs from a backend."""

    @property
    def device_key(self) -> str:
        """Stable identifier for the installation, used for unique ids."""

    @property
    def provided_keys(self) -> frozenset[str]:
        """Which of the normalised keys this backend can supply."""

    async def async_get_device_info(self) -> dict[str, Any]:
        """Return static metadata, fetched once during setup."""

    async def async_get_live(self) -> dict[str, Any]:
        """Return the normalised live values."""

    async def async_get_energy(self) -> dict[str, Any]:
        """Return the normalised cumulative counters."""

    async def async_get_forecast(self) -> dict[str, Any]:
        """Return the normalised production forecast.

        Only called when the backend claims a key from :data:`FORECAST_KEYS`.
        """
