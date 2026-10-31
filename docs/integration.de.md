# WiFi App Helper in eigene Apps integrieren

[English](integration.en.md) · [API-Spezifikation](api.md)

Diese Anleitung richtet sich an App-Entwickler. Endnutzer installieren und konfigurieren Helper und Client vollständig in Home Assistant. Es sind keine Host-Befehle nötig. Der Client muss ein eigener, isolierter Container sein; dieses Beispiel gehört weder in Home Assistant Core noch in einen Container mit Host-Netzwerk.

## 1. Einsatzbereich und Versionierung

Der Helper eignet sich für vertrauenswürdige Apps, die genau einen unbenutzten WLAN-PHY zum Scannen, als Station oder als temporären Access Point benötigen. Er übernimmt keine aktive Verwaltungsverbindung und lädt keine Kernelmodule nach. Voraussetzungen sind HAOS/Supervisor, NetworkManager, eine vom Host-Treiber bereitgestellte WLAN-Schnittstelle, angekündigter AP-Modus und erfolgreiche Namespace-Übergabe durch den Kernel. Home Assistant sollte über Ethernet erreichbar bleiben.

SDK **1.0.0** spricht API-Protokoll **3**. App- und Helper-Versionen müssen nicht gleich sein: Entscheidend ist die Protokollnummer. Eine geprüfte SDK-Revision mit Commit und Datei-Prüfsummen festhalten und bewusst aktualisieren. Keine bewegliche Branch-Version beim Start aus dem Internet nachladen.

## 2. SDK übernehmen

Den Ordner `sdk/wifi_helper/` samt `build_info.json` nach `vendor/wifi_helper/` im eigenen Projekt übernehmen. Lizenz, Herkunft und Commit dokumentieren. Das SDK benötigt Linux und Python ab 3.11, aber keine zusätzlichen Python-Laufzeitpakete. Alternativ kann das Paket über `sdk/pyproject.toml` gebaut und installiert werden; die JSON-Paketdaten müssen mitgeliefert werden.

Die [vollständige Beispiel-App](../examples/minimal_app/) erwartet diesen Vendor-Ordner im Docker-Build-Kontext. Ihr Dockerfile kopiert ihn nach `/opt/sdk/wifi_helper` und setzt PYTHONPATH auf `/opt/sdk`. Ein paralleler Checkout von UnTuyaOS3 oder Tuya Breaker ist nicht erforderlich.

## 3. Rechte und Konfiguration

Als Vorlage dienen [config.yaml](../examples/minimal_app/config.yaml.example), [Dockerfile](../examples/minimal_app/Dockerfile) und [AppArmor-Profil](../examples/minimal_app/apparmor.txt). Der Client erhält sein eigenes Netzwerk, das private gemeinsame Socket-Verzeichnis und NET_ADMIN zum Bearbeiten und Zurückgeben seines ausgeliehenen Adapters. NET_RAW nur hinzufügen, wenn DHCP, Ping oder Raw-Sockets es tatsächlich benötigen.

Kein Host-Netzwerk, kein Host-D-Bus, keine Host-PID-Namespace, kein SYS_ADMIN, keine Docker-, Supervisor- oder Home-Assistant-API. Der `/share`-Mount wird mit AppArmor auf `/share/wifi-helper-private/` eingeschränkt. Eine reine Inventarabfrage benötigt keine Netzwerk-Capabilities. Die Option `pairing_token` ist ein Passwortfeld; Endnutzer tragen denselben privaten Wert im Helper und im Client ein.

Eine eigene Ingress-Oberfläche muss zusätzlich den echten Ingress-Peer prüfen, Änderungen gegen CSRF schützen und Geheimnisse aus Statusantworten fernhalten. Das Minimalbeispiel hat bewusst keinen HTTP-Server.

## 4. Inventar und Adapterauswahl

```python
from wifi_helper import Client

client = Client(secret, lost=fatal_event, log=emit_log)
status = client.inventory()
eligible = [item for item in status['adapters'] if item['eligible']]
# Nur bei genau einem geeigneten Adapter automatisch vorauswählen.
radio = client.acquire(selected_interface)
```

`secret` stammt aus den privaten App-Optionen, nicht aus einer URL, einem fest eingebauten Testwert oder dem Browser-Speicher. `fatal_event` ist ein `threading.Event`; `emit_log(level, text, channel)` bindet die eigene strukturierte Protokollierung an. Mehrere geeignete Adapter muss der Nutzer ausdrücklich auswählen. Bei einem Fehler nicht heimlich den nächsten Adapter versuchen.

Das Inventar ist eine Momentaufnahme. `acquire()` wiederholt die Sicherheitsprüfungen und liefert erst nach erfolgreicher Übergabe einen Handle. `radio.interface`, `phy`, `mac`, `adapter` und `original_power_save` beschreiben den eigenen Adapter. Das SDK übergibt nur einen Descriptor von `/proc/self/ns/net`; es betritt keinen fremden Namespace.

## 5. Lebenszyklus sauber umsetzen

[radio_job.py](../examples/radio_job.py) zeigt einen vollständigen Ablauf mit privaten HA-Optionen, Inventar, begrenzter Laufzeit, Signal- und Verlustbehandlung sowie Rückgabe. Die eigentliche WLAN-Arbeit bleibt eine klar markierte Stelle für das eigene Projekt.

```python
radio = client.acquire(selected_interface)
try:
    run_your_bounded_job(radio.interface, client.lost)
finally:
    stop_and_wait_for_your_radio_processes()
    radio.release()
```

Vor `release()` alle eigenen Supplicant-, Hostapd-, DHCP- und sonstigen Funkprozesse beenden und auf ihr Ende warten. Das SDK kennt diese Prozesse nicht. Es prüft anschließend die Adapteridentität, trennt nur den eigenen Adapter, setzt ihn herunter, entfernt seine Adressen und Routen und lässt den Helper die ursprünglichen Host-Einstellungen wiederherstellen. Eine erfolgreich abgeschlossene Rückgabe kann erneut aufgerufen werden, ohne weitere Änderungen auszulösen.

Bei gesetztem `client.lost` oder fehlgeschlagener Rückgabe nach dem Stoppen der Worker den gesamten Client-Container beenden. Nur den Socket zu schließen zerstört einen vom laufenden Prozess gehaltenen Netzwerk-Namespace nicht. Solche Fehler nicht abfangen und mit einer scheinbar bereiten UI weiterarbeiten. Solange Wiederherstellung aussteht, keine neue Sitzung starten. Der Helper behält seine Wiederherstellungsdaten und verändert keinen fremden Adapter.

Eine Ingress-App sollte Auswahl, Start, Stop und Rückgabe mit einer gemeinsamen Operationssperre serialisieren, während Statusabfragen weiter antworten. Werkzeug- und Adapterwahl bleiben bis nach dem Cleanup gesperrt. Nach erfolgreicher Rückgabe wieder entsperren; bei unklarem Besitz den Hauptprozess beenden. Eigene AP-Dienste ausschließlich an den ausgeliehenen Adapter bzw. seine Adresse binden und Weiterleitung zum Container-Uplink blockieren.

## 6. Fehler, Geheimnisse und Logs

`HelperUnavailable`, `SecretNotSet`, `PairingFailed` und `ProtocolMismatch` getrennt behandeln. Ein Authentifizierungsfehler rechtfertigt weder Host-Netzwerk noch mehr Container-Rechte. Adapteridentität, Fortschritt, Heartbeats, Prozess-Endstatus und Cleanup-Ergebnisse protokollieren. Kopplungsgeheimnisse, WLAN-Passwörter, lokale Geräteschlüssel und Flash-Dumps gehören nicht in öffentliche Logs oder URLs.

Jeder, der das gemeinsame Kopplungsgeheimnis kennt, ist ein vertrauenswürdiger Steuerungs-Client. Protokoll 3 enthält keine individuellen App-ACLs und ist keine Mandantentrennung. Das Geheimnis nicht beliebigen Erweiterungen oder öffentlichen Proxys geben.

## 7. Tests und Veröffentlichung

Die echten Unix-Socket- und HMAC-Tests des SDK verwenden, Host-Mutationen jedoch mocken. Mindestens falsches Geheimnis, falsche Protokollnummer, unerwartete Deskriptoren, fehlender oder belegter Adapter, mehrere Interfaces auf einem PHY, abgelehnte Übergabe, USB-Abziehen, Lease-EOF, teilweiser Start, Abbruch, fehlgeschlagenes Cleanup und geänderte PHY-Nummer bei der Rückkehr prüfen. Fremde Interfaces, Routen und NetworkManager-Dienste dürfen unverändert bleiben.

Softwaretests beweisen kein physisches AP-Verhalten eines Treibers. Hardwaretests separat dokumentieren. Die eigene App wird unabhängig vom Helper versioniert und veröffentlicht. Für alle Endnutzer-Schritte eine Home-Assistant-Oberfläche anbieten; keine Shell-Kommandos voraussetzen.
