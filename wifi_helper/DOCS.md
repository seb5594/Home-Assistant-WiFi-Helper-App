# WiFi Namespace Helper

Reusable local service for Home Assistant apps: lends one unused, AP-capable WLAN PHY to a client's isolated network namespace and restores it afterwards. It has no Web UI, HTTP listener, Docker API or host PID access.

Install this helper once for trusted compatible clients, configure the same private pairing secret, and start the helper before a client. Keep Protection mode and AppArmor enabled. [English user guide](../README.md) · [Deutsche Anleitung](../README.de.md) · [Developer API and examples](../docs/integration.en.md).

Read the [migration guide](../README.md#migration-from-anti-tuya-wifi-helper) before removing an existing helper. Never remove it while adapter recovery is pending.
