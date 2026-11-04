# WiFi App Helper

[🇬🇧 English](README.md) · **🇩🇪 Deutsch**

WiFi App Helper übergibt genau einen unbenutzten, AP-fähigen WLAN-Adapter an den isolierten Netzwerk-Namespace einer Home-Assistant-App und stellt danach den ursprünglichen Host-Zustand wieder her. Er ist unabhängig von Tuya und kann von anderen vertrauenswürdigen Apps verwendet werden.

## Installation und Nutzung

1. Im [Home-Assistant-App-Katalog](https://github.com/seb5594/Home-Assistant-Apps) **WiFi App Helper** und eine kompatible Client-App installieren.
2. In beiden Konfigurationsseiten dasselbe private Kopplungsgeheimnis mit mindestens 32 Zeichen eintragen. Den Generator der Client-WebUI verwenden, falls vorhanden.
3. Zuerst den Helper starten. Danach in der Client-WebUI einen freien Adapter auswählen. Eine aktive Verwaltungsverbindung wird nicht übernommen; Home Assistant sollte über Ethernet erreichbar sein.
4. Eine Sitzung sauber beenden und den Adapter zurückgeben, bevor der Helper beendet wird. Bei ausstehender Wiederherstellung beide Log-Seiten prüfen. Wird beim Start überhaupt keine WLAN-Schnittstelle erkannt, beendet sich der Helper sofort mit Diagnosemeldungen.

Protection mode und AppArmor eingeschaltet lassen. Nur der Helper besitzt Host-Netzwerk, Host-D-Bus und NET_ADMIN. Die Client-App benötigt keinen Host- oder Docker-API-Zugriff. Das Geheimnis verleiht allen Apps, die es kennen, Steuerungsrechte: nur an vertrauenswürdige Apps weitergeben.

## Für Entwickler

Die [deutsche Integrationsanleitung](docs/integration.de.md) enthält ein vollständiges Beispiel, Konfigurations-, Dockerfile- und AppArmor-Vorlagen, Lebenszyklus, Fehlerbehandlung und Tests. Zusätzlich gibt es die [englische Anleitung](docs/integration.en.md), die [API-Spezifikation](docs/api.md) und das [Python-SDK](sdk/).

Helper und Clients werden unabhängig versioniert. Entscheidend ist API-Protokoll **3**, nicht dieselbe App-Versionsnummer. Ein Client wird mit einer geprüften SDK-Revision ausgeliefert und benötigt beim Bauen keine andere App-Repository.

## Umzug vom Anti Tuya WiFi Helper

Der alte Helper hatte die Kennung `untuyaos3_wifi`, der neue heißt technisch `wifi_helper`. Auch das private Socket-Verzeichnis ist jetzt allgemein benannt. Alte Sitzungen vollständig beenden und im alten Helper die erfolgreiche Adapter-Rückgabe prüfen. Erst danach den neuen Helper installieren und das privat gesicherte Kopplungsgeheimnis übernehmen. Client-App auf den neuen Stand aktualisieren bzw. neu erstellen. Beide Helper nicht gleichzeitig verwenden. Den alten Helper erst entfernen, wenn keine Wiederherstellung mehr aussteht und der neue funktioniert.

Alle Schritte für Endnutzer laufen über die Home-Assistant-Oberfläche. Es sind keine Host-Befehle und keine deaktivierten Schutzmechanismen erforderlich. Ein USB-Gerät ohne WLAN-Schnittstelle deutet auf einen fehlenden oder ungeeigneten HAOS-Treiber bzw. Firmware hin; der Helper lädt keine Kernelmodule nach.
