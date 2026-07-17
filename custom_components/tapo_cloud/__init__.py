"""Tapo & Kasa Cloud Bridge.

Controls TP-Link Tapo and Kasa devices through TP-Link's cloud — the
same channel the official apps use — so devices keep working in Home
Assistant even after firmware updates (e.g. the TPAP local-protocol
rollout) break local control.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TPLinkCloudBridge, build_ssl_context
from .const import (
    CONF_KASA_HOST,
    CONF_KASA_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TAPO_HOST,
    CONF_TAPO_REFRESH_TOKEN,
    CONF_TERM_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TapoCloudCoordinator

_SSL_CONTEXT_KEY = "ssl_context"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TP-Link account from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    if _SSL_CONTEXT_KEY not in domain_data:
        domain_data[_SSL_CONTEXT_KEY] = await hass.async_add_executor_job(
            build_ssl_context
        )

    bridge = TPLinkCloudBridge(
        async_get_clientsession(hass),
        domain_data[_SSL_CONTEXT_KEY],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_TERM_ID],
    )
    # Resume with the regional hosts and refresh tokens from the last
    # session, so restarts don't need a password login (or MFA).
    if entry.data.get(CONF_KASA_HOST):
        bridge.kasa.host = entry.data[CONF_KASA_HOST]
    if entry.data.get(CONF_TAPO_HOST):
        bridge.tapo.host = entry.data[CONF_TAPO_HOST]
    bridge.kasa.refresh_token = entry.data.get(CONF_KASA_REFRESH_TOKEN)
    bridge.tapo.refresh_token = entry.data.get(CONF_TAPO_REFRESH_TOKEN)

    coordinator = TapoCloudCoordinator(
        hass,
        entry,
        bridge,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    domain_data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
