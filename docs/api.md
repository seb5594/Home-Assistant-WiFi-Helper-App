# Local radio lease API — protocol 3

This API is a Linux-only, authenticated **AF_UNIX / SOCK_SEQPACKET** protocol at `/share/wifi-helper-private/wifi.sock`. It is not HTTP and cannot be forwarded over a network: `SCM_RIGHTS` transfers live kernel descriptors locally. Use the Python SDK whenever possible. Source of truth: `sdk/wifi_helper/protocol.py`, `client.py` and `wifi_helper/app/broker.py`.

## Transport

Each packet is one UTF-8 JSON object, at most 65,536 bytes, sent with `sendmsg`. Requests are not newline-delimited streams. Receive with `recvmsg`, inspect `MSG_TRUNC` / `MSG_CTRUNC`, and close every received descriptor on every path. Descriptors must be non-inheritable except when deliberately passed to the fixed `iw` subprocess. A malformed object, unexpected descriptor or failed handshake is rejected. The private directory is mode 0700, socket 0600, owned by the runtime user. HA apps normally use root in their own container; matching UID and mount access are required, without host PID access.

## Mutual authentication

1. Server → client: `{"protocol":3,"challenge":"<64 lowercase hex characters>"}`.
2. Client chooses a fresh 32-byte nonce (64 lowercase hex), then sends `{"protocol":3,"interface":"@inventory or exact interface","nonce":"...","proof":"..."}`.
3. Server verifies the request and returns `{"proof":"..."}`. Client verifies the server proof before passing a descriptor.

The proof is lowercase hex HMAC-SHA256, key = the UTF-8 pairing secret. The message is compact JSON with no spaces:

```python
json.dumps([3, direction, challenge, nonce, scope], separators=(",", ":")).encode()
```

`direction` is `client` or `server`. `scope` is `@inventory` or the exact interface name. The secret is at least 32 characters and is never sent. Both nonces and scope bind the proof, preventing replay and scope substitution. Authentication is required on **each new connection**, including return. The app release version is not in the proof and may differ between server and client. No descriptors are accepted during authentication.

## Inventory

Authenticate with scope `@inventory`, then send `{"operation":"inventory"}` without descriptors. Response:

```json
{
  "adapters": [{"name":"wlan1","phy":"phy2","type":"managed","driver":"ath9k_htc","bus":"USB","eligible":true,"reason":""}],
  "usb_devices": [],
  "host": {"kernel":"…","loaded_wifi_modules":["ath9k_htc"]},
  "helper": {"version":"1.0.0","protocol":3},
  "recovery_pending":""
}
```

Additional fields may be added. Treat `eligible` as a snapshot; lease acquisition repeats every check. Inventory remains available while a lease is active or recovery is pending. USB diagnostics distinguish an enumerated USB device from a driver-bound WLAN interface. No-radio startup exits instead of keeping an unusable service alive.

## Lease

Authenticate for an exact interface such as `wlan1`, then send `{"operation":"lease","interface":"wlan1"}` with **exactly one** read-only descriptor opened from `/proc/self/ns/net`. The descriptor must be a network namespace and must differ from the helper's host namespace. Never use host networking for a client.

The helper sends zero or more `{"event":"log","level":"info","text":"…"}` objects, followed by:

```json
{"event":"ready","phy":"phy2","mac":"02:00:00:00:00:01","power_save":"off"}
```

It moves the whole selected PHY, not merely an interface. Only one interface may exist on that PHY. Keep this **original connection open**, do not send application data on it, and watch for EOF. EOF means loss of the helper/lease; stop child processes and terminate the client container. There is one global active lease. Another acquire is rejected until the previous adapter is restored; there is no queue or silent fallback to another radio.

## Normal return

1. Stop all processes using the leased radio. Disconnect it, bring it down, clear its IPv4/IPv6 addresses and dependent routes. Verify its identity before each mutation.
2. Keep the original lease connection open. Open a **second authenticated connection** scoped to the leased interface. Send `{"operation":"return"}` without descriptors.
3. Receive `{"event":"return_target","phy":"phy2"}` with exactly one read-only host network namespace descriptor. Validate `NS_GET_NSTYPE == CLONE_NEWNET (0x40000000)`. Do not call `setns`, mount it, or execute anything inside the host namespace.
4. On the client, call only `iw phy <leased-phy> set netns name /proc/self/fd/<fd>` with that descriptor explicitly inherited. The client's NET_ADMIN operates on its own leased radio. Verify PHY, interface index and MAC first.
5. Close the descriptor and send `{"operation":"returned"}`. The helper independently verifies the same radio has returned idle, restores power saving, link state and NetworkManager ownership, and answers `{"event":"released"}`. Close both connections.

The SDK implements these details. A read-only namespace descriptor is a return destination, not authorization to enter it; SYS_ADMIN is not granted.

## Failures and timeouts

Errors are objects with `error` and, when relevant, `restart_required` or `recovery_pending`. Do not infer that no mutation occurred just because acquisition failed. The SDK sets its loss event for uncertain assignments. Its client connection timeout is 45 seconds; server handshake timeout 5 seconds, return timeout 15 seconds. Recovery polls at bounded intervals and retains durable `/data/recovery.json` until verified restoration. Main applications must impose their own run deadline and serialize operations.

| Condition | Required client behavior |
| --- | --- |
| Missing socket / helper stopped | Keep UI responsive; offer helper setup/refresh. Do not use host networking as fallback. |
| Wrong secret | Report pairing failure; do not log or resend the secret in plaintext. |
| Protocol mismatch | Update to a compatible SDK/helper; do not require matching app release versions. |
| Radio busy or ineligible | Show the rejection reason; let the user explicitly choose a different adapter. |
| Lease EOF, USB disappearance or uncertain handover | Stop radio workers and exit the container. Keep recovery metadata. |
| Cleanup/return not confirmed | Exit the container, show recovery pending, and do not start another session. |

Closing only the socket does **not** destroy a still-running client's network namespace. If explicit return fails, the entire client container must stop. A long-running Ingress app must coordinate worker shutdown and process exit; do not leave the client UI alive with unknown ownership.

## Security and recovery

Only unused, AP-capable managed interfaces with no active addresses, routes, bridge/master or association are eligible. Host NetworkManager must report an idle device; the helper temporarily changes ownership of only that interface. Recovery matches stable MAC plus driver/bus/device/USB path; PHY renumbering is not a different adapter. An unrelated or active radio is never disconnected to satisfy recovery.

The helper requires host networking, host D-Bus and NET_ADMIN, not host PID, SYS_ADMIN, Docker API, Supervisor API, Home Assistant API or broad USB access. Clients use their own network namespace, the private shared IPC directory and NET_ADMIN; add NET_RAW only for DHCP/ping/raw Wi-Fi workflows. AppArmor narrows `/share` to the IPC directory. Inventory alone needs no network capability.

Every holder of the one pairing secret is a trusted radio-control peer. Protocol 3 does not provide per-app ACLs, owner IDs or per-tenant isolation. Do not expose the socket via an unauthenticated proxy, share it with untrusted containers, or describe HMAC as protection from a compromised authorized client. No API operation loads drivers, resets USB controllers, changes global regulatory settings or restarts host NetworkManager.
