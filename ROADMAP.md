# Roadmap

## Now (done)

- [x] v1.0.0 — Cloud bridge integration: control Tapo/Kasa devices through
  TP-Link's cloud, working around the TPAP local-protocol lockout.

## Next

- [ ] **Matter migration path** *(requested — investigate separately)*
  - Matter is the long-term fix: Home Assistant's Matter integration is fully
    local and immune to TP-Link protocol changes (TPAP, KLAP, or whatever
    comes next).
  - Firmware cannot be modified by third parties (signed by TP-Link), so
    Matter can only arrive via official TP-Link firmware. Investigate:
    - Which owned models have received **official Matter firmware** from
      TP-Link, per region (TP-Link has shipped Matter updates for select
      Tapo/Kasa models; availability differs by hardware revision).
    - Audit the device inventory exposed by this integration (model + hwVer +
      fwVer are in each device's diagnostics/connectivity sensor attributes)
      against TP-Link's Matter compatibility list.
    - Replacement guidance: Matter-native variants (e.g. P110M/P125M plugs,
      S505/S506 switches) as devices are retired.
    - Optional: a repair/notification in this integration flagging devices
      that have a known Matter firmware available.
  - Alternative for flash-friendly hardware: ESPHome/LibreTiny conversion for
    older ESP- or Realtek-based plugs (local control, not Matter).

## Later / ideas

- [ ] Color and color-temperature support for bulbs.
- [ ] Tapo hub (KH100) child devices (TRVs, sensors) via cloud.
- [ ] Per-device "TPAP-locked" detection by probing local discovery, to show
      which devices still support local control (and could be moved back to
      the core integration).
- [ ] Publish to the HACS default repository list.
