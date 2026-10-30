# Integrate WiFi Namespace Helper into your app

[Deutsch](integration.de.md) · [Wire specification](api.md)

This guide is for app developers. End users install and configure both apps in Home Assistant; they never need host terminal commands. Do not run this code inside Home Assistant Core or a host-network container: the radio must be handed to an isolated client container.

## 1. Choose the right integration

Use this helper when a trusted Home Assistant app needs exclusive control of an unused WLAN PHY for scanning, station mode or temporary AP services. It is not for taking over the host's active management Wi-Fi, installing missing kernel drivers, or exposing an HTTP radio-control endpoint. Standard requirements are HAOS/Supervisor, NetworkManager, `iw`, a real unused WLAN interface, AP mode advertised by its driver, and namespace movement accepted by the kernel. Ethernet should carry Home Assistant's management connection.

The app release version and API version are independent. SDK **1.0.0** speaks protocol **3**. A client at version 7.4 can use a helper at version 1.0 as long as the protocol matches. Use a reviewed SDK commit, record it and its file hashes in your repository, and refresh intentionally. Never fetch a floating branch at application startup.

## 2. Vendor the SDK

Copy `sdk/wifi_helper/` into `vendor/wifi_helper/` in your app project, including `build_info.json`. Preserve its copyright/license and record the source repository and commit. The SDK has no third-party Python runtime dependencies and needs Linux/Python 3.11+. You can instead build/install the package defined by `sdk/pyproject.toml`; include package data so `build_info.json` is available.

The [complete example app](../examples/minimal_app/) assumes `vendor/wifi_helper/` exists in its build context. Its Dockerfile copies it to `/opt/sdk/wifi_helper`, puts `/opt/sdk` on PYTHONPATH and uses the official Home Assistant Python base image. No other app repository or sibling checkout is required.

## 3. Give the client only its required permissions

Start with [config.yaml](../examples/minimal_app/config.yaml.example), [Dockerfile](../examples/minimal_app/Dockerfile) and [AppArmor profile](../examples/minimal_app/apparmor.txt). The client has:

- its own network namespace; no `host_network`, host D-Bus, host PID or SYS_ADMIN;
- a `/share` mount, narrowed by AppArmor to `/share/wifi-helper-private/`;
- NET_ADMIN for configuring and returning its leased radio;
- NET_RAW only if its actual workflow needs DHCP, ping or raw sockets;
- a password option named `pairing_token` and no Supervisor, Home Assistant or Docker API access.

For an inventory-only client remove both capabilities; listing uses local IPC. A client that provides Ingress must validate the real Ingress peer, use CSRF protection for mutations and keep secrets out of status responses. The included example deliberately has no HTTP server.

## 4. Inventory, selection and acquisition

```python
from wifi_helper import Client

client = Client(secret, lost=fatal_event, log=emit_log)
status = client.inventory()
choices = [item for item in status['adapters'] if item['eligible']]
# Auto-select only if there is exactly one eligible radio; otherwise ask the user.
radio = client.acquire(selected_interface)
# radio.interface, radio.phy, radio.mac, radio.adapter, radio.original_power_save
```

`secret` comes from the app's private options, never a URL, browser-local storage or hard-coded example value. `emit_log(level, text, channel)` can connect to your own structured journal. `fatal_event` is a `threading.Event`. The helper rechecks eligibility during acquisition; inventory is not approval. Do not silently try another adapter if acquisition fails.

`acquire()` returns only after the PHY has moved into your container. It transfers a descriptor opened from `/proc/self/ns/net`; neither app enters the other's namespace. Keep the returned handle alive while workers use the radio. The SDK maintains the original lease connection and watches for unexpected EOF.

## 5. Own the complete lifecycle

[radio_job.py](../examples/radio_job.py) is a runnable reference. It reads private HA options, discovers adapters, starts a bounded demonstration, watches termination/loss and returns the radio. Its template leaves actual Wi-Fi work to your application.

```python
radio = client.acquire(selected_interface)
try:
    run_your_bounded_job(radio.interface, client.lost)
finally:
    stop_and_wait_for_your_radio_processes()
    radio.release()
```

Always stop and reap supplicant, hostapd, DHCP, raw-socket users and any related child process before release. `release()` validates the leased identity, disconnects/down/cleans only that radio and asks the helper to restore host settings. It is idempotent after success. It does not know your processes and cannot safely stop them for you.

If `client.lost` is set or release fails, terminate the entire client app/container after stopping workers. Closing only the socket does not release a namespace held by your running process. Do not catch such an error and continue serving an idle UI as though recovery succeeded. Recovery pending must block another session. The helper retains its recovery snapshot and refuses to touch unrelated hardware.

For an Ingress application, serialize acquire/start/stop/return with one operation lock; keep status requests responsive. Freeze tool/radio configuration during a run and cleanup. On normal completion, return the radio, then unlock adapter selection. On uncertainty, let the main process exit so Supervisor stops the container. If your job creates AP services, bind them only to the leased adapter/address and block forwarding to the container uplink.

## 6. Errors and privacy

Handle `HelperUnavailable`, `SecretNotSet`, `PairingFailed` and `ProtocolMismatch` separately. Authentication failures are configuration problems, not permission to enable host networking. User-facing recovery messages should identify the failed stage, not print secrets or device dumps. The pairing secret grants all trusted peers access to this one helper; protocol 3 is not per-app authorization. Do not give it to arbitrary third-party code.

Use an explicit user action to export diagnostic files that may contain device data. Log radio identity, progress, heartbeats, child exit status and cleanup results, but keep pairing tokens, Wi-Fi passwords and device keys out of logs and URLs.

## 7. Tests before publication

Use the SDK's real Unix socket/authentication tests and mock host operations. Test wrong secrets, protocol mismatch, unexpected descriptors, no adapter, busy adapter, two interfaces on one PHY, namespace-move rejection, USB removal, lease EOF, partial startup, cancellation, failed cleanup and return with a changed PHY number. Assert unrelated interfaces/routes/NetworkManager services are untouched. Verify API and permission templates in CI.

Software tests do not prove a driver's physical AP behavior. Document your actual hardware checks separately. Use your own app version and release pipeline; neither app needs to share the helper's release number.
