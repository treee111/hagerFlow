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
| Solar power | W | sum of all strings, DC side |
| House consumption | W | derived by the device, includes the inverter losses |
| Battery power | W | positive = charging, negative = discharging |
| Grid power | W | positive = import, negative = export |
| Inverter power | W | disabled by default |
| Solar energy | kWh | cumulative, `total_increasing`, AC side |
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
integration sums each group.

The sign convention was verified against live readings in both directions — once
while importing and charging, once while exporting — and the power balance adds up
to the watt in both cases: solar plus battery discharge plus grid import equals house
consumption plus battery charging plus grid export. Inverting either sign throws the
balance off by hundreds of watts, so the mapping is unambiguous.

The cumulative counters need two corrections before they mean what their names
suggest, both established by integrating the live power over several hours and
comparing the result against the counter differences:

| Backend register | What it actually is |
|---|---|
| `NetIn` | grid **export** — the name is written from the grid's point of view |
| `NetOut` | grid **import** |
| `Production` | the balance *without* the battery, not the PV production |
| `Consumption`, `BatPowerIn`, `BatPowerOut` | as expected |

`Production` satisfies `Consumption + NetIn - NetOut` to the watt-hour at every
reading, which is why it keeps climbing overnight at roughly the house base load.
The integration therefore derives the PV counter as
`Production + BatPowerIn - BatPowerOut`.

That derivation makes the PV counter the balancing term, so the counters adding up
is true by construction and confirms nothing on its own. What pins the mapping down
is the comparison against the live power integrated over whole days: grid export,
grid import and both battery counters agree with it to well under one percent, and
swapping `NetIn` and `NetOut` puts grid import and export off by an order of
magnitude on a sunny day.

### The counters are AC, the PV power register is DC

The PV counter is the one place where that comparison does not land on the nose.
Integrated over a full day, the live `POWER_PV_S*` sum comes out a few percent
*above* the counter — consistently, and in the same proportion on days with very
different yields. That is not an error in the derivation; the two simply live on
opposite sides of the inverter:

- `POWER_PV_S1..S3` are **DC** string powers.
- Every cumulative counter, and therefore the derived PV counter as well, is **AC**.

The cross-check: the AC energy implied by the counters (`Consumption - NetOut +
NetIn`) matches the integrated `POWER_AC` register to about a percent, and dividing
it by the DC energy that passed through the inverter gives a plausible conversion
efficiency. The gap between the DC and the AC view is exactly that conversion loss.

House consumption inherits the same offset, because the device does not meter it —
it derives it as the residual of the live registers. That is why the live power
balance closes to the watt while `POWER_C_L*` integrated over a day exceeds the
`Consumption` counter by the *same absolute amount* that PV does. The live house
figure carries the inverter losses; the counter does not.

For the energy dashboard the AC basis is the right one, since every other counter is
AC too. Just do not expect *Solar power* integrated over a day to equal *Solar
energy* — the difference is the inverter, not a bug.

## Known limitations

- **Cloud dependent.** No data without internet access or during a portal outage.
  Locally the device offers neither a settable RSCP key (there is no configuration
  web interface) nor Modbus TCP; Hager support can enable either one.
- **The refresh token expires after ~30 days** and cannot be renewed automatically,
  because the refresh endpoint does not return a new one.
- **The counter register names cannot be taken at face value** — see the table above.
  Upgrading from a version before this correction swaps grid import and export and
  raises the PV counter by the battery charge, so the long-term statistics of those
  three sensors are worth clearing once (*Developer tools → Statistics*); otherwise
  the old, wrong values stay in the energy dashboard.
- **The counters lag real time** by up to about 17 minutes and only advance on a
  15-minute grid, so a short window compared against live power will not balance.
  Over a few hours it does.
- **Power and energy are measured on different sides of the inverter.** Solar power
  is DC, all energy counters are AC, and house power is a residual that includes the
  conversion losses — see [above](#the-counters-are-ac-the-pv-power-register-is-dc).
  Integrating a power entity will therefore not reproduce the matching counter.
- **Do not derive counters from the `from` field** of `history-values/difference`.
  Its snapshots are unreliable — solar production appears to rise overnight. Only the
  `to` field is used, which is the current reading; Home Assistant computes the
  differences itself.
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
