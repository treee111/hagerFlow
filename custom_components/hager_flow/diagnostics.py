"""Diagnostics support for the Hager flow integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HagerFlowConfigEntry
from .const import CONF_REAUTH_TOKEN

TO_REDACT = {CONF_REAUTH_TOKEN, "ownerID", "installerID", "Anschrift_ID", "IP"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HagerFlowConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "device": async_redact_data(coordinator.device_info_raw, TO_REDACT),
        "data": coordinator.data,
    }
