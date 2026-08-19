"""Base entity for the Hager flow integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HagerFlowCoordinator


class HagerFlowEntity(CoordinatorEntity[HagerFlowCoordinator]):
    """Common device wiring for all Hager flow entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HagerFlowCoordinator, description: EntityDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description

        serial = coordinator.api.serial
        raw = coordinator.device_info_raw

        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name="Hager flow",
            manufacturer=MANUFACTURER,
            model=raw.get("product") or "flow",
            sw_version=raw.get("sw_release"),
            serial_number=serial,
            configuration_url="https://flow.hager.com",
        )

    @property
    def available(self) -> bool:
        """Return whether the entity currently has a usable value."""
        return super().available and self.coordinator.data is not None
