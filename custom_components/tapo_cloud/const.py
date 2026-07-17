"""Constants for the Tapo & Kasa Cloud Bridge integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "tapo_cloud"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_TERM_ID = "term_id"
CONF_KASA_REFRESH_TOKEN = "kasa_refresh_token"
CONF_TAPO_REFRESH_TOKEN = "tapo_refresh_token"
CONF_KASA_HOST = "kasa_host"
CONF_TAPO_HOST = "tapo_host"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 600

# Cloud device-list "status" value meaning the device is connected to
# TP-Link's cloud and therefore controllable through this integration.
STATUS_ONLINE = 1

EVENT_DEVICE_OFFLINE = f"{DOMAIN}_device_offline"
EVENT_DEVICE_ONLINE = f"{DOMAIN}_device_online"

# deviceType values, as returned by getDeviceList, grouped by how we
# should represent them in Home Assistant.
SWITCH_DEVICE_TYPES = {
    "IOT.SMARTPLUGSWITCH",
    "IOT.RANGEEXTENDER.SMARTPLUG",
    "SMART.KASAPLUG",
    "SMART.KASASWITCH",
    "SMART.TAPOPLUG",
    "SMART.TAPOSWITCH",
}
LIGHT_DEVICE_TYPES = {
    "IOT.SMARTBULB",
    "SMART.KASABULB",
    "SMART.TAPOBULB",
}

# Model prefixes for wall switches (as opposed to plug/outlet devices),
# used only to pick the right SwitchDeviceClass.
WALL_SWITCH_MODEL_PREFIXES = ("HS2", "KS2", "ES2", "S5", "TS2")

# Model prefixes known to have energy monitoring.
EMETER_MODEL_PREFIXES = ("HS110", "HS300", "KP115", "KP125", "EP25", "P110", "P115", "P304")

# Matter-certified TP-Link hardware (see docs/MATTER.md). Compared against
# the base model name with any "(XX)" region suffix stripped.
MATTER_NATIVE_MODELS = {
    "P110M",
    "P125M",
    "P400M",
    "KP125M",
    "S505",
    "S505D",
    "S515",
    "S515D",
    "L535E",
    "H100",
    "H110",
    "H200",
    "H500",
    "T100",
    "T110",
    "T310",
    "T315",
    "S200D",
    "RV20 MAX",
    "RV20 MAX PLUS",
    "RV30 MAX",
    "RV30 MAX PLUS",
    "RV50 PRO OMNI",
}


def base_model(device_model: str | None) -> str:
    """Strip the region suffix from a cloud deviceModel, e.g. 'P110(EU)'."""
    if not device_model:
        return ""
    return device_model.split("(")[0].strip().upper()
