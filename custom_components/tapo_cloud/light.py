"""Light platform: Kasa and Tapo bulbs controlled via the cloud."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LIGHT_DEVICE_TYPES, base_model
from .coordinator import TapoCloudCoordinator
from .entity import TapoCloudEntity

LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"

DEFAULT_MIN_KELVIN = 2500
DEFAULT_MAX_KELVIN = 6500
# Models with a wider tunable-white range than the default.
WIDE_KELVIN_MODEL_PREFIXES = ("KL130", "KL135", "LB130", "LB230")
WIDE_MAX_KELVIN = 9000


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
    get brightness/color/color-temperature support according to their
    capability flags; anything else falls back to plain on/off through
    the relay, which the cloud passthrough accepts for Tapo bulbs too.
    """

    _attr_name = None

    def __init__(self, coordinator: TapoCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = device_id

    # ---- capability helpers -------------------------------------------------

    def _sysinfo(self) -> dict[str, Any] | None:
        device = self.device
        return device.sysinfo if device else None

    def _light_state(self) -> dict[str, Any] | None:
        sysinfo = self._sysinfo()
        if sysinfo is None:
            return None
        light_state = sysinfo.get("light_state")
        if not isinstance(light_state, dict):
            return None
        # When off, current settings live under dft_on_state.
        if not light_state.get("on_off") and "dft_on_state" in light_state:
            return {"on_off": 0, **light_state["dft_on_state"]}
        return light_state

    def _has_capability(self, flag: str) -> bool:
        sysinfo = self._sysinfo() or {}
        return bool(sysinfo.get(flag)) and self._light_state() is not None

    # ---- HA light properties ------------------------------------------------

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        if self._has_capability("is_color"):
            modes.add(ColorMode.HS)
        if self._has_capability("is_variable_color_temp"):
            modes.add(ColorMode.COLOR_TEMP)
        if modes:
            return modes
        if self._has_capability("is_dimmable"):
            return {ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        modes = self.supported_color_modes
        light_state = self._light_state() or {}
        if ColorMode.COLOR_TEMP in modes and (light_state.get("color_temp") or 0) > 0:
            return ColorMode.COLOR_TEMP
        if ColorMode.HS in modes:
            return ColorMode.HS
        if ColorMode.COLOR_TEMP in modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def supported_features(self) -> LightEntityFeature:
        if self._light_state() is not None:
            return LightEntityFeature.TRANSITION
        return LightEntityFeature(0)

    @property
    def min_color_temp_kelvin(self) -> int:
        return DEFAULT_MIN_KELVIN

    @property
    def max_color_temp_kelvin(self) -> int:
        device = self.device
        if device and base_model(device.model).startswith(WIDE_KELVIN_MODEL_PREFIXES):
            return WIDE_MAX_KELVIN
        return DEFAULT_MAX_KELVIN

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.sysinfo is not None

    @property
    def is_on(self) -> bool | None:
        light_state = self._light_state()
        if light_state is not None:
            return light_state.get("on_off") == 1
        sysinfo = self._sysinfo()
        if sysinfo is not None and sysinfo.get("relay_state") is not None:
            return sysinfo["relay_state"] == 1
        return None

    @property
    def brightness(self) -> int | None:
        light_state = self._light_state()
        if light_state is None or light_state.get("brightness") is None:
            return None
        return round(light_state["brightness"] * 255 / 100)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        light_state = self._light_state()
        if light_state is None or not self._has_capability("is_color"):
            return None
        hue = light_state.get("hue")
        saturation = light_state.get("saturation")
        if hue is None or saturation is None:
            return None
        return (float(hue), float(saturation))

    @property
    def color_temp_kelvin(self) -> int | None:
        light_state = self._light_state()
        if light_state is None:
            return None
        color_temp = light_state.get("color_temp") or 0
        return color_temp if color_temp > 0 else None

    # ---- commands -----------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._light_state() is not None:
            state: dict[str, Any] = {"on_off": 1, "ignore_default": 1}
            if ATTR_TRANSITION in kwargs:
                state["transition_period"] = int(kwargs[ATTR_TRANSITION] * 1000)
            if ATTR_BRIGHTNESS in kwargs and self._has_capability("is_dimmable"):
                state["brightness"] = max(
                    1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
                )
            if ATTR_HS_COLOR in kwargs and self._has_capability("is_color"):
                hue, saturation = kwargs[ATTR_HS_COLOR]
                state["hue"] = int(hue)
                state["saturation"] = int(saturation)
                state["color_temp"] = 0
            elif ATTR_COLOR_TEMP_KELVIN in kwargs and self._has_capability(
                "is_variable_color_temp"
            ):
                state["color_temp"] = min(
                    self.max_color_temp_kelvin,
                    max(self.min_color_temp_kelvin, kwargs[ATTR_COLOR_TEMP_KELVIN]),
                )
            request = {LIGHT_SERVICE: {"transition_light_state": state}}
        else:
            request = {"system": {"set_relay_state": {"state": 1}}}
        await self.coordinator.async_send_command(self._device_id, request)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._light_state() is not None:
            state: dict[str, Any] = {"on_off": 0}
            if ATTR_TRANSITION in kwargs:
                state["transition_period"] = int(kwargs[ATTR_TRANSITION] * 1000)
            request: dict[str, Any] = {
                LIGHT_SERVICE: {"transition_light_state": state}
            }
        else:
            request = {"system": {"set_relay_state": {"state": 0}}}
        await self.coordinator.async_send_command(self._device_id, request)
        await self.coordinator.async_request_refresh()
