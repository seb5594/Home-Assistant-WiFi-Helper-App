# Datenverkehr mit Wireshark ansehen

Optionale Funktion des WiFi App Helpers, standardmäßig **aus**.

## Funktionsweise

Der Adapter einer Client-App liegt im isolierten Netzwerk-Namespace dieser App, der Helper kann ihn von außen nicht mitschneiden. Deshalb zeichnet die Client-App den Verkehr ihres eigenen Adapters in eine pcap-Datei im gemeinsamen Ordner `/share/wifi-helper-private/captures/` auf. Der Helper stellt diese Dateien per HTTP bereit und kann `tshark` darauf ausführen:

```
Client-App ── PcapRecorder ──► /share/wifi-helper-private/captures/*.pcap
                                         │
Helper ── HTTP (+ tshark) ◄──────────────┘◄── Wireshark / curl am PC
```

Aufgezeichnet wird, was der Kernel an der Schnittstelle sieht: entschlüsselte Ethernet-Frames des WLANs, dem die Client-App beigetreten ist (IP, UDP, TCP, ...), keine rohen 802.11-Frames. Genau das braucht man, um zu verstehen, wie ein Gerät mit seiner App spricht.

## 1. Im Helper einschalten

In der Konfiguration des Helpers:

| Option | Wert |
| --- | --- |
| Paketmitschnitt | an |
| Capture-Token | Passwort mit mindestens 16 druckbaren Zeichen, ohne Leerzeichen |
| Lauschadresse | `0.0.0.0` für Zugriff aus dem LAN (siehe Sicherheitshinweis), leer nur für das interne Home-Assistant-Netz |

Helper neu starten. Im Log steht `packet capture enabled`. Ist das Token zu kurz oder fehlt `tshark`, nennt das Log den Grund; der Mitschnitt bleibt aus, das Ausleihen funktioniert weiter.

## 2. In einer Client-App aufzeichnen

Unterstützende Apps haben einen Schalter (WiFi Drone Connect: *Verkehr aufzeichnen*). In einer eigenen App:

```python
from wifi_helper.capture import PcapRecorder

recorder = PcapRecorder(radio.interface, label="mein-geraet").start()   # benötigt NET_RAW
...
recorder.stop()
```

Dateien heißen `<label>-JJJJMMTT-HHMMSS.pcap`. Nur die zehn neuesten bleiben erhalten, eine einzelne Datei endet bei 128 MiB.

## 3. Unter Windows öffnen

`homeassistant.local` durch Hostnamen oder IP ersetzen, `4817` durch den HTTP-Port des Helpers, dazu das Capture-Token verwenden.

**Live-Ansicht** (Wireshark im Standardordner, Windows 10 oder neuer wegen `curl.exe`):

```powershell
.\live-capture.ps1 -Server homeassistant.local -Token "<Token>" -Name drone-20261126-101500.pcap -Follow
```

Das Skript liegt unter [`examples/wireshark/live-capture.ps1`](../examples/wireshark/live-capture.ps1). Ohne `-Name` listet es die Mitschnitte auf. Ohne `-Follow` lädt es die Datei herunter und öffnet sie. Mit `-Filter 'udp.port == 6666'` reduziert `tshark` im Helper die Datei vorher.

Ohne Skript in der `cmd.exe` (nicht in PowerShell 5, das Binärdaten in Pipes verfälscht):

```bat
curl.exe -sN -H "Authorization: Bearer <Token>" "http://homeassistant.local:4817/v1/captures/<Name>?follow=1" | "C:\Program Files\Wireshark\Wireshark.exe" -k -i -
```

**Schneller Überblick ohne Wireshark**: `curl.exe -H "Authorization: Bearer <Token>" http://homeassistant.local:4817/v1/captures/<Name>/summary` zeigt die Gesprächstabellen (wer spricht mit wem auf welchem Port, mit Bytezahlen).

**Host-Schnittstellen**: `POST /v1/host-capture` mit `{"interface":"eth0","seconds":60,"filter":"udp port 6666"}` zeichnet eine Host-Schnittstelle (z. B. `hassio`) mit `tshark` im selben Ordner auf.

## Sicherheit

- Jeder Capture-Endpunkt verlangt `Authorization: Bearer <Token>`; ohne Token existieren die Endpunkte nicht.
- Mitschnitte enthalten alles, was über den Adapter lief: Gerätekennungen, von billigen Geräten im Klartext gesendete WLAN-Passwörter, Kamerabilder. Nach der Analyse löschen (`DELETE /v1/captures/<Name>`) und nie ungeschwärzt veröffentlichen.
- HTTP ist unverschlüsselt. Token und Verkehr kann jeder auf dem Weg mitlesen. Die Lauschadresse nur in einem vertrauenswürdigen Netz öffnen und danach wieder schließen.
- `tshark` läuft nur mit festen Argumenten; Anzeigefilter sind in Länge und Zeichen begrenzt, Dateinamen werden gegen ein strenges Muster geprüft.
