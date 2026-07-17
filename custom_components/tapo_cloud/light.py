"""Light platform: Kasa and Tapo bulbs controlled via the cloud."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LIGHT_DEVICE_TYPES
from .coordinator import TapoCloudCoordinator
from .entity import TapoCloudEntity

LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"


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
            TapoCloudLight(coordinator, device_id)
            for device_id, device in (coordinator.data or {}).items()
            if device.device_type in LIGHT_DEVICE_TYPES and device_id not in known
        ]
        known.update(entity._device_id for entity in new_entities)
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class TapoCloudLight(TapoCloudEntity, LightEntity):
    """A smart bulb controlled via the cloud.

    Bulbs whose sysinfo exposes the Kasa lighting service (light_state)
    get brightness support; anything else falls back to plain on/off
    through the relay, which the cloud passthrough accepts for Tapo
    bulbs as well.
    """

    _attr_name = None

    def __init__(self, coordinator: TapoCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = device_id

    def _light_state(self) -> dict[str, Any] | None:
        device = self.device
        if device is None or device.sysinfo is None:
            return None
        light_state = device.sysinfo.get("light_state")
        if not isinstance(light_state, dict):
            return None
        # When off, current settings live under dft_on_state.
        if not light_state.get("on_off") and "dft_on_state" in light_state:
            return {"on_off": 0, **light_state["dft_on_state"]}
        return light_state

    def _dimmable(self) -> bool:
        device = self.device
        return bool(
            device
            and device.sysinfo
            and device.sysinfo.get("is_dimmable")
            and self._light_state() is not None
        )

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {ColorMode.BRIGHTNESS} if self._dimmable() else {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.BRIGHTNESS if self._dimmable() else ColorMode.ONOFF

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.sysinfo is not None

    @property
    def is_on(self) -> bool | None:
        light_state = self._light_state()
        if light_state is not None:
            return light_state.get("on_off") == 1
        device = self.device
        if device and device.sysinfo is not None:
            relay_state = device.sysinfo.get("relay_state")
            if relay_state is not None:
                return relay_state == 1
        return None

    @property
    def brightness(self) -> int | None:
        light_state = self._light_state()
        if light_state is None or light_state.get("brightness") is None:
            return None
        return round(light_state["brightness"] * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._light_state() is not None:
            state: dict[str, Any] = {"on_off": 1, "ignore_default": 1}
            if ATTR_BRIGHTNESS in kwargs and self._dimmable():
                state["brightness"] = max(
                    1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
                )
            request = {LIGHT_SERVICE: {"transition_light_state": state}}
        else:
            request = {"system": {"set_relay_state": {"state": 1}}}
        await self.coordinator.async_send_command(self._device_id, request)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._light_state() is not None:
            request: dict[str, Any] = {
                LIGHT_SERVICE: {"transition_light_state": {"on_off": 0}}
            }
        else:
            request = {"system": {"set_relay_state": {"state": 0}}}
        await self.coordinator.async_send_command(self._device_id, request)
        await self.coordinator.async_request_refresh()
