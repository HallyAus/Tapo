# Tapo & Kasa Cloud Bridge for Home Assistant

A [HACS](https://hacs.xyz) custom integration that controls **TP-Link Tapo and Kasa devices through TP-Link's cloud** — the same channel the official apps use.

## Why this exists

TP-Link has been rolling out firmware updates that switch devices to a new local protocol called **TPAP** (SPAKE2+ handshake over TLS on port 4433, with device attestation certificates). The [python-kasa library](https://github.com/python-kasa/python-kasa/issues/1590) that Home Assistant's built-in TP-Link integration relies on **does not support TPAP**, and the [work to add it](https://github.com/python-kasa/python-kasa/pull/1592) is blocked on TP-Link's certificate infrastructure. When a device updates, it silently drops out of Home Assistant:

> `Unsupported device ... with encrypt_scheme EncryptionScheme(is_support_https=True, encrypt_type='TPAP', http_port=4433, lv=2)`

This has hit P100/P105/P110 plugs, P300 strips, wall switches, KH100 hubs, and more — and it will eventually reach every Tapo/Kasa device as firmware rolls out.

**The device still works from the Tapo app** because the app talks to the device through TP-Link's cloud. This integration uses that same cloud channel, so:

- ✅ Works on devices locked to TPAP firmware — no downgrade needed
- ✅ Works for both **Tapo** and **Kasa** devices under one account
- ✅ No local network access to the device required at all
- ⚠️ It is **cloud polling** — it needs internet, and state updates are polled (default every 60 s), not instant

## What you get

| Device type | Entities |
|---|---|
| Smart plugs & wall switches (P100/P105/P110/P115, HS1xx, HS2xx, KP1xx, KS2xx, …) | Switch |
| Power strips (HS300, KP303, KP400, EP40, …) | One switch per outlet |
| Bulbs (L510/L530, KL series, …) | Light (brightness, color, and color temperature where supported) |
| Energy-monitoring devices (P110/P115, HS110, KP115/KP125, …) | Power, voltage, current, total energy sensors |
| **Every device on the account** (incl. hubs, cameras, vacuums) | Cloud connectivity binary sensor |

The integration also fires `tapo_cloud_device_offline` / `tapo_cloud_device_online` events on the Home Assistant event bus when a device drops off or rejoins the TP-Link cloud, so you can build automations that alert you the moment a firmware update knocks something out.

Each cloud-connectivity sensor exposes a `matter_capable` attribute flagging devices whose hardware is Matter-certified — those can be commissioned into Home Assistant's fully local Matter integration instead. See the [Matter migration guide](docs/MATTER.md) for the long-term exit strategy from TP-Link's protocol churn.

### Local protocol detection

On every poll the integration also broadcasts TP-Link's discovery packets on your LAN (toggleable in options) and reports each device's **local** protocol as sensor attributes:

- `local_protocol`: `iot` (legacy, fully local-capable), `klap`/`aes` (local-capable via the core `tplink` integration), or `tpap` (locked out of local control)
- `tpap_locked`: `true` when the device can **only** be reached through the cloud — i.e. exactly the devices this integration exists for
- `locally_controllable`: `true` when you could (also) use Home Assistant's built-in TP-Link integration for instant local control

This gives you a live inventory of which devices the TPAP rollout has claimed so far.

## Installation

### Via HACS (recommended)

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/HallyAus/Tapo` with category **Integration**.
3. Install **Tapo & Kasa Cloud Bridge** and restart Home Assistant.

### Manual

Copy `custom_components/tapo_cloud` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration** and search for **Tapo & Kasa Cloud Bridge**.
2. Sign in with your TP-Link account (the one you use in the Tapo/Kasa app).
3. If your account has two-step verification, you'll be prompted for the code TP-Link emails you — once per cloud (Kasa and Tapo are separate clouds behind the same account).

All devices registered to the account are discovered automatically. The polling interval is adjustable under the integration's **Configure** option (15–600 seconds).

## How it works

TP-Link runs two parallel clouds for the same account:

| | Kasa cloud | Tapo cloud |
|---|---|---|
| Endpoint | `n-wap.tplinkcloud.com` | `n-wap.i.tplinkcloud.com` |
| Passthrough | V1 `{"method":"passthrough"}` on `/` | V2 `POST /api/v2/common/passthrough` |

Every request is HMAC-SHA1-signed with app-level keys (the same signing the official Android apps perform), and commands are relayed to the device over the device's own persistent cloud connection. Since the device authenticates *outward* to the cloud, the local TPAP lockout is irrelevant.

The cloud endpoints present certificates from TP-Link's private CA, which is bundled with the integration.

Protocol details were derived from the excellent GPL-3.0 [piekstra/tplink-cloud-api](https://github.com/piekstra/tplink-cloud-api) project.

## Recommendations alongside this integration

- **Keep local control where you still can:** for devices not yet on TPAP firmware, the built-in TP-Link integration (local, instant) remains better. Use this integration for the devices that have been locked out, and as the safety net for the rest.
- **Enable "Third-Party Compatibility"** in the Tapo app (Device → Settings) for every device that offers it — on many firmwares this re-enables the KLAP local protocol that Home Assistant supports natively.
- **Disable auto-update** in the Tapo/Kasa app for devices that still work locally.
- Watch [python-kasa#1590](https://github.com/python-kasa/python-kasa/issues/1590) — if native TPAP support lands upstream, local control returns via the core integration.

## Limitations

- Cloud polling: state changes made outside HA can take up to one polling interval to appear.
- Requires an internet connection and TP-Link's cloud to be up.
- Bulb color/color-temperature support depends on the device exposing the Kasa lighting service through the cloud; Tapo bulbs may be limited to on/off.
- Hubs, sensors, cameras, and vacuums are presence-only (connectivity sensor, no control).
- TP-Link could change the cloud API at any time; this is an unofficial client.

## Credits & license

- Cloud protocol: [piekstra/tplink-cloud-api](https://github.com/piekstra/tplink-cloud-api) (GPL-3.0)
- TPAP tracking: [python-kasa/python-kasa#1590](https://github.com/python-kasa/python-kasa/issues/1590)

This project is licensed under the [GPL-3.0](LICENSE).

*This is an unofficial project, not affiliated with TP-Link. Tapo and Kasa are trademarks of TP-Link Corporation.*
