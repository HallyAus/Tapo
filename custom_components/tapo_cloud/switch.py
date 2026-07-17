"""Switch platform: plugs, wall switches, and power-strip outlets."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SWITCH_DEVICE_TYPES, WALL_SWITCH_MODEL_PREFIXES
from .coordinator import CloudDevice, TapoCloudCoordinator
from .entity import TapoCloudEntity


def _relay_request(state: int, child_id: str | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {"system": {"set_relay_state": {"state": state}}}
    if child_id:
        request["context"] = {"child_ids": [child_id]}
    return request


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        new_entities: list[SwitchEntity] = []
        for device_id, device in (coordinator.data or {}).items():
            if device.device_type not in SWITCH_DEVICE_TYPES:
                continue
            # Power strips expose one switch per outlet, not a parent switch.
            is_strip = bool(device.children) or (
                device.sysinfo is not None
                and device.sysinfo.get("relay_state") is None
                and "children" in device.sysinfo
            )
            if device_id not in known and not is_strip:
                known.add(device_id)
                new_entities.append(TapoCloudSwitch(coordinator, device_id))
            for child in device.children:
                child_id = child.get("id")
                if not child_id:
                    continue
                child_key = f"{device_id}_{child_id}"
                if child_key not in known:
                    known.add(child_key)
                    new_entities.append(
                        TapoCloudChildSwitch(coordinator, device_id, child_id)
                    )
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class TapoCloudSwitch(TapoCloudEntity, SwitchEntity):
    """A single plug or wall switch controlled via the cloud."""

    _attr_name = None

    def __init__(self, coordinator: TapoCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = device_id
        device = self.device
        model = device.model.upper() if device else ""
        self._attr_device_class = (
            SwitchDeviceClass.SWITCH
            if model.startswith(WALL_SWITCH_MODEL_PREFIXES)
            else SwitchDeviceClass.OUTLET
        )

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.sysinfo is not None

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None or device.sysinfo is None:
            return None
        # Power strips report no top-level relay; expose children instead.
        relay_state = device.sysinfo.get("relay_state")
        if relay_state is None:
            return None
        return relay_state == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_state(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_state(0)

    async def _async_set_state(self, state: int) -> None:
        await self.coordinator.async_send_command(
            self._device_id, _relay_request(state)
        )
        device = self.device
        if device and device.sysinfo is not None:
            device.sysinfo["relay_state"] = state
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class TapoCloudChildSwitch(TapoCloudEntity, SwitchEntity):
    """One outlet of a multi-outlet power strip."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self, coordinator: TapoCloudCoordinator, device_id: str, child_id: str
    ) -> None:
        super().__init__(coordinator, device_id)
        self._child_id = child_id
        self._attr_unique_id = f"{device_id}_{child_id}"

    def _child(self) -> dict[str, Any] | None:
        device = self.device
        if device is None:
            return None
        for child in device.children:
            if child.get("id") == self._child_id:
                return child
        return None

    @property
    def name(self) -> str | None:
        child = self._child()
        return child.get("alias") if child else None

    @property
    def available(self) -> bool:
        return super().available and self._child() is not None

    @property
    def is_on(self) -> bool | None:
        child = self._child()
        if child is None or child.get("state") is None:
            return None
        return child["state"] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_state(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_state(0)

    async def _async_set_state(self, state: int) -> None:
        await self.coordinator.async_send_command(
            self._device_id, _relay_request(state, self._child_id)
        )
        child = self._child()
        if child is not None:
            child["state"] = state
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
