# Looking at the traffic with Wireshark

An optional feature of WiFi App Helper. It is **off by default**.

## How it works

The radio of a client app lives inside that app's isolated network namespace, so the helper cannot sniff it from the outside. The client therefore records the traffic of its own leased radio into a pcap file in the shared folder `/share/wifi-helper-private/captures/`. The helper serves these files over HTTP and can run `tshark` on them:

```
client app ── PcapRecorder ──► /share/wifi-helper-private/captures/*.pcap
                                         │
helper ── HTTP (+ tshark) ◄──────────────┘◄── Wireshark / curl on your PC
```

The recording contains what the kernel sees on the interface: the decrypted Ethernet frames of the Wi-Fi network the client joined (IP, UDP, TCP, ...), not raw 802.11 frames. That is what you need to understand how a device talks to its app.

## 1. Switch it on in the helper

In the helper's Configuration tab:

| Option | Value |
| --- | --- |
| Packet capture | on |
| Capture token | a password of at least 16 printable characters, no spaces |
| Listen address | `0.0.0.0` to reach it from your LAN (see the security note), empty for Home Assistant's internal network only |

Restart the helper. The log shows `packet capture enabled`. If the token is too short or `tshark` is missing, the log says why and capture stays off while leasing keeps working.

## 2. Record in a client app

Clients that support it have a switch (the WiFi Drone Connect app: *Record traffic*). In your own client:

```python
from wifi_helper.capture import PcapRecorder

recorder = PcapRecorder(radio.interface, label="my-device").start()   # needs NET_RAW
...
recorder.stop()
```

Files are named `<label>-YYYYMMDD-HHMMSS.pcap`; only the newest ten are kept and a single file stops at 128 MiB.

## 3. Open it on Windows

Replace `homeassistant.local` with your Home Assistant host or IP, `4817` with the helper's HTTP port and use your capture token.

**Live view** (Wireshark installed in the default folder, Windows 10 or later for `curl.exe`):

```powershell
.\live-capture.ps1 -Server homeassistant.local -Token "<token>" -Name drone-20261126-101500.pcap -Follow
```

The script lives at [`examples/wireshark/live-capture.ps1`](../examples/wireshark/live-capture.ps1). With no `-Name` it lists the available captures. Without `-Follow` it downloads the file and opens it. `-Filter 'udp.port == 6666'` lets `tshark` on the helper reduce the file first.

Without the script, in `cmd.exe` (not PowerShell 5, which corrupts binary pipes):

```bat
curl.exe -sN -H "Authorization: Bearer <token>" "http://homeassistant.local:4817/v1/captures/<name>?follow=1" | "C:\Program Files\Wireshark\Wireshark.exe" -k -i -
```

**Quick look without Wireshark**: `curl.exe -H "Authorization: Bearer <token>" http://homeassistant.local:4817/v1/captures/<name>/summary` prints the conversation tables (who talked to whom on which port, with byte counts).

**Host interfaces**: `POST /v1/host-capture` with `{"interface":"eth0","seconds":60,"filter":"udp port 6666"}` records a host-side interface (for example `hassio`) with `tshark` into the same folder.

## Security

- Every capture endpoint needs `Authorization: Bearer <token>`; without a token the endpoints do not exist.
- Capture files contain everything that crossed the radio: device identifiers, Wi-Fi passwords sent in clear text by cheap devices, camera frames. Delete them when done (`DELETE /v1/captures/<name>`) and do not publish them unredacted.
- HTTP is not encrypted. The token and the traffic can be read by anyone on the path. Open the listen address to your LAN only on a network you trust and keep it off while you do not need it.
- `tshark` runs only with fixed arguments; display filters are length- and character-limited, and file names are matched against a strict pattern.
