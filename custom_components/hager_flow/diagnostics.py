"""Diagnostics support for the Hager flow integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HagerFlowConfigEntry
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_REAUTH_TOKEN

# Credentials, plus everything that identifies the installation or its owner.
# Diagnostics end up attached to bug reports, and the official backend returns
# the owner's name in the installation title and a full postal address with it.
TO_REDACT = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_REAUTH_TOKEN,
    "Anschrift_ID",
    "IP",
    "address",
    "installerID",
    "latitude",
    "longitude",
    "name",
    "ownerID",
    "ownerId",
    "serialNumber",
}


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
