"""Sensor platform for the Hager flow integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HagerFlowCoordinator
from .entity import HagerFlowEntity


@dataclass(frozen=True, kw_only=True)
class HagerFlowSensorDescription(SensorEntityDescription):
    """Describes a sensor and the coordinator key it reads."""

    data_key: str


POWER_SENSORS: tuple[HagerFlowSensorDescription, ...] = (
    HagerFlowSensorDescription(
        key="soc",
        data_key="soc",
        translation_key="soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HagerFlowSensorDescription(
        key="pv_power",
        data_key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HagerFlowSensorDescription(
        key="house_power",
        data_key="house_power",
        translation_key="house_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HagerFlowSensorDescription(
        key="battery_power",
        data_key="battery_power",
        translation_key="battery_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HagerFlowSensorDescription(
        key="grid_power",
        data_key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HagerFlowSensorDescription(
        key="inverter_power",
        data_key="inverter_power",
        translation_key="inverter_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Unsigned variants, handy for template-free automations and graphs.
    HagerFlowSensorDescription(
        key="battery_charge_power",
        data_key="battery_charge_power",
        translation_key="battery_charge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HagerFlowSensorDescription(
        key="battery_discharge_power",
        data_key="battery_discharge_power",
        translation_key="battery_discharge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HagerFlowSensorDescription(
        key="grid_import_power",
        data_key="grid_import_power",
        translation_key="grid_import_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    HagerFlowSensorDescription(
        key="grid_export_power",
        data_key="grid_export_power",
        translation_key="grid_export_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
)

# Cumulative counters, ready to be used directly in the energy dashboard.
ENERGY_SENSORS: tuple[HagerFlowSensorDescription, ...] = (
    HagerFlowSensorDescription(
        key="pv_energy",
        data_key="pv_energy",
        translation_key="pv_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    HagerFlowSensorDescription(
        key="house_energy",
        data_key="house_energy",
        translation_key="house_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    HagerFlowSensorDescription(
        key="grid_import_energy",
        data_key="grid_import_energy",
        translation_key="grid_import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    HagerFlowSensorDescription(
        key="grid_export_energy",
        data_key="grid_export_energy",
        translation_key="grid_export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    HagerFlowSensorDescription(
        key="battery_charge_energy",
        data_key="battery_charge_energy",
        translation_key="battery_charge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    HagerFlowSensorDescription(
        key="battery_discharge_energy",
        data_key="battery_discharge_energy",
        translation_key="battery_discharge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Hager flow sensors."""
    coordinator: HagerFlowCoordinator = entry.runtime_data
    async_add_entities(
        HagerFlowSensor(coordinator, description)
        for description in POWER_SENSORS + ENERGY_SENSORS
    )


class HagerFlowSensor(HagerFlowEntity, SensorEntity):
    """A single measurement of the installation."""

    entity_description: HagerFlowSensorDescription

    @property
    def native_value(self) -> float | int | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def available(self) -> bool:
        """Energy counters stay unavailable until the first energy poll."""
        return super().available and self.native_value is not None
