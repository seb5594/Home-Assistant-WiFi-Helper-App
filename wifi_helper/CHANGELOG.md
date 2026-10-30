# Changelog

## 1.0.0

- Extract the general WiFi Namespace Helper into its own repository and independent release cycle.
- Preserve the reviewed protocol-3 authentication, radio checks, one-lease policy, recovery and immediate no-radio exit.
- Use generic app slug `wifi_helper` and private socket directory `wifi-helper-private`; document migration from the previous companion.
- Add a dependency-free Python SDK, public Client/RadioLease helpers, wire specification, English and German developer guides and runnable app templates.
