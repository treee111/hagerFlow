# Hager flow for Home Assistant

[![HACS custom repository][hacs-badge]][hacs-url]
[![Release][release-badge]][release-url]
[![HACS validation][hacs-ci-badge]][hacs-ci-url]
[![hassfest][hassfest-badge]][hassfest-url]
[![License: MIT][license-badge]](LICENSE)

Home Assistant integration for the **Hager flow** battery storage system with PV
(E3/DC hardware underneath). Provides live power readings, battery state of charge
and cumulative energy counters — the latter ready to use in the energy dashboard.

> **Two ways in.** Preferred is Hager's official API at
> [developer.hagerenergy.com](https://developer.hagerenergy.com/): documented, and its
> credentials do not expire. The undocumented API behind the flow portal stays
> available for anyone without API access, at the price of a token that has to be
> replaced roughly every 30 days. Both produce the same set of entities.

## Entities

| Entity | Unit | Notes |
|---|---|---|
| Battery level | % | |
| Solar power | W | |
| House consumption | W | derived by the device, includes the inverter losses |
| Battery power | W | positive = charging, negative = discharging |
| Grid power | W | positive = import, negative = export |
| Inverter power | W | disabled by default |
| Solar energy | kWh | cumulative, `total_increasing` |
| House energy | kWh | cumulative |
| Grid import / export energy | kWh | cumulative |
| Battery charge / discharge energy | kWh | cumulative |
| Online | — | connection to the cloud |
| Solar forecast today / tomorrow | kWh | expected production, official API only |

Four of those differ depending on which backend is in use:

| Entity | official API | flow portal |
|---|---|---|
| Solar power | installation total | sum of the three string registers |
| Solar energy | gross DC yield, reported as such | the AC balance, derived — a few percent lower, and [here is why](#the-counters-are-ac-the-pv-power-register-is-dc) |
| Inverter power | not registered | sum of the AC phase registers |
| Solar forecast today / tomorrow | expected production in kWh | not registered |

Both report solar *power* on the DC side, before the inverter; only the counter
behind *Solar energy* differs.

The last two are not merely unavailable on the route that lacks them — they are not
created at all. Each backend declares what it can supply and the platforms register
only that, because an entity that could never hold a value is worse than an absent
one. Inverter power does exist on the official API's per-device measurements, which
are a separate request this integration does not make.

There are also unsigned power variants (charge power, discharge power, grid import,
grid export), disabled by default — handy for automations without templates.

The energy counters can be used directly in the energy dashboard:

- **Grid** → Grid import energy / Grid export energy
- **Solar** → Solar energy
- **Battery** → Battery charge energy / Battery discharge energy

## Installation

### HACS

[![Open your Home Assistant instance and open this repository inside HACS.][my-hacs-badge]][my-hacs-url]

The button adds this repository to HACS on the instance you are signed in to. By hand:

1. HACS → ⋮ → *Custom repositories*
2. Add `https://github.com/treee111/hagerFlow`, category *Integration*
3. Install "Hager flow", then restart Home Assistant

### Manual

Copy `custom_components/hager_flow/` into `<config>/custom_components/` and restart
Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up a new integration.][my-config-badge]][my-config-url]

Or by hand: *Settings → Devices & Services → Add Integration → Hager flow*. Either
way, pick one of the two routes.

### Official API (recommended)

Request access at [developer.hagerenergy.com](https://developer.hagerenergy.com/).
Self-service through the MyE3/DC portal is announced; until then Hager creates the
OAuth client on request. You receive a **client ID** and a **client secret** — enter
both, and the integration finds your installation itself. If the credentials cover
more than one, it asks which.

Client ID and secret do not expire. The integration derives a five-minute access
token from them and renews it on its own, so nothing has to be replaced by hand.

### flow portal

Needs no API access. Two values:

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

### Running both at once

Nothing stops you from adding the same installation twice, once per route, but the
two entries identify it differently — by serial number on the portal, by installation
id on the official API. Home Assistant therefore sees two devices with two full sets
of entities rather than recognising them as one. The entry title names the route, so
the two stay tellable apart.

Side by side the two agree on everything except the solar counter, which is the whole
point: same live power to the watt, same grid, house and battery counters to the
decimal, and a solar counter that sits a few percent higher on the official route
because it is the gross DC yield.

There is no automatic migration between the routes. To move an existing setup over
without losing its history:

1. Add the official route and let it run alongside for a while, comparing the two
2. Delete the old entry, which removes its entities but leaves their statistics
3. Rename the new entities from `..._2` back to the old entity ids, so they pick up
   those statistics again

Step 3 logs an error per entity, which is expected and harmless:

```
Cannot rename statistic_id `sensor.…_2` to `sensor.…`
because the new statistic_id is already in use
```

The *entity* is renamed all the same, and from then on it writes into the existing
series — which is exactly the point of renaming it. Only the short `..._2` series
recorded while both routes ran are left behind; clear those under *Developer tools →
Statistics*.

Step 3 then needs one correction, and only for the solar counter. Going from the AC
balance to the gross DC yield is a jump upwards of a few percent of everything
produced so far, and a `total_increasing` sensor reads a jump upwards as production —
so the energy dashboard would show one enormous solar hour. Wait until the hour
containing the jump has been compiled, which happens on the next full hour; before
that there is nothing to adjust and the attempt silently does nothing. Then use
*Adjust sum* on that hour, subtracting the difference between the two counters as
read at the same moment. What remains is the production that really happened in that
hour, so the figure is measured rather than estimated.

Purging the counter's statistics instead also works, at the price of its whole
history — which is a poor trade, because the old values are not wrong. They are the
AC yield, a different and equally valid quantity, so what the switch leaves behind is
a change of definition on one date rather than an error to be erased.

The other five counters need no such care: they carry the same values on both routes,
usually to the last decimal.

## How it works

Both backends normalise their own registers into one shared vocabulary, so the
coordinator and the entities never see which one is in use. `backend.py` states that
contract; `api.py` and `api_official.py` implement it.

Live values are polled every 30 s and the cumulative counters every 5 minutes. The
slower cadence for the counters is not a compromise: on both backends they only
advance on a 15-minute grid and lag real time by about 17 minutes anyway, so polling
them more often would just repeat the same numbers.

### Official API

An OAuth 2 client credentials grant against Hager Energy's identity provider, then
plain REST:

```
POST /realms/customer/protocol/openid-connect/token  grant_type=client_credentials
GET  /v1/installations                               discover the installation id
GET  /v1/installations/{id}/energy/current           live flows in W
GET  /v1/installations/{id}/energy/total             cumulative counters in Wh
```

The access token lives five minutes and the flow has no refresh token, so an expired
one is simply requested again. Responses are JSend-wrapped — the payload sits in
`data`.

The mapping is one to one. Nothing has to be derived, and no register name misleads:
`pvProduction`, `gridFeedIn`, `gridConsumption`, `consumption`, `batteryCharge` and
`batteryDischarge` all mean what they say. `pvProduction` in particular is the gross
DC yield, which the portal backend cannot report at all — there it has to be derived,
and what comes out is the AC balance, a few percent lower.

There is no online flag on `energy/current`; the reading carries a timestamp that
advances every 10 to 30 seconds, so a stale one is what marks the system offline.

#### Production forecast

```
GET /v1/installations/{id}/forecast/production/{YYYY-MM-DD}
```

Served for **today and tomorrow only** — any other date is refused with *"must be
either today or tomorrow"*. Hourly watt-hours, which the integration sums into the
sensor value and carries along as an `hourly` attribute, so the profile can be
charted without a second request. Polled hourly, and a failure is swallowed rather
than raised: losing the forecast must not take the live readings down with it.

The sensors deliberately have no state class. A forecast is not a measurement, and
letting it into long-term statistics would file predicted kilowatt-hours next to
metered ones.

There is a consumption forecast at `forecast/consumption` as well, but it answered
with an empty `values` list on the installation this was built against, so it is not
wired up. An empty day is treated as no reading rather than as a confident zero.

### flow portal

The flow portal is a frontend for the E3/DC cloud. The integration signs in with the
long-lived refresh token, derives a short-lived access token (10 minutes) from it and
renews that on its own:

```
POST /auth-saml/re-auth   {"reAuthToken": "..."}  ->  {"token": "..."}
GET  /storages/{SN}/status                            Authorization: Bearer <token>
GET  /storages/{SN}/history-values/difference         cumulative counters in Wh
```

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

#### The counters are AC, the PV power register is DC

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

For the energy dashboard the AC basis is the right one here, since every other
counter this backend reports is AC too. Just do not expect *Solar power* integrated
over a day to equal *Solar energy* — the difference is the inverter, not a bug.

None of this applies to the official API, which reports the gross DC yield as
`pvProduction` and needs no derivation at all.

## Known limitations

- **Cloud dependent.** No data without internet access or during a cloud outage.
  Locally the device offers neither a settable RSCP key (there is no configuration
  web interface) nor Modbus TCP; Hager support can enable either one.
- **The counters lag real time** by about 17 minutes and only advance on a 15-minute
  grid, on both routes, so a short window compared against live power will not
  balance. Over a few hours it does.
- **Read only.** This integration only reads. The official API does expose write
  endpoints — the grid feed-in limit, and wallbox controls once e-mobility goes live
  — but none of them are wired up here.

Only on the flow portal route:

- **The refresh token expires after ~30 days** and cannot be renewed automatically,
  because the refresh endpoint does not return a new one. The official API has no
  such limit.
- **The counter register names cannot be taken at face value** — see the table above.
  Upgrading from a version before this correction swaps grid import and export and
  raises the PV counter by the battery charge, so the long-term statistics of those
  three sensors are worth clearing once (*Developer tools → Statistics*); otherwise
  the old, wrong values stay in the energy dashboard.
- **Power and energy are measured on different sides of the inverter.** Solar power
  is DC, the counters are AC, and house power is a residual that includes the
  conversion losses — see [above](#the-counters-are-ac-the-pv-power-register-is-dc).
  Integrating a power entity will therefore not reproduce the matching counter, and
  the solar counter is the AC balance rather than the gross yield. This backend has
  no register for the DC yield; the official API reports it directly.
- **Do not derive counters from the `from` field** of `history-values/difference`.
  Its snapshots are unreliable — solar production appears to rise overnight. Only the
  `to` field is used, which is the current reading; Home Assistant computes the
  differences itself.
- Undocumented API that may change at any time.

## What the official API also offers

Not read by this integration yet: hourly, daily, weekly, monthly and yearly energy
history, per-device measurements including the inverter's AC output and per-string DC
input, and the PV configuration (installed capacity, feed-in limit). Wallbox endpoints
are announced but not live.

The per-device measurements are the interesting gap: they carry the AC output that
would fill *Inverter power* on this route, and the per-string DC input the portal
reports directly.

## Tests

```bash
python3 tests/test_parse.py
python3 tests/test_translations.py
```

Both run without credentials and without Home Assistant installed. The CI
additionally runs [hassfest](https://developers.home-assistant.io/docs/creating_integration_manifest)
and the HACS validation on every push.

## License

MIT

<!-- Badge definitions, kept out of the prose. -->
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://hacs.xyz/docs/faq/custom_repositories
[release-badge]: https://img.shields.io/github/v/release/treee111/hagerFlow?display_name=tag&sort=semver
[release-url]: https://github.com/treee111/hagerFlow/releases
[hacs-ci-badge]: https://github.com/treee111/hagerFlow/actions/workflows/validate.yaml/badge.svg
[hacs-ci-url]: https://github.com/treee111/hagerFlow/actions/workflows/validate.yaml
[hassfest-badge]: https://github.com/treee111/hagerFlow/actions/workflows/hassfest.yaml/badge.svg
[hassfest-url]: https://github.com/treee111/hagerFlow/actions/workflows/hassfest.yaml
[license-badge]: https://img.shields.io/badge/license-MIT-blue.svg
[my-hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-hacs-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=treee111&repository=hagerFlow&category=integration
[my-config-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[my-config-url]: https://my.home-assistant.io/redirect/config_flow_start/?domain=hager_flow
