"""Sensor platform: energy monitoring readings via the cloud."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CloudDevice, TapoCloudCoordinator
from .entity import TapoCloudEntity


@dataclass(frozen=True, kw_only=True)
class TapoCloudSensorDescription(SensorEntityDescription):
    """Describes one emeter reading."""

    emeter_key: str


SENSOR_DESCRIPTIONS: tuple[TapoCloudSensorDescription, ...] = (
    TapoCloudSensorDescription(
        key="current_power",
        emeter_key="power",
        translation_key="current_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
    ),
    TapoCloudSensorDescription(
        key="voltage",
        emeter_key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    TapoCloudSensorDescription(
        key="current",
        emeter_key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    TapoCloudSensorDescription(
        key="total_energy",
        emeter_key="total",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        new_entities: list[SensorEntity] = []
        for device_id, device in (coordinator.data or {}).items():
            if device_id in known or not device.emeter_supported or not device.emeter:
                continue
            known.add(device_id)
            new_entities.extend(
                TapoCloudSensor(coordinator, device_id, description)
                for description in SENSOR_DESCRIPTIONS
                if description.emeter_key in device.emeter
            )
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class TapoCloudSensor(TapoCloudEntity, SensorEntity):
    """One energy-monitoring reading."""

    entity_description: TapoCloudSensorDescription

    def __init__(
        self,
        coordinator: TapoCloudCoordinator,
        device_id: str,
        description: TapoCloudSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        device = self.device
        if device is None or not device.emeter:
            return None
        return device.emeter.get(self.entity_description.emeter_key)
