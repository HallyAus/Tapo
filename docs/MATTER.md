# Matter migration guide

Matter is the long-term escape hatch from TP-Link's protocol churn: Home
Assistant's built-in [Matter integration](https://www.home-assistant.io/integrations/matter/)
controls devices **fully locally**, using an open standard TP-Link cannot
switch off with a firmware update. A Matter device is immune to the whole
TPAP/KLAP situation by design.

## The hard truth about firmware

**TP-Link does not add Matter to existing non-Matter devices via firmware
update, and third parties can't either** (firmware images are signed).
Owners of legacy HS200 switches and P100/P105/P110 plugs have been asking
TP-Link for Matter firmware for years with no result — see the
[HS200 Matter request thread](https://community.tp-link.com/en/smart-home/forum/topic/621772).
Matter support only ships in hardware sold with it: the "M"-suffixed models
and most newer product lines.

What TP-Link *does* ship via firmware update is **improvements to devices
that already have Matter** — e.g. the P110M gained
[energy monitoring over Matter](https://www.tp-link.com/au/press/news/21871/)
by firmware update, and monthly firmware rounds include Matter performance
fixes. So the migration path is hardware replacement, not a flash.

## Matter-certified TP-Link models (mid-2026)

Authoritative, always-current list: **<https://www.tp-link.com/us/matter/product-list/>**

| Category | Models | Replaces |
|---|---|---|
| Smart plugs | Tapo **P110M**, **P125M**, **P400M**; Kasa **KP125M** | P100/P105/P110/P115, KP115/KP125, HS103/HS105 |
| Wall switches | Tapo **S505**, **S505D** (dimmer), **S515**, **S515D** | Kasa HS200/HS210/HS220, KS2xx |
| Bulbs | Tapo **L535E** (v3) | L510/L530, KL series |
| Hubs | Tapo **H100**, **H110**, **H200**, **H500** (bridge child sensors/buttons into Matter) | KH100 |
| Sensors (via hub bridge) | T100, T110, T310, T315, S200D | — |
| Robot vacuums | RV20 Max (Plus), RV30 Max (Plus), RV50 Pro Omni | — |

Notes:

- These are **Wi-Fi Matter** devices — no Thread border router needed.
- Feature coverage over Matter varies by ecosystem (some features remain
  app-only): see [TP-Link's feature matrix](https://www.tapo.com/us/faq/351/).
  On/off, dimming, and (on P110M/P125M) energy monitoring work in Home
  Assistant's Matter integration.
- Wall switches: check the neutral-wire requirement for your wiring before
  buying (model pages list it).
- A device can be commissioned to Matter **and** stay paired to the Tapo app
  at the same time (multi-admin), so migrating doesn't break the app.

## Suggested migration strategy

1. **Don't replace anything that still works.** Devices controlled by this
   integration (cloud) or the core `tplink` integration (local) can stay.
2. **Replace on failure/lockout with the M-variant** from the table above,
   and commission it straight into Home Assistant Matter (Settings → Devices
   & Services → Add Integration → Matter, scan the QR code).
3. **Automations survive** if you keep entity IDs: after adding the Matter
   replacement, rename its entity to the old device's entity ID.
4. For wall switches with automations attached, batch-replace per room to
   keep rewiring sessions short.

## Checking your inventory

Every device this integration discovers exposes a **Cloud connection**
sensor whose attributes include the exact model. Devices flagged with
`matter_capable: true` are already Matter hardware — commission them into
the HA Matter integration for local control and keep this cloud bridge as
backup. Everything else needs a hardware swap to get Matter.

## Sources

- [TP-Link Matter-certified product list](https://www.tp-link.com/us/matter/product-list/)
- [Features supported over Matter per ecosystem](https://www.tapo.com/us/faq/351/)
- [P110M energy monitoring via Matter firmware update](https://www.tp-link.com/au/press/news/21871/)
- [KP125M announcement](https://community.tp-link.com/en/smart-home/forum/topic/607264)
- [HS200 Matter request (unanswered)](https://community.tp-link.com/en/smart-home/forum/topic/621772)
- [Tapo robot vacuum Matter FAQ](https://www.tp-link.com/us/support/faq/4395/)
