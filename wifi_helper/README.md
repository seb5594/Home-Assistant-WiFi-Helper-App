# WiFi App Helper

Reusable local service for Home Assistant apps: lends one unused, AP-capable WLAN PHY to a client's isolated network namespace and restores it afterwards. It has no Web UI, Docker API or host PID access. Client apps reach its small HTTP API by host name (`4c7fee11-wifi-helper`); no pairing secret is needed.

Install this helper once for trusted compatible clients and start it before a client. Keep Protection mode and AppArmor enabled. [English user guide](../README.md) · [Deutsche Anleitung](../README.de.md) · [Developer API and examples](../docs/integration.en.md).
