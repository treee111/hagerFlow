"""The Hager flow integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HagerFlowApi
from .const import CONF_REAUTH_TOKEN, CONF_SERIAL
from .coordinator import HagerFlowCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type HagerFlowConfigEntry = ConfigEntry[HagerFlowCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HagerFlowConfigEntry) -> bool:
    """Set up Hager flow from a config entry."""
    api = HagerFlowApi(
        async_get_clientsession(hass),
        entry.data[CONF_REAUTH_TOKEN],
        entry.data[CONF_SERIAL],
    )

    coordinator = HagerFlowCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HagerFlowConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: HagerFlowConfigEntry
) -> None:
    """Reload the entry when its options or credentials change."""
    await hass.config_entries.async_reload(entry.entry_id)
