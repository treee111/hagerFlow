# Hager flow for Home Assistant

Home Assistant integration for the **Hager flow** battery storage system with PV
(E3/DC hardware underneath). Provides live power readings, battery state of charge
and cumulative energy counters — the latter ready to use in the energy dashboard.

> **Unofficial.** This integration uses the undocumented API behind the flow portal.
> Hager now offers an official one at [developer.hagerenergy.com](https://developer.hagerenergy.com/)
> — see [Looking ahead](#looking-ahead-the-official-api).

## Entities

| Entity | Unit | Notes |
|---|---|---|
| Battery level | % | |
| Solar power | W | sum of all strings |
| House consumption | W | |
| Battery power | W | positive = charging, negative = discharging |
| Grid power | W | positive = import, negative = export |
| Inverter power | W | disabled by default |
| Solar energy | kWh | cumulative, `total_increasing` |
| House energy | kWh | cumulative |
| Grid import / export energy | kWh | cumulative |
| Battery charge / discharge energy | kWh | cumulative |
| Online | — | connection to the portal |

There are also unsigned power variants (charge power, discharge power, grid import,
grid export), disabled by default — handy for automations without templates.

The energy counters can be used directly in the energy dashboard:

- **Grid** → Grid import energy / Grid export energy
- **Solar** → Solar energy
- **Battery** → Battery charge energy / Battery discharge energy

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories*
2. Add `https://github.com/treee111/hagerFlow`, category *Integration*
3. Install "Hager flow", then restart Home Assistant

### Manual

Copy `custom_components/hager_flow/` into `<config>/custom_components/` and restart
Home Assistant.

## Setup

*Settings → Devices & Services → Add Integration → Hager flow*

Two values are needed:

**Serial number** — shown in the portal title bar and in its URL, a twelve-digit
number.

**Refresh token** — how to get it:

1. Open [flow.hager.com](https://flow.hager.com) and sign in
2. Open the developer tools (F12)
3. *Application* → *Local Storage* → `flow.hager.com`
4. Copy the value of `reAuthToken` (without the surrounding quotes)

The token is valid for roughly **30 days**. When it expires, Home Assistant reports a
repair issue and asks for a new one through the regular reauth dialog — there is no
need to set the integration up again.

## How it works

The flow portal is a frontend for the E3/DC cloud. The integration signs in with the
long-lived refresh token, derives a short-lived access token (10 minutes) from it and
renews that on its own:

```
POST /auth-saml/re-auth   {"reAuthToken": "..."}  ->  {"token": "..."}
GET  /storages/{SN}/status                            Authorization: Bearer <token>
GET  /storages/{SN}/history-values/difference         cumulative counters in Wh
```

Live values are polled every 30 s and the energy counters every 5 minutes — the
latter only advance on a 15-minute grid anyway and lag real time by up to about
17 minutes. That is irrelevant for the energy dashboard.

Battery, grid and consumption are reported per phase and PV per string; the
integration sums each group. Verified against the energy balance, which adds up
exactly: solar plus battery discharge plus grid import, minus charging and export,
equals house consumption.

## Known limitations

- **Cloud dependent.** No data without internet access or during a portal outage.
  Locally the device offers neither a settable RSCP key (there is no configuration
  web interface) nor Modbus TCP; Hager support can enable either one.
- **The refresh token expires after ~30 days** and cannot be renewed automatically,
  because the refresh endpoint does not return a new one.
- **Signs not fully verified.** The reference reading was taken at night with 0 W
  solar and roughly 0 W grid. Whether a positive grid power really means import
  should be checked once during the day while exporting.
- **Read only.** No control over the installation.
- Undocumented API that may change at any time.

## Looking ahead: the official API

Hager runs an official, documented API at
[developer.hagerenergy.com](https://developer.hagerenergy.com/) (REST, OAuth 2,
OpenAPI) with endpoints for energy flows, installations and e-mobility. According to
the documentation it is *"available to all customers of E3/DC and Hager Flow"*;
self-service access through the portal is announced, and for now there is preview
access on request at **api-team@e3dc.com**.

Once access is granted it should be preferred over this route: documented, stable,
and with a proper OAuth refresh token instead of a 30-day expiry. That is why backend
access is isolated in `api.py`, so a second implementation can be added alongside it
without touching the coordinator or the entities.

## Tests

```bash
python3 tests/test_parse.py
python3 tests/test_translations.py
```

Both run without credentials and without Home Assistant installed. The CI
additionally runs [hassfest](https://developers.home-assistant.io/docs/creating_component_manifest)
and the HACS validation on every push.

## License

MIT
