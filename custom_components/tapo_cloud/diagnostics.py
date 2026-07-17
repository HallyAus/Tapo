"""Diagnostics support for Tapo & Kasa Cloud Bridge."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_KASA_REFRESH_TOKEN,
    CONF_TAPO_REFRESH_TOKEN,
    CONF_TERM_ID,
    DOMAIN,
)
from .coordinator import TapoCloudCoordinator

REDACT_ENTRY = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_TERM_ID,
    CONF_KASA_REFRESH_TOKEN,
    CONF_TAPO_REFRESH_TOKEN,
}
REDACT_DEVICE = {
    "deviceId",
    "deviceMac",
    "hwId",
    "fwId",
    "oemId",
    "alias",
    "deviceName",
    "latitude",
    "longitude",
    "ssid",
    "mac",
    "hw_id",
    "fw_id",
    "oem_id",
    "dev_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator: TapoCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = [
        {
            "info": async_redact_data(device.info, REDACT_DEVICE),
            "sysinfo": async_redact_data(device.sysinfo, REDACT_DEVICE)
            if device.sysinfo
            else None,
            "emeter": device.emeter,
            "emeter_supported": device.emeter_supported,
            "online": device.online,
        }
        for device in (coordinator.data or {}).values()
    ]
    return {
        "entry": async_redact_data(dict(entry.data), REDACT_ENTRY),
        "options": dict(entry.options),
        "devices": devices,
    }
