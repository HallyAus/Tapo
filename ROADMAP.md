# Roadmap

## Now (done)

- [x] v1.0.0 — Cloud bridge integration: control Tapo/Kasa devices through
  TP-Link's cloud, working around the TPAP local-protocol lockout.

## Next

- [x] **Matter migration path** — researched; see [docs/MATTER.md](docs/MATTER.md).
  Outcome: TP-Link does not ship Matter to legacy hardware via firmware
  (images are signed; HS200/P110 requests have gone unanswered for years).
  Migration = hardware replacement with Matter-certified models (P110M,
  P125M, KP125M, S505/S515, L535E, H100/H200 hubs). The connectivity
  sensor now exposes a `matter_capable` attribute per device.
  - [ ] Optional follow-up: repair issue/notification for devices whose
        Matter-capable hardware is not yet commissioned into HA Matter.
  - [ ] Optional: ESPHome/LibreTiny conversion notes for flash-friendly
        legacy plugs (local control, not Matter).

## Later / ideas

- [x] Color and color-temperature support for bulbs (v1.1.0), including
      transitions, for bulbs exposing the lighting service via the cloud.
- [ ] Tapo hub (KH100) child devices (TRVs, sensors) via cloud.
- [x] Per-device "TPAP-locked" detection via local discovery probe (v1.2.0):
      `local_protocol`, `tpap_locked`, and `locally_controllable` attributes
      on each Cloud connection sensor.
- [ ] Publish to the HACS default repository list.
