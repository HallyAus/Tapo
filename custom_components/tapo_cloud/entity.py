"""Base entity for Tapo & Kasa Cloud Bridge."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CloudDevice, TapoCloudCoordinator


def _format_mac(raw_mac: str | None) -> str | None:
    """Normalize the cloud's MAC format (often colon-less) for the registry."""
    if not raw_mac:
        return None
    mac = raw_mac.replace(":", "").replace("-", "").lower()
    if len(mac) != 12 or not all(c in "0123456789abcdef" for c in mac):
        return None
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


class TapoCloudEntity(CoordinatorEntity[TapoCloudCoordinator]):
    """Entity tied to one cloud device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TapoCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def device(self) -> CloudDevice | None:
        return (self.coordinator.data or {}).get(self._device_id)

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.online

    @property
    def device_info(self) -> DeviceInfo | None:
        device = self.device
        if device is None:
            return None
        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="TP-Link",
            model=device.model,
            name=device.alias,
            sw_version=device.info.get("fwVer"),
            hw_version=device.info.get("deviceHwVer"),
        )
        mac = _format_mac(device.info.get("deviceMac"))
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info
