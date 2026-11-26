# WiFi App Helper

Reusable local service for Home Assistant apps: lends one unused, AP-capable WLAN PHY to a client's isolated network namespace and restores it afterwards. It has no Web UI, Docker API or host PID access. Client apps reach its small HTTP API by host name (`4c7fee11-wifi-helper`); no pairing secret is needed.

Install this helper once for trusted compatible clients and start it before a client. Keep Protection mode and AppArmor enabled. [English user guide](../README.md) · [Deutsche Anleitung](../README.de.md) · [Developer API and examples](../docs/integration.en.md).

## Options

- **HTTP port** (default 4817): port of the helper's HTTP API on Home Assistant's internal network.
- **Listen address**: empty keeps the API on the internal app network only. Set `0.0.0.0` only to reach the optional capture endpoints from your LAN.
- **Packet capture** and **Capture token**: optional, see the [Wireshark guide](../docs/wireshark.en.md). The token protects every capture endpoint.

Read the [migration guide](../README.md#migration-from-anti-tuya-wifi-helper) before removing an existing helper. Never remove it while adapter recovery is pending.
