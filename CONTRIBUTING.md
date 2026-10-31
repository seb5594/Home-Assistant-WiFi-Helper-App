# Contributing to WiFi App Helper

This is one independent app plus a reusable Python SDK. `project.json` controls the app release, API protocol, independent `sdk_version` and generated build context. SDK packaging metadata is generated from its template too. SDK source lives in `sdk/wifi_helper/`; its public API and wire contract must remain versioned independently of consumers. Owned broker/inventory code lives in `wifi_helper/app/` and local logging in `shared/journal.py`. Run `tools/sync_project.py` after changes and commit generated copies.

Run the Linux `tests/` suite with PyYAML, verify the generator and parse the app/example AppArmor profiles. Protocol tests transfer real descriptors and perform HMAC authentication while radio mutations remain mocked. SDK tests cover independent app versions, partial acquisition and identity checks before cleanup. The example config carries `.example` so the catalog never treats it as a second app.

Breaking wire changes require a protocol version change, updated SDK and English/German API documentation. Additive inventory fields do not require matching release numbers. Keep the fail-closed checks, one active lease, durable recovery, no-radio immediate exit and no global network-service changes. Test on real HAOS hardware before claiming driver compatibility.

`dev` publishes via the pinned hass-workflows caller after builds/checks. The helper requires only host networking, host D-Bus and NET_ADMIN. Never add host PID, SYS_ADMIN, Docker/HA/Supervisor API or broad USB access. Do not expose this descriptor API as HTTP. The pairing secret authorizes trusted peers collectively; do not claim per-app tenancy isolation.

All end-user installation, configuration and recovery instructions must use Home Assistant's UI. Developer templates and examples are in `examples/`, with full English/German integration guides under `docs/`.
