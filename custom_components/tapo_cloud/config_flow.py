"""Config flow for Tapo & Kasa Cloud Bridge."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    TPLinkAuthError,
    TPLinkCloudBridge,
    TPLinkCloudError,
    TPLinkMFARequiredError,
    build_ssl_context,
)
from .const import (
    CONF_KASA_HOST,
    CONF_KASA_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TAPO_HOST,
    CONF_TAPO_REFRESH_TOKEN,
    CONF_TERM_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
MFA_SCHEMA = vol.Schema({vol.Required("code"): str})

# Login progress states per cloud.
_PENDING = "pending"
_OK = "ok"
_NEEDS_MFA = "mfa"
_AUTH_FAILED = "auth_failed"
_UNREACHABLE = "unreachable"


class TapoCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow, including per-cloud MFA challenges."""

    VERSION = 1

    def __init__(self) -> None:
        self._bridge: TPLinkCloudBridge | None = None
        self._username: str = ""
        self._password: str = ""
        self._term_id: str = ""
        self._cloud_states: dict[str, str] = {}
        self._mfa_cloud: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input[CONF_PASSWORD]

            if self._reauth_entry is None:
                await self.async_set_unique_id(self._username.lower())
                self._abort_if_unique_id_configured()
                self._term_id = str(uuid.uuid4())
            else:
                self._term_id = self._reauth_entry.data.get(
                    CONF_TERM_ID, str(uuid.uuid4())
                )

            await self._async_create_bridge()
            self._cloud_states = {"kasa": _PENDING, "tapo": _PENDING}
            result = await self._async_advance()
            if result is not None:
                return result
            errors["base"] = self._login_error()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_USERNAME: self._username}
            ),
            errors=errors,
        )

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the verification code TP-Link sent for one cloud."""
        assert self._bridge is not None and self._mfa_cloud is not None
        errors: dict[str, str] = {}
        cloud = self._bridge.cloud_for(self._mfa_cloud)

        if user_input is not None:
            try:
                await cloud.async_verify_mfa(
                    self._username, self._password, user_input["code"].strip()
                )
                self._cloud_states[self._mfa_cloud] = _OK
                self._mfa_cloud = None
            except TPLinkAuthError:
                errors["base"] = "invalid_mfa_code"
            except TPLinkCloudError:
                errors["base"] = "cannot_connect"
            if not errors:
                result = await self._async_advance()
                if result is not None:
                    return result
                return self.async_show_form(
                    step_id="user", data_schema=USER_SCHEMA,
                    errors={"base": self._login_error()},
                )

        return self.async_show_form(
            step_id="mfa",
            data_schema=MFA_SCHEMA,
            errors=errors,
            description_placeholders={
                "cloud": "Tapo" if self._mfa_cloud == "tapo" else "Kasa",
                "username": self._username,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        self._username = entry_data.get(CONF_USERNAME, "")
        return await self.async_step_user()

    async def _async_create_bridge(self) -> None:
        ssl_context = await self.hass.async_add_executor_job(build_ssl_context)
        self._bridge = TPLinkCloudBridge(
            async_get_clientsession(self.hass),
            ssl_context,
            self._username,
            self._password,
            self._term_id,
        )

    async def _async_advance(self) -> ConfigFlowResult | None:
        """Drive both cloud logins forward; return the next flow step.

        Returns None when the flow cannot complete (all logins failed) so
        the caller can re-render the user form with an error.
        """
        assert self._bridge is not None
        for cloud_type in ("kasa", "tapo"):
            if self._cloud_states[cloud_type] != _PENDING:
                continue
            cloud = self._bridge.cloud_for(cloud_type)
            try:
                await cloud.async_login(self._username, self._password)
                self._cloud_states[cloud_type] = _OK
            except TPLinkMFARequiredError:
                self._cloud_states[cloud_type] = _NEEDS_MFA
                self._mfa_cloud = cloud_type
                return await self.async_step_mfa()
            except TPLinkAuthError:
                self._cloud_states[cloud_type] = _AUTH_FAILED
            except TPLinkCloudError as err:
                _LOGGER.warning("%s cloud login failed: %s", cloud_type, err)
                self._cloud_states[cloud_type] = _UNREACHABLE

        if _OK not in self._cloud_states.values():
            return None
        return self._finish()

    def _login_error(self) -> str:
        states = set(self._cloud_states.values())
        if _AUTH_FAILED in states:
            return "invalid_auth"
        return "cannot_connect"

    def _finish(self) -> ConfigFlowResult:
        assert self._bridge is not None
        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_TERM_ID: self._term_id,
            CONF_KASA_REFRESH_TOKEN: self._bridge.kasa.refresh_token,
            CONF_TAPO_REFRESH_TOKEN: self._bridge.tapo.refresh_token,
            CONF_KASA_HOST: self._bridge.kasa.host,
            CONF_TAPO_HOST: self._bridge.tapo.host,
        }
        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry, data=data
            )
        return self.async_create_entry(title=self._username, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TapoCloudOptionsFlow()


class TapoCloudOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
