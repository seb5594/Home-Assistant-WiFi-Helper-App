# Changelog

## 2026.11.26

- **Breaking, protocol 4:** clients find the helper by its Home Assistant host name (`4c7fee11-wifi-helper` for the official repository) over a small HTTP API instead of sharing a pairing secret. The `pairing_token` option is gone from the helper and from all clients. Inventory is served over HTTP; the radio still moves through the Unix socket because a namespace descriptor cannot travel over HTTP.
- A client asks the helper for a ticket (valid 30 seconds, single use, bound to one operation and interface) and redeems it on the socket. The HTTP API only answers peers inside Home Assistant's internal network and listens on its gateway address by default.
- New optional packet capture: `tshark` in the image, pcap files recorded by clients (SDK module `wifi_helper.capture`), served and analysed over token-protected HTTP endpoints for Wireshark on another computer. Disabled by default; adds roughly 30 MiB to the image.
- AppArmor allows `net_raw` for host-side captures.

## 1.0.2

- Update the pinned Home Assistant Python base image to Python 3.14 and regenerate the build context from project.json.

## 1.0.1

- Rename the app to WiFi App Helper in Home Assistant, container metadata, branding and integration guides.
- Keep app slug `wifi_helper`, protocol 3, pairing settings, socket path and recovery data unchanged. Existing clients remain compatible.

## 1.0.0

- Extract the general WiFi App Helper into its own repository and independent release cycle.
- Preserve the reviewed protocol-3 authentication, radio checks, one-lease policy, recovery and immediate no-radio exit.
- Use generic app slug `wifi_helper` and private socket directory `wifi-helper-private`; document migration from the previous companion.
- Add a dependency-free Python SDK, public Client/RadioLease helpers, wire specification, English and German developer guides and runnable app templates.
