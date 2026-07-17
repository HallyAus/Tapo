"""Data update coordinator polling device state through the TP-Link cloud."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TPLinkAuthError,
    TPLinkCloudBridge,
    TPLinkCloudError,
    TPLinkMFARequiredError,
)
from .discovery import LocalInfo, async_probe_local, normalize_mac
from .const import (
    CONF_KASA_HOST,
    CONF_KASA_REFRESH_TOKEN,
    CONF_LOCAL_PROBE,
    CONF_TAPO_HOST,
    CONF_TAPO_REFRESH_TOKEN,
    DEFAULT_LOCAL_PROBE,
    DOMAIN,
    EMETER_MODEL_PREFIXES,
    EVENT_DEVICE_OFFLINE,
    EVENT_DEVICE_ONLINE,
    STATUS_ONLINE,
)

_LOGGER = logging.getLogger(__name__)

# Limit concurrent cloud requests per refresh cycle.
_MAX_CONCURRENCY = 6

SYSINFO_REQUEST = {"system": {"get_sysinfo": None}}
EMETER_REQUEST = {"emeter": {"get_realtime": {}}}


@dataclass
class CloudDevice:
    """State snapshot for one cloud device."""

    info: dict[str, Any]
    sysinfo: dict[str, Any] | None = None
    emeter: dict[str, Any] | None = None
    emeter_supported: bool | None = None
    local: LocalInfo | None = None

    @property
    def device_id(self) -> str:
        return self.info["deviceId"]

    @property
    def alias(self) -> str:
        # Device-list alias can lag behind; sysinfo alias is authoritative.
        if self.sysinfo and self.sysinfo.get("alias"):
            return self.sysinfo["alias"]
        return self.info.get("alias") or self.info.get("deviceName") or self.device_id

    @property
    def model(self) -> str:
        return self.info.get("deviceModel") or "Unknown"

    @property
    def device_type(self) -> str:
        return self.info.get("deviceType") or ""

    @property
    def online(self) -> bool:
        return self.info.get("status") == STATUS_ONLINE

    @property
    def children(self) -> list[dict[str, Any]]:
        if self.sysinfo:
            return self.sysinfo.get("children") or []
        return []


def _normalize_emeter(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize emeter get_realtime fields across firmware generations.

    Older firmware reports base units (power, voltage, current, total);
    newer firmware reports milli-units (power_mw, voltage_mv, ...).
    """
    normalized: dict[str, Any] = {}
    conversions = (
        ("power", "power_mw", 1000),
        ("voltage", "voltage_mv", 1000),
        ("current", "current_ma", 1000),
        ("total", "total_wh", 1000),
    )
    for base_key, milli_key, factor in conversions:
        if raw.get(milli_key) is not None:
            normalized[base_key] = raw[milli_key] / factor
        elif raw.get(base_key) is not None:
            normalized[base_key] = raw[base_key]
    return normalized


class TapoCloudCoordinator(DataUpdateCoordinator[dict[str, CloudDevice]]):
    """Polls the TP-Link cloud for device presence and state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        bridge: TPLinkCloudBridge,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.bridge = bridge
        self._emeter_support: dict[str, bool] = {}

    async def _async_update_data(self) -> dict[str, CloudDevice]:
        probe_enabled = self.entry.options.get(CONF_LOCAL_PROBE, DEFAULT_LOCAL_PROBE)
        probe_task = (
            asyncio.create_task(async_probe_local()) if probe_enabled else None
        )
        try:
            raw_devices = await self.bridge.async_get_devices()
        except (TPLinkAuthError, TPLinkMFARequiredError) as err:
            if probe_task:
                probe_task.cancel()
            raise ConfigEntryAuthFailed(str(err)) from err
        except TPLinkCloudError as err:
            if probe_task:
                probe_task.cancel()
            raise UpdateFailed(f"TP-Link cloud unreachable: {err}") from err

        devices = {
            raw["deviceId"]: CloudDevice(info=raw)
            for raw in raw_devices
            if raw.get("deviceId")
        }

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def fetch_state(device: CloudDevice) -> None:
            if not device.online:
                return
            async with semaphore:
                try:
                    response = await self.bridge.async_device_request(
                        device.info, SYSINFO_REQUEST
                    )
                except TPLinkCloudError as err:
                    _LOGGER.debug(
                        "get_sysinfo failed for %s (%s): %s",
                        device.alias,
                        device.model,
                        err,
                    )
                    return
                if response:
                    device.sysinfo = (response.get("system") or {}).get("get_sysinfo")
                await self._async_fetch_emeter(device)

        await asyncio.gather(*(fetch_state(device) for device in devices.values()))

        if probe_task:
            try:
                local_results = await probe_task
            except Exception:  # noqa: BLE001 — probe is strictly best-effort
                local_results = {}
            for device in devices.values():
                mac = normalize_mac(device.info.get("deviceMac"))
                if mac and mac in local_results:
                    device.local = local_results[mac]

        self._fire_presence_events(devices)
        self._persist_refresh_tokens()
        return devices

    async def _async_fetch_emeter(self, device: CloudDevice) -> None:
        """Fetch energy readings for devices that support them.

        Support is probed once per device: known energy-monitoring models,
        or a sysinfo feature string containing ENE.
        """
        device_id = device.device_id
        supported = self._emeter_support.get(device_id)
        if supported is None:
            feature = (device.sysinfo or {}).get("feature") or ""
            supported = "ENE" in feature or device.model.upper().startswith(
                EMETER_MODEL_PREFIXES
            )
        if not supported:
            device.emeter_supported = False
            return
        try:
            response = await self.bridge.async_device_request(
                device.info, EMETER_REQUEST
            )
        except TPLinkCloudError:
            response = None
        realtime = ((response or {}).get("emeter") or {}).get("get_realtime")
        if realtime and realtime.get("err_code", 0) == 0:
            device.emeter = _normalize_emeter(realtime)
            device.emeter_supported = True
            self._emeter_support[device_id] = True
        elif self._emeter_support.get(device_id):
            # Previously worked: keep the entity, report unknown this cycle.
            device.emeter_supported = True
        else:
            device.emeter_supported = False
            self._emeter_support[device_id] = False

    def _fire_presence_events(self, devices: dict[str, CloudDevice]) -> None:
        """Fire events when devices join or drop off the TP-Link cloud."""
        if not self.data:
            return
        for device_id, device in devices.items():
            previous = self.data.get(device_id)
            if previous is None or previous.online == device.online:
                continue
            event = EVENT_DEVICE_ONLINE if device.online else EVENT_DEVICE_OFFLINE
            self.hass.bus.async_fire(
                event,
                {
                    "device_id": device_id,
                    "alias": device.alias,
                    "model": device.model,
                    "cloud_type": device.info.get("cloud_type"),
                },
            )
            _LOGGER.info(
                "%s (%s) went %s on the TP-Link cloud",
                device.alias,
                device.model,
                "online" if device.online else "offline",
            )

    def _persist_refresh_tokens(self) -> None:
        """Keep rotated refresh tokens and regional hosts in the config entry."""
        updates: dict[str, Any] = {}
        stored = self.entry.data
        current = {
            CONF_KASA_REFRESH_TOKEN: self.bridge.kasa.refresh_token,
            CONF_TAPO_REFRESH_TOKEN: self.bridge.tapo.refresh_token,
            CONF_KASA_HOST: self.bridge.kasa.host,
            CONF_TAPO_HOST: self.bridge.tapo.host,
        }
        for key, value in current.items():
            if value and value != stored.get(key):
                updates[key] = value
        if updates:
            self.hass.config_entries.async_update_entry(
                self.entry, data={**stored, **updates}
            )

    async def async_send_command(
        self, device_id: str, request_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a command to a device and schedule a state refresh."""
        device = (self.data or {}).get(device_id)
        if device is None:
            raise UpdateFailed(f"Unknown device {device_id}")
        try:
            response = await self.bridge.async_device_request(
                device.info, request_data
            )
        except (TPLinkAuthError, TPLinkMFARequiredError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        return response
