"""Async client for the TP-Link cloud V2 API (Kasa and Tapo clouds).

TP-Link runs two parallel cloud services for the same account:

  Kasa: https://n-wap.tplinkcloud.com     (appType Kasa_Android_Mix)
  Tapo: https://n-wap.i.tplinkcloud.com   (appType TP-Link_Tapo_Android)

Both use the same V2 protocol: every request is signed with HMAC-SHA1
using an app-level AccessKey/SecretKey pair, and device commands are
relayed to the device over its own cloud connection ("passthrough").

Because commands travel device->cloud, control keeps working even when
the device's local API is unreachable — e.g. after a firmware update
switched the device to the (still unsupported) TPAP local protocol.

Protocol details derived from the GPL-3.0 project
https://github.com/piekstra/tplink-cloud-api
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import ssl
import uuid
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

KASA_HOST = "https://n-wap.tplinkcloud.com"
TAPO_HOST = "https://n-wap.i.tplinkcloud.com"

KASA_APP_TYPE = "Kasa_Android_Mix"
TAPO_APP_TYPE = "TP-Link_Tapo_Android"
APP_VER = "3.4.451"

# App-level signing keys from the official Android apps. These identify
# the client application, not the user account.
KASA_ACCESS_KEY = "e37525375f8845999bcc56d5e6faa76d"
KASA_SECRET_KEY = "314bc6700b3140ca80bc655e527cb062"
TAPO_ACCESS_KEY = "4d11b6b9d5ea4d19a829adbb9714b057"
TAPO_SECRET_KEY = "6ed7d97f3e73467f8a5bab90b577ba4c"

# Both official apps sign with this fixed timestamp.
SIGNING_TIMESTAMP = "9999999999"

PATH_ACCOUNT_STATUS = "/api/v2/account/getAccountStatusAndUrl"
PATH_LOGIN = "/api/v2/account/login"
PATH_REFRESH = "/api/v2/account/refreshToken"
PATH_MFA_LOGIN = "/api/v2/account/checkMFACodeAndLogin"
PATH_TAPO_PASSTHROUGH = "/api/v2/common/passthrough"

ERR_MFA_REQUIRED = -20677
ERR_TOKEN_EXPIRED = -20651
ERR_REFRESH_TOKEN_EXPIRED = -20655
ERR_WRONG_CREDENTIALS = -20601
ERR_ACCOUNT_LOCKED = -20675

_CA_CHAIN = Path(__file__).parent / "certs" / "tplink-ca-chain.pem"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TPLinkCloudError(Exception):
    """Base error for cloud API failures."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class TPLinkAuthError(TPLinkCloudError):
    """Wrong credentials or locked account."""


class TPLinkMFARequiredError(TPLinkCloudError):
    """Login requires a multi-factor verification code."""

    def __init__(self, message: str, mfa_type: str | None = None) -> None:
        super().__init__(message, error_code=ERR_MFA_REQUIRED)
        self.mfa_type = mfa_type


class TPLinkTokenExpiredError(TPLinkCloudError):
    """Auth or refresh token has expired."""


def build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context trusting both public CAs and TP-Link's private CA.

    The n-*.tplinkcloud.com V2 endpoints present certificates issued by
    TP-Link's own CA, which is not in the system trust store. Blocking —
    call from an executor.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(_CA_CHAIN))
    return context


def _signing_headers(
    body_json: str, url_path: str, access_key: str, secret_key: str
) -> dict[str, str]:
    """Compute Content-MD5 and X-Authorization headers for a V2 request."""
    content_md5 = base64.b64encode(hashlib.md5(body_json.encode()).digest()).decode()
    nonce = str(uuid.uuid4())
    sig_string = f"{content_md5}\n{SIGNING_TIMESTAMP}\n{nonce}\n{url_path}"
    signature = hmac.new(
        secret_key.encode(), sig_string.encode(), hashlib.sha1
    ).hexdigest()
    return {
        "Content-MD5": content_md5,
        "X-Authorization": (
            f"Timestamp={SIGNING_TIMESTAMP}, Nonce={nonce}, "
            f"AccessKey={access_key}, Signature={signature}"
        ),
    }


class TPLinkCloud:
    """Client for one of the two TP-Link clouds ("kasa" or "tapo")."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ssl_context: ssl.SSLContext,
        cloud_type: str,
        term_id: str,
    ) -> None:
        self._session = session
        self._ssl = ssl_context
        self.cloud_type = cloud_type
        self._term_id = term_id

        if cloud_type == "tapo":
            self._access_key = TAPO_ACCESS_KEY
            self._secret_key = TAPO_SECRET_KEY
            self._app_type = TAPO_APP_TYPE
            self.host = TAPO_HOST
        else:
            self._access_key = KASA_ACCESS_KEY
            self._secret_key = KASA_SECRET_KEY
            self._app_type = KASA_APP_TYPE
            self.host = KASA_HOST

        self.token: str | None = None
        self.refresh_token: str | None = None

        self._query_params = {
            "appName": self._app_type,
            "appVer": APP_VER,
            "netType": "wifi",
            "termID": term_id,
            "ospf": "Android 14",
            "brand": "TPLINK",
            "locale": "en_US",
            "model": "Pixel",
            "termName": "Pixel",
            "termMeta": "Pixel",
        }
        self._headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; Pixel Build/UP1A)",
            "Content-Type": "application/json;charset=UTF-8",
        }

    async def _post(
        self,
        base_url: str,
        url_path: str,
        body: dict[str, Any],
        with_token: bool = True,
    ) -> dict[str, Any]:
        """POST a signed request and return the parsed JSON envelope."""
        body_json = json.dumps(body)
        params = dict(self._query_params)
        if with_token and self.token:
            params["token"] = self.token
        headers = {
            **self._headers,
            **_signing_headers(body_json, url_path, self._access_key, self._secret_key),
        }
        url = base_url if url_path == "/" else f"{base_url}{url_path}"
        try:
            async with self._session.post(
                url,
                data=body_json,
                params=params,
                headers=headers,
                ssl=self._ssl,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status != 200:
                    raise TPLinkCloudError(
                        f"HTTP {response.status} from {url_path}: {response.reason}"
                    )
                return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise TPLinkCloudError(f"Connection error calling {url_path}: {err}") from err

    async def _get_regional_url(self, username: str) -> str:
        body = {"appType": self._app_type, "cloudUserName": username}
        envelope = await self._post(self.host, PATH_ACCOUNT_STATUS, body, with_token=False)
        if envelope.get("error_code") == 0:
            return (envelope.get("result") or {}).get("appServerUrl", self.host)
        return self.host

    async def async_login(self, username: str, password: str) -> None:
        """Log in with account credentials.

        Raises TPLinkMFARequiredError when the account needs a
        verification code; complete the login with async_verify_mfa().
        """
        self.host = await self._get_regional_url(username)
        body = {
            "appType": self._app_type,
            "appVersion": APP_VER,
            "cloudPassword": password,
            "cloudUserName": username,
            "platform": "Android",
            "refreshTokenNeeded": True,
            "supportBindAccount": False,
            "terminalUUID": self._term_id,
            "terminalName": "Home Assistant",
            "terminalMeta": "Home Assistant",
        }
        envelope = await self._post(self.host, PATH_LOGIN, body, with_token=False)
        self._handle_login_result(envelope)

    async def async_verify_mfa(self, username: str, password: str, code: str) -> None:
        """Complete a login challenged with MFA."""
        body = {
            "appType": self._app_type,
            "cloudPassword": password,
            "cloudUserName": username,
            "code": code,
            "terminalUUID": self._term_id,
        }
        envelope = await self._post(self.host, PATH_MFA_LOGIN, body, with_token=False)
        error_code = envelope.get("error_code")
        if error_code != 0:
            raise TPLinkAuthError(
                envelope.get("msg") or f"MFA verification failed ({error_code})",
                error_code=error_code,
            )
        self._store_tokens(envelope.get("result") or {})

    def _handle_login_result(self, envelope: dict[str, Any]) -> None:
        error_code = envelope.get("error_code")
        result = envelope.get("result") or {}
        if error_code == 0:
            self._store_tokens(result)
            return
        if error_code == ERR_MFA_REQUIRED:
            raise TPLinkMFARequiredError(
                "MFA verification required", mfa_type=result.get("mfaType")
            )
        if error_code in (ERR_WRONG_CREDENTIALS, ERR_ACCOUNT_LOCKED):
            raise TPLinkAuthError(
                envelope.get("msg") or "Authentication failed", error_code=error_code
            )
        raise TPLinkCloudError(
            envelope.get("msg") or f"Login failed ({error_code})", error_code=error_code
        )

    def _store_tokens(self, result: dict[str, Any]) -> None:
        self.token = result.get("token")
        self.refresh_token = result.get("refreshToken") or self.refresh_token

    async def async_refresh_login(self) -> None:
        """Get a fresh auth token using the stored refresh token."""
        if not self.refresh_token:
            raise TPLinkTokenExpiredError("No refresh token available")
        body = {
            "appType": self._app_type,
            "refreshToken": self.refresh_token,
            "terminalUUID": self._term_id,
        }
        envelope = await self._post(self.host, PATH_REFRESH, body, with_token=False)
        error_code = envelope.get("error_code")
        if error_code == 0:
            self._store_tokens(envelope.get("result") or {})
            return
        if error_code == ERR_REFRESH_TOKEN_EXPIRED:
            self.refresh_token = None
            raise TPLinkTokenExpiredError(
                "Refresh token expired", error_code=error_code
            )
        raise TPLinkCloudError(
            envelope.get("msg") or f"Token refresh failed ({error_code})",
            error_code=error_code,
        )

    async def async_get_device_list(self) -> list[dict[str, Any]]:
        """Return the raw device list registered to this cloud."""
        envelope = await self._post(self.host, "/", {"method": "getDeviceList"})
        error_code = envelope.get("error_code")
        if error_code == 0:
            return (envelope.get("result") or {}).get("deviceList", [])
        if error_code == ERR_TOKEN_EXPIRED:
            raise TPLinkTokenExpiredError("Auth token expired", error_code=error_code)
        raise TPLinkCloudError(
            envelope.get("msg") or f"getDeviceList failed ({error_code})",
            error_code=error_code,
        )

    async def async_passthrough(
        self, app_server_url: str, device_id: str, request_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Relay a command to a device over its cloud connection."""
        if self.cloud_type == "tapo":
            body: dict[str, Any] = {
                "deviceId": device_id,
                "requestData": json.dumps(request_data),
            }
            envelope = await self._post(app_server_url, PATH_TAPO_PASSTHROUGH, body)
        else:
            body = {
                "method": "passthrough",
                "params": {
                    "deviceId": device_id,
                    "requestData": json.dumps(request_data),
                },
            }
            envelope = await self._post(app_server_url, "/", body)

        error_code = envelope.get("error_code")
        if error_code == ERR_TOKEN_EXPIRED:
            raise TPLinkTokenExpiredError("Auth token expired", error_code=error_code)
        if error_code != 0:
            raise TPLinkCloudError(
                envelope.get("msg") or f"passthrough failed ({error_code})",
                error_code=error_code,
            )
        response_data = (envelope.get("result") or {}).get("responseData")
        if isinstance(response_data, str):
            return json.loads(response_data)
        return response_data


class TPLinkCloudBridge:
    """Manages both clouds for one TP-Link account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ssl_context: ssl.SSLContext,
        username: str,
        password: str,
        term_id: str,
    ) -> None:
        self.username = username
        self._password = password
        self.kasa = TPLinkCloud(session, ssl_context, "kasa", term_id)
        self.tapo = TPLinkCloud(session, ssl_context, "tapo", term_id)
        self._lock = asyncio.Lock()

    def cloud_for(self, cloud_type: str) -> TPLinkCloud:
        return self.tapo if cloud_type == "tapo" else self.kasa

    async def _async_ensure_login(self, cloud: TPLinkCloud) -> None:
        """Make sure a cloud has a usable token (refresh first, then password)."""
        if cloud.token:
            return
        if cloud.refresh_token:
            try:
                await cloud.async_refresh_login()
                return
            except TPLinkTokenExpiredError:
                _LOGGER.debug(
                    "%s refresh token expired, falling back to password login",
                    cloud.cloud_type,
                )
        await cloud.async_login(self.username, self._password)

    async def _async_call(self, cloud: TPLinkCloud, coro_factory):
        """Run a cloud call, transparently re-authenticating once on expiry."""
        async with self._lock:
            await self._async_ensure_login(cloud)
        try:
            return await coro_factory()
        except TPLinkTokenExpiredError:
            async with self._lock:
                cloud.token = None
                await self._async_ensure_login(cloud)
            return await coro_factory()

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Merged device list from both clouds.

        Each device dict gains a "cloud_type" key. Devices present in both
        clouds keep the Kasa entry (V1 passthrough is the older, most
        battle-tested path).
        """
        devices: list[dict[str, Any]] = []
        try:
            kasa_devices = await self._async_call(
                self.kasa, lambda: self.kasa.async_get_device_list()
            )
            for device in kasa_devices:
                device["cloud_type"] = "kasa"
                devices.append(device)
        except (TPLinkAuthError, TPLinkMFARequiredError):
            raise
        except TPLinkCloudError as err:
            _LOGGER.warning("Kasa cloud device list failed: %s", err)

        try:
            tapo_devices = await self._async_call(
                self.tapo, lambda: self.tapo.async_get_device_list()
            )
            known_ids = {device.get("deviceId") for device in devices}
            for device in tapo_devices:
                if device.get("deviceId") not in known_ids:
                    device["cloud_type"] = "tapo"
                    devices.append(device)
        except (TPLinkAuthError, TPLinkMFARequiredError):
            # The Tapo cloud rejects accounts that have never used the Tapo
            # app; that must not break Kasa-only setups.
            if not devices:
                raise
            _LOGGER.debug("Tapo cloud login rejected; continuing with Kasa only")
        except TPLinkCloudError as err:
            _LOGGER.warning("Tapo cloud device list failed: %s", err)

        return devices

    async def async_device_request(
        self, device: dict[str, Any], request_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a passthrough command to a device from the merged list."""
        cloud = self.cloud_for(device.get("cloud_type", "kasa"))
        app_server_url = device.get("appServerUrl") or cloud.host
        device_id = device["deviceId"]
        return await self._async_call(
            cloud,
            lambda: cloud.async_passthrough(app_server_url, device_id, request_data),
        )
