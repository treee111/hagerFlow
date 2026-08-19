# Hager flow für Home Assistant

Home-Assistant-Integration für den **Hager flow** Batteriespeicher mit PV-Anlage
(intern E3/DC-Hardware). Liefert Live-Leistungen, Batterie-Ladestand und kumulierte
Energiezähler — letztere direkt nutzbar im Energie-Dashboard.

> **Inoffiziell.** Diese Integration nutzt die undokumentierte API hinter dem
> flow-Portal. Hager bietet unter [developer.hagerenergy.com](https://developer.hagerenergy.com/)
> inzwischen eine offizielle API an — siehe [Ausblick](#ausblick-offizielle-api).

## Entitäten

| Entität | Einheit | Bemerkung |
|---|---|---|
| Batterie-Ladestand | % | |
| PV-Leistung | W | Summe aller Strings |
| Hausverbrauch | W | |
| Batterieleistung | W | positiv = laden, negativ = entladen |
| Netzleistung | W | positiv = Bezug, negativ = Einspeisung |
| Wechselrichterleistung | W | standardmäßig deaktiviert |
| PV-Energie | kWh | kumuliert, `total_increasing` |
| Hausverbrauch Energie | kWh | kumuliert |
| Netzbezug / Einspeisung Energie | kWh | kumuliert |
| Batterie Lade-/Entladeenergie | kWh | kumuliert |
| Online | — | Verbindung zum Portal |

Zusätzlich gibt es vorzeichenlose Leistungsvarianten (Ladeleistung, Entladeleistung,
Netzbezug, Einspeisung), die standardmäßig deaktiviert sind — praktisch für
Automationen ohne Template.

Die Energiezähler eignen sich unmittelbar für das Energie-Dashboard:

- **Netz** → Netzbezug Energie / Einspeisung Energie
- **Solar** → PV-Energie
- **Batterie** → Batterie Ladeenergie / Batterie Entladeenergie

## Installation

### HACS

1. HACS → ⋮ → *Benutzerdefinierte Repositories*
2. `https://github.com/treee111/hagerFlow` hinzufügen, Kategorie *Integration*
3. „Hager flow" installieren, Home Assistant neu starten

### Manuell

`custom_components/hager_flow/` nach `<config>/custom_components/` kopieren und
Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → Hager flow*

Zwei Angaben werden gebraucht:

**Seriennummer** — steht in der Titelzeile des Portals und in dessen URL,
eine zwölfstellige Zahl.

**Refresh-Token** — so kommst du dran:

1. [flow.hager.com](https://flow.hager.com) öffnen und anmelden
2. Entwicklertools öffnen (F12)
3. *Application* → *Local Storage* → `flow.hager.com`
4. Wert von `reAuthToken` kopieren (ohne die äußeren Anführungszeichen)

Das Token ist etwa **30 Tage** gültig. Läuft es ab, meldet Home Assistant das als
Reparatur und fragt über den normalen Reauth-Dialog nach einem neuen — die
Integration muss nicht neu eingerichtet werden.

## Funktionsweise

Das flow-Portal ist ein Frontend vor der E3/DC-Cloud. Die Integration meldet sich
mit dem langlebigen Refresh-Token an, holt daraus ein kurzlebiges Access-Token
(10 Minuten) und erneuert es selbstständig:

```
POST /auth-saml/re-auth   {"reAuthToken": "..."}  ->  {"token": "..."}
GET  /storages/{SN}/status                            Authorization: Bearer <token>
GET  /storages/{SN}/history-values/difference         kumulierte Zähler in Wh
```

Live-Werte werden alle 30 s abgefragt, die Energiezähler alle 5 Minuten — sie
bewegen sich ohnehin nur im 15-Minuten-Raster und hinken der Echtzeit um bis zu
etwa 17 Minuten hinterher. Für das Energie-Dashboard ist das unerheblich.

Batterie, Netz und Verbrauch werden je Phase gemeldet, PV je String; die
Integration summiert jeweils. Geprüft über die Energiebilanz, die exakt aufgeht:
PV plus Batterieentladung plus Netzbezug, abzüglich Ladung und Einspeisung,
ergibt exakt den Hausverbrauch.

## Bekannte Grenzen

- **Cloud-abhängig.** Ohne Internet oder bei Portal-Störung keine Daten. Lokal ist
  am Gerät weder ein RSCP-Schlüssel setzbar (kein Konfigurations-Webinterface) noch
  Modbus TCP freigeschaltet; beides kann der Hager-Support aktivieren.
- **Refresh-Token läuft nach ~30 Tagen ab** und lässt sich nicht automatisch
  erneuern, da der Refresh-Endpunkt kein neues zurückgibt.
- **Vorzeichen nicht endgültig verifiziert.** Die Referenzmessung entstand nachts
  bei 0 W PV und ~0 W Netz. Ob positiv bei der Netzleistung wirklich Bezug bedeutet,
  sollte einmal tagsüber bei Einspeisung gegen das Portal geprüft werden.
- **Nur lesend.** Keine Steuerung der Anlage.
- Undokumentierte API, die sich jederzeit ändern kann.

## Ausblick: offizielle API

Hager betreibt unter [developer.hagerenergy.com](https://developer.hagerenergy.com/)
eine offizielle, dokumentierte API (REST, OAuth 2, OpenAPI) mit Endpunkten für
Energieflüsse, Installationen und E-Mobilität. Laut Doku ist sie *„available to all
customers of E3/DC and Hager Flow"*; ein Self-Service-Zugang im Portal ist
angekündigt, aktuell gibt es nur Preview-Zugang auf Anfrage bei **api-team@e3dc.com**.

Sobald Zugang besteht, ist sie diesem Weg vorzuziehen: dokumentiert, stabil,
mit echtem OAuth-Refresh-Token statt 30-Tage-Ablauf. Der Backend-Zugriff ist
deshalb in `api.py` gekapselt, sodass eine zweite Implementierung danebengestellt
werden kann, ohne Koordinator oder Entitäten anzufassen.

## Tests

```bash
python3 tests/test_parse.py
```

Läuft ohne Zugangsdaten und ohne installiertes Home Assistant.

## Lizenz

MIT
