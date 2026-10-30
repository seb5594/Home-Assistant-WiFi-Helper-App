# Minimal client app template

Copy this folder into your own app repository and rename `config.yaml.example` to `config.yaml`. The `.example` suffix keeps this documentation template out of the app catalog. Vendor the reviewed `sdk/wifi_helper/` package as `vendor/wifi_helper/` **inside this build context**, preserving its license, source revision and checksums. See [English](../../docs/integration.en.md) / [Deutsch](../../docs/integration.de.md).

Install both apps through Home Assistant, configure the same private pairing secret and select `interface` only when multiple eligible radios exist. Start the helper before this example. The example logs interface information, waits at most 30 seconds and returns its radio; it never flashes, connects to a device, or opens an AP. Exit errors stop its container so helper recovery can proceed.

Only NET_ADMIN is needed for this demonstration. A real DHCP/ping job also needs NET_RAW. An inventory-only client needs neither. No host networking, host D-Bus, SYS_ADMIN, broad USB access, or Home Assistant/Supervisor/Docker API is required. Keep Protection mode and AppArmor on.
