"""Base entity for the Hager flow integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, PORTAL_URL
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

        key = coordinator.api.device_key
        raw = coordinator.device_info_raw
        # The official backend nests the hardware under "device"; the portal
        # backend reports it flat. Either may be missing entirely.
        hardware = raw.get("device") if isinstance(raw.get("device"), dict) else {}

        self._attr_unique_id = f"{key}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            name="Hager flow",
            manufacturer=MANUFACTURER,
            model=raw.get("product") or hardware.get("productName") or "flow",
            sw_version=raw.get("sw_release"),
            serial_number=raw.get("serial") or hardware.get("serialNumber") or key,
            configuration_url=PORTAL_URL,
        )

    @property
    def available(self) -> bool:
        """Return whether the entity currently has a usable value."""
        return super().available and self.coordinator.data is not None
