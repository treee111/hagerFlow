"""Binary sensor platform for the Hager flow integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HagerFlowCoordinator
from .entity import HagerFlowEntity

ONLINE = BinarySensorEntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Hager flow binary sensors."""
    coordinator: HagerFlowCoordinator = entry.runtime_data
    async_add_entities([HagerFlowOnlineSensor(coordinator, ONLINE)])


class HagerFlowOnlineSensor(HagerFlowEntity, BinarySensorEntity):
    """Reports whether the installation is reporting to the portal."""

    @property
    def is_on(self) -> bool | None:
        """Return True when the installation is online."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("online")
