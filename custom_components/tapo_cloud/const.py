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
