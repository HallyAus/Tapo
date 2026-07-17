"""Binary sensor platform: cloud connectivity for every account device."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MATTER_NATIVE_MODELS, base_model
from .coordinator import TapoCloudCoordinator
from .entity import TapoCloudEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = [
            TapoCloudConnectivitySensor(coordinator, device_id)
            for device_id in (coordinator.data or {})
            if device_id not in known
        ]
        known.update(entity._device_id for entity in new_entities)
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class TapoCloudConnectivitySensor(TapoCloudEntity, BinarySensorEntity):
    """Whether the device is connected to the TP-Link cloud.

    Created for every device on the account — including types this
    integration cannot control (hubs, cameras, vacuums) — so automations
    can react when TP-Link firmware updates knock devices offline.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "cloud_connection"

    def __init__(self, coordinator: TapoCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_cloud_connection"

    @property
    def available(self) -> bool:
        # Deliberately not gated on device.online — this sensor reports it.
        return self.coordinator.last_update_success and self.device is not None

    @property
    def is_on(self) -> bool | None:
        device = self.device
        return device.online if device else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.device
        if device is None:
            return {}
        return {
            "cloud_type": device.info.get("cloud_type"),
            "device_type": device.device_type,
            "model": device.model,
            "hardware_version": device.info.get("deviceHwVer"),
            "firmware_version": device.info.get("fwVer"),
            "device_region": device.info.get("deviceRegion"),
            # True when this hardware is Matter-certified and could be
            # commissioned into HA's local Matter integration instead.
            "matter_capable": base_model(device.model) in MATTER_NATIVE_MODELS,
        }
