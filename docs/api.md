# Local radio lease API — protocol 4

The helper speaks two protocols, each for what it can do. Use the Python SDK whenever possible. Source of truth: `sdk/wifi_helper/protocol.py`, `client.py` and `wifi_helper/app/broker.py`, `api.py`.

| Channel | Address | Used for |
| --- | --- | --- |
| HTTP | `http://4c7fee11-wifi-helper:4817` (host name of the helper's repository slug, `local-wifi-helper` for a local install; port is the helper's *HTTP port* option) | Inventory, tickets, optional capture |
| Unix socket | `/share/wifi-helper-private/wifi.sock` (`AF_UNIX`, `SOCK_SEQPACKET`) | Lease and return, which transfer live kernel descriptors (`SCM_RIGHTS`) and therefore cannot use HTTP |

The helper listens on Home Assistant's internal gateway address (or `listen_address`) and answers inventory and ticket requests only for peers inside the app network or loopback. There is no pairing secret.

## HTTP endpoints

| Method and path | Access | Result |
| --- | --- | --- |
| `GET /v1/inventory` | app network | Adapter inventory (see below) |
| `POST /v1/tickets` | app network | Body `{"protocol":4,"operation":"lease"\|"return","interface":"wlan1"}` → `{"ticket":"<64 hex>"}`. HTTP 409 on a protocol mismatch, 400 on invalid input. |
| `GET /v1/captures` | capture token | `{"captures":[{"name","bytes","modified"}]}` |
| `GET /v1/captures/<name>[?follow=1][&filter=<display filter>]` | capture token | pcap bytes. `follow=1` keeps streaming appended packets (for `wireshark -k -i -`), `filter` returns a tshark-filtered copy. |
| `GET /v1/captures/<name>/summary[?filter=…]` | capture token | Plain-text tshark conversation tables |
| `DELETE /v1/captures/<name>` | capture token | Deletes a capture |
| `POST /v1/host-capture` | capture token | Body `{"interface":"eth0","seconds":60,"filter":"<capture filter>"}` records a host interface in the background (max. 600 s, one at a time) and returns `{"name"}` with HTTP 202 |

Capture endpoints exist only when *Packet capture* is enabled with a *Capture token* of at least 16 printable characters; they require `Authorization: Bearer <token>` and answer 404 otherwise. See the [Wireshark guide](wireshark.en.md).

A **ticket** is valid for 30 seconds, can be redeemed once and is bound to one operation and one interface. At most 8 are outstanding.

## Socket handshake

1. Server → client: `{"protocol":4}`.
2. Client → server: `{"protocol":4,"ticket":"<64 lowercase hex characters>"}`.
3. Server → client: `{"event":"authenticated"}`, or `{"error":"…"}` and a closed connection.

No descriptors are accepted before the ticket has been redeemed. Each packet is one UTF-8 JSON object, at most 65,536 bytes, sent with `sendmsg`; receive with `recvmsg`, inspect `MSG_TRUNC` / `MSG_CTRUNC` and close every received descriptor on every path. The private directory is mode 0700, the socket 0600, owned by the runtime user. HA apps normally use root in their own container; matching UID and mount access are required, without host PID access. The first request after the handshake must carry the same `operation` as the ticket.

## Inventory

`GET /v1/inventory` returns:

```json
{
  "adapters": [{"name":"wlan1","phy":"phy2","type":"managed","driver":"ath9k_htc","bus":"USB","eligible":true,"reason":""}],
  "usb_devices": [],
  "host": {"kernel":"…","loaded_wifi_modules":["ath9k_htc"]},
  "helper": {"version":"2026.11.26","protocol":4,"addon_slug":"4c7fee11_wifi_helper"},
  "recovery_pending":""
}
```

`helper.addon_slug` is the helper's validated full Home Assistant app ID, derived from its own container hostname. It lets clients link to a helper installed from a different repository. Unknown identity is null. Treat `eligible` as a snapshot; lease acquisition repeats every check. Inventory remains available while a lease is active or recovery is pending. USB diagnostics distinguish an enumerated USB device from a driver-bound WLAN interface. No-radio startup exits instead of keeping an unusable service alive.

## Lease

Request a `lease` ticket for an exact interface such as `wlan1`, redeem it on the socket, then send `{"operation":"lease","interface":"wlan1"}` with **exactly one** read-only descriptor opened from `/proc/self/ns/net`. The descriptor must be a network namespace and must differ from the helper's host namespace. Never use host networking for a client.

The helper sends zero or more `{"event":"log","level":"info","text":"…"}` objects, followed by:

```json
{"event":"ready","phy":"phy2","mac":"02:00:00:00:00:01","power_save":"off"}
```

It moves the whole selected PHY, not merely an interface. Only one interface may exist on that PHY. Keep this **original connection open**, do not send application data on it, and watch for EOF. EOF means loss of the helper/lease; stop child processes and terminate the client container. There is one global active lease. Another acquire is rejected until the previous adapter is restored; there is no queue or silent fallback to another radio.

## Normal return

1. Stop all processes using the leased radio. Disconnect it, bring it down, clear its IPv4/IPv6 addresses and dependent routes. Verify its identity before each mutation.
2. Keep the original lease connection open. Request a `return` ticket for the leased interface and redeem it on a **second socket connection**. Send `{"operation":"return"}` without descriptors.
3. Receive `{"event":"return_target","phy":"phy2"}` with exactly one read-only host network namespace descriptor. Validate `NS_GET_NSTYPE == CLONE_NEWNET (0x40000000)`. Do not call `setns`, mount it, or execute anything inside the host namespace.
4. On the client, call only `iw phy <leased-phy> set netns name /proc/self/fd/<fd>` with that descriptor explicitly inherited. The client's NET_ADMIN operates on its own leased radio. Verify PHY, interface index and MAC first.
5. Close the descriptor and send `{"operation":"returned"}`. The helper independently verifies the same radio has returned idle, restores power saving, link state and NetworkManager ownership, and answers `{"event":"released"}`. Close both connections.

The SDK implements these details. A read-only namespace descriptor is a return destination, not authorization to enter it; SYS_ADMIN is not granted.

## Failures and timeouts

Errors are objects with `error` and, when relevant, `restart_required` or `recovery_pending`. Do not infer that no mutation occurred just because acquisition failed. The SDK sets its loss event for uncertain assignments. Its client connection timeout is 45 seconds; server handshake timeout 5 seconds, return timeout 15 seconds. Recovery polls at bounded intervals and retains durable `/data/recovery.json` until verified restoration. Main applications must impose their own run deadline and serialize operations.

| Condition | Required client behavior |
| --- | --- |
| Missing socket / helper stopped | Keep UI responsive; offer helper setup/refresh. Do not use host networking as fallback. |
| Helper not reachable over HTTP | Show the configured host name and offer a refresh. Check that the helper runs and that the host name matches its repository (`4c7fee11-wifi-helper`, `local-wifi-helper`). |
| Ticket rejected | Retry once; tickets expire after 30 seconds and work only once. |
| Protocol mismatch | Update to a compatible SDK/helper; do not require matching app release versions. |
| Radio busy or ineligible | Show the rejection reason; let the user explicitly choose a different adapter. |
| Lease EOF, USB disappearance or uncertain handover | Stop radio workers and exit the container. Keep recovery metadata. |
| Cleanup/return not confirmed | Exit the container, show recovery pending, and do not start another session. |

Closing only the socket does **not** destroy a still-running client's network namespace. If explicit return fails, the entire client container must stop. A long-running Ingress app must coordinate worker shutdown and process exit; do not leave the client UI alive with unknown ownership.

## Security and recovery

Only unused, AP-capable managed interfaces with no active addresses, routes, bridge/master or association are eligible. Host NetworkManager must report an idle device; the helper temporarily changes ownership of only that interface. Recovery matches stable MAC plus driver/bus/device/USB path; PHY renumbering is not a different adapter. An unrelated or active radio is never disconnected to satisfy recovery.

The helper requires host networking, host D-Bus and NET_ADMIN, not host PID, SYS_ADMIN, Docker API, Supervisor API, Home Assistant API or broad USB access. Clients use their own network namespace, the private shared IPC directory and NET_ADMIN; add NET_RAW only for DHCP/ping/raw Wi-Fi workflows. AppArmor narrows `/share` to the IPC directory. Inventory alone needs no network capability.

Every app that reaches the helper's HTTP port *and* opens its socket in `/share` is a trusted radio-control peer. Protocol 4 does not provide per-app ACLs, owner IDs or per-tenant isolation. Do not expose the socket via a proxy, give the `share` mount to untrusted containers, or describe tickets as protection from a compromised authorized client. Tickets only tie one HTTP request to one socket session. No API operation loads drivers, resets USB controllers, changes global regulatory settings or restarts host NetworkManager.
