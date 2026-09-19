# Intent

What this project is for, what it refuses to do, and the shape that follows from
both. This document is the arbiter. When code, `ARCHITECTURE.md` or a config
file disagrees with this file, this file is right and the other is stale.

Written 2026-09-19, superseding the floorplan-overlay design that preceded it.

Companion: [`HARDWARE.md`](HARDWARE.md) holds the panel and driver facts this
document reasons from.

---

## 1. The moment this serves

A family stands in the hallway at 07:20 on a Tuesday. Someone asks whether the
child needs rain trousers. Someone else wonders why the bathroom smells damp
again.

The dashboard answers both **without being asked, without being touched, and
without anyone taking out a phone.** It hangs on the wall and is simply true.

Two jobs, in priority order:

1. **Dress the family correctly.** Today's weather with enough depth to decide:
   what it feels like, not just what it is; the day's arc, not just this minute;
   whether rain is coming and when.
2. **Report the health of the house.** Every room's temperature and humidity at
   a glance, with anything abnormal visually shouting before anyone reads a
   number.

Everything else is a distraction. If a feature does not serve the hallway at
07:20, it does not belong on the screen.

## 2. Principles

**Glanceable beats complete.** The screen is read in two seconds from three
metres. A number nobody reads at that distance is clutter, no matter how
interesting it is. Hierarchy is enforced by size and weight, not by adding
labels.

**Red means *act*.** The panel has a third colour and it is a scarce resource.
Red is reserved for things a person should do something about: a room that is
too hot or too cold, humidity high enough to grow mould, rain that is actually
falling, the "you are here" marker on the day's curve. Red used decoratively
destroys red used semantically.

**Absence is a state, not a crash.** A dead Zigbee sensor, a Home Assistant
restart, an expired token, a renamed entity — none of these may blank the
screen or stop the loop. Missing data renders as a neutral placeholder and the
rest of the dashboard carries on. The last good frame is always better than no
frame.

**The panel is slow, so updating is a deliberate act.** Refreshing is not free
and not invisible. Every refresh is chosen, budgeted and justified. See §4.

**Home Assistant is a source, not a foundation.** HA is generous and
unstable — entity ids get renamed, attribute shapes change between releases,
the forecast API has already moved once. Nothing above the adapter layer may
know that Home Assistant exists.

**Danish, locally.** `Europe/Copenhagen`. Danish weekday and month names. Comma
as decimal separator (`23,1°`), dot as time separator (`14.32`). This is not a
localisation framework; it is one household's dashboard and the language is
baked in deliberately.

## 3. The screen

One screen, 800×480, black / white / red. The floorplan background is retired —
the layout is computed from a box model, not from pixel coordinates hand-tuned
against a bitmap.

```
┌────────────────────────────────────────────────────────────────┐
│ Lørdag 19. september                        OPDATERET 14.32    │  header, inverted
├───────────────────────────────┬────────────────────────────────┤
│   ☀☁      17°   Let regn      │  RUM              TEMP    RF   │
│           Føles som 15°       │  Stue           ▲ 23,1°   44 % │
│           18° / 9°            │  Køkken/alrum     22,4°   47 % │
├───────────────────────────────┤  Soveværelse      19,8°   41 % │
│ SOL OP  SOL NED  VIND         │  Stort bad        22,8°  [68 %]│
│ LUFTFUGT  TRYK   NEDBØR       │  … 10 rooms total …            │
├───────────────────────────────┤  Garage         ▼ 14,2°   58 % │
│ TEMPERATUR I DAG      9°–18°  │  Ude              11,6°   82 % │  inverted row
│      ╭──╮   ┆NU                ├────────────────────────────────┤
│  ╭───╯  ╰────╮                │  HUSET – 10 RUM   20,8°   49 % │
│ ▪  ▪        ▪ ▪  (nedbør)     │  TEMP MIN/MAX/SPREDN.          │
├───────────────────────────────┤  RF MIN/MAX/MED.               │
│ SØN MAN TIR ONS TOR FRE LØR   │                                │
└───────────────────────────────┴────────────────────────────────┘
```

**Left — weather, for dressing.** Condition icon, current temperature at the
largest size on the screen, condition text, apparent temperature, today's
high/low. Below it a six-slot strip: sunrise, sunset, wind, outdoor humidity,
pressure, precipitation. Below that today's temperature curve from 00 to 24
with a marker at now and precipitation as bars along the baseline. Below that
seven days: weekday, icon, high, low.

**Right — the house, for wellbeing.** One row per room: icon, name,
temperature, relative humidity. Rooms in a fixed, deliberate order; the outdoor
row sits last and is inverted so the eye reads it as "not part of the house".
Beneath, a summary block: room count, mean temperature, mean humidity, and the
min / max / spread that reveal whether the house is evenly heated.

**Where red is allowed.** Condition text when precipitation is occurring; the
precipitation value and bars; the now-marker on the curve; the alert arrow and
value on a room outside its comfort band; a humidity badge on a room above its
threshold. Nowhere else.

Comfort bands and humidity thresholds are configuration, per room. A bathroom
and a bedroom do not share a definition of "too humid".

## 4. The refresh contract

This is the part that constrains everything, so it is stated as a contract
rather than an aspiration.

Hardware facts and vendor warnings live in [`HARDWARE.md`](HARDWARE.md). The
ones that bind this contract:

- The panel is a **Waveshare 7.5" e-Paper HAT (B), revision V3**, 800 x 480,
  red/black/white. V3 is interface-compatible with V2, so `epd7in5b_V2.py` is
  the correct driver and no V3 driver exists.
- A full three-colour refresh takes **26 seconds**, with the black-white
  inversion flash.
- `display_Partial()` writes **only** the B/W plane (`0x13`). **There is no
  partial path to the red plane.** Partial and full need different init
  sequences, and partial x-windows snap to multiples of 8.
- **Minimum 180 s between refreshes** of any class - vendor floor.
- **At least one refresh every 24 h** - required against burn-in on
  three-colour panels.
- **Sleep between refreshes is mandatory.** Leaving the panel powered holds it
  at high voltage and causes damage that "cannot be repaired". Wake, init,
  write, sleep is the unit of work.
- **A full refresh is required after ~5 rounds of partial refresh**, or the
  image degrades.

**Therefore the renderer has two update classes, and the layout must declare
which one each region is eligible for.**

| Class | Colours | Cost | Carries |
| --- | --- | --- | --- |
| **Full** | black + red | **26 s**, visible flash | the whole frame |
| **Partial** | black only | ~1 s, quiet | regions that are provably red-free |

**Cadence.** The numbers sit deliberately inside the vendor limits rather than
being picked for feel:

- **Full refresh every 30 minutes**, tightened to every 15 during the morning
  window (roughly 06:00-08:30), when the dashboard is actually being read and
  dressing decisions are being made.
- **Partial refresh every 5 minutes** between full cycles, for the updated-at
  clock and any changed value in a red-free region.
- That yields **exactly 5 partials per full cycle** - the vendor's stated limit
  before a full refresh becomes necessary. The two rules coincide rather than
  conflict, which is why these numbers and not others.
- 5 minutes is also comfortably above the 180 s floor. Nothing may schedule
  closer than that, including manual and startup refreshes.
- **Sleep after every refresh**, without exception.
- Quiet hours overnight: no refresh at all. E-paper holds its image; the panel
  ages instead of informing nobody. The 24 h rule still binds - if quiet hours
  ever stretched that far, a single keep-alive full refresh wins.

**The consequences, accepted deliberately.**

*Red lags.* An alert that appears at 14:03 is not on the glass until the next
full cycle. A slowly-warming bathroom does not need second-level latency, and
the alternative is flashing the hallway wall every five minutes.

*The dashboard is never "live".* Twenty-six seconds of flashing, twice an hour,
is the entire budget. A feature that wants fresher data than that is asking for
the wrong device.

**A region's colour eligibility is a property of the layout, not a guess.** If a
region *could* render red for some input, it is full-only for all inputs. A
value crossing into alert state marks the frame full-dirty and waits.

## 5. The domain model

The internal model is the decoupling. It is plain dataclasses, no I/O, no HA
vocabulary, no PIL.

**`Room`** — the central concept. Every room has climate; some rooms have
devices.

- identity: key, display name, icon, display order
- climate: temperature, humidity, setpoint, heating action (heating / idle /
  off), each independently nullable
- comfort: the temperature band and humidity ceiling that decide alert state
- devices: an open list of `DeviceState` (lights, computers, appliances) with a
  kind, a name and an on/off/unknown state

**Devices are modelled from day one and rendered by nobody yet.** The mockup
has no room on screen for them; the adapter and model are built to carry them
so that adding a device row later is configuration plus a render function, not
a remodel.

**`Weather`** — condition, temperature, apparent temperature, high/low,
humidity, pressure, wind speed and bearing, precipitation.
**`HourlyPoint` / `DailyPoint`** — the curve and the seven-day strip.
**`SunTimes`** — sunrise, sunset, and a correctly-computed `is_night`.
**`HouseSummary`** — derived, not fetched: count, means, min, max, spread.

Every field is explicitly nullable. `None` is a first-class value that renders
as a placeholder.

> Note for the rewrite: the existing `SunWidget` computes `is_night` as
> `next_rising > next_setting`. Both are future timestamps, so that expression
> is true *during the day*. It is inverted, its test asserts only `isinstance(…,
> bool)`, and the mock entity is self-inconsistent (`above_horizon` with
> elevation −26). Night detection is a domain function with real assertions this
> time.

## 6. Boundaries

```
sources/   Home Assistant lives here and nowhere else.
           A port (Protocol) + a REST implementation + a fixture implementation.
           Fetches one snapshot per cycle; maps entity ids -> domain objects
           using house configuration; swallows and reports source failures.
             ↓  domain objects only
domain/    Pure dataclasses and pure derivations (summary, alert state,
           night detection). No I/O. Trivially testable.
             ↓  domain objects only
view/      Pure functions: domain -> a declarative draw list. Each item carries
           its primitive, its box, its colour, and its update class.
           No PIL, no hardware, no clock.
             ↓  draw list only
render/    Executes a draw list. BMPRenderer for development, EPDRenderer for
           the panel. Diffs successive draw lists to find dirty regions.
refresh/   The policy from §4: what to update, when, in which class.
app.py     Composition root and loop.
```

**The inversion from the current code.** Today each widget fetches its own data
and draws imperatively into a shared canvas. That makes partial refresh
impossible — you cannot know which pixels changed, or whether a region is
red-free, if drawing is a side effect. Layout therefore becomes a *value*: a
draw list you can diff, assert on in tests, and reason about without a display.

**Configuration** is one schema-validated house file mapping rooms to entity
ids, comfort bands and devices — replacing `rooms.yml` and `rooms.widget.yml`,
and carrying no pixel coordinates. Layout positions are computed, never
configured.

## 7. The development loop

Hardware is the last step, not the first.

- The default target is a BMP written to disk at 800×480, rendered in three
  colours so red placement can actually be judged by eye.
- A parallel mono preview shows what a partial-only refresh would show, so the
  §4 contract is visible during development rather than discovered on the wall.
- A fixture source replays recorded Home Assistant payloads, including the
  unpleasant ones: missing entity, `unavailable`, `unknown`, string where a
  float was expected, empty forecast.
- Layout is tested on draw lists, not pixels — assertions about content,
  position, colour and update class, which survive a font change.
- Everything runs in the tools container. Per `AGENTS.md`: Ruff and the
  relevant tests after every change; visual inspection of the rendered BMP for
  anything touching rendering. GPIO and SPI do not exist in the container and
  nothing in the test suite may assume they do.

## 8. Non-goals

Not interactive. No touch, no buttons, no web UI, no configuration screen.

Not a historian. Today's curve comes from the forecast provider; the dashboard
keeps no database and answers no questions about last week.

Not a general platform. One household, one language, one panel, one screen. No
theming, no plugin system, no multi-home support, no HA add-on packaging.

Not a control surface. It reports the house; it never commands it. No setpoint
changes, no switching lights.

Not complete. Ten rooms and one weather provider. Rooms the family does not ask
about do not go on the wall.

## 9. Decisions taken

| Decision | Rationale |
| --- | --- |
| Tiered refresh: red on a slow full cycle, B/W partials between | The only model that respects both the hardware's B/W-only partial path and the mockup's semantic use of red. Cost: red lags by up to one full cycle. |
| Greenfield `src/`; keep assets, vendored driver, Docker/Ruff/pytest/CI | The existing widget layer bakes in floorplan pixel coordinates and widget-owned fetching, both of which this design removes. Rewriting is cheaper than unpicking. |
| Retire the floorplan background | The new screen is tables and strips, which need a computed box model. `hass-dash-house.bmp` and `.xcf` stay in the repo, unused. |
| Model rooms fully, render climate only | The device model is cheap now and expensive to retrofit. Screen real estate for devices does not exist yet and is not invented speculatively. |

## 10. Cleared in the rewrite

`src/hass.py`, `src/display.py`, `src/epd_7in5b_V2_dash.py` (broken imports
since `a5fbbec`), `src/dashboard.py`, `src/components/`, `rooms.yml`,
`rooms.widget.yml`.

Also to be fixed while passing through: `requirements.txt` is UTF-16 LE with
CRLF and is invisible to `grep`; `.gitignore` ends with `*.bmp` while 33 BMP
assets are force-added and tracked, so every new icon is silently ignored by
`git add`.

## 11. Open questions

These block specific slices, not the architecture. Each needs an answer from
the live Home Assistant instance.

- **Duplicate humidity sensor.** `sophie` and `gang` both point at
  `sensor.0x5cc7c1fffede1ef5_humidity_9`. One is wrong; `_humidity_8` is the
  plausible candidate but needs confirming against the real sensor layout.
- **The outdoor row.** Which entity backs "Ude" — the weather provider, or a
  physical outdoor sensor?
- **Weather depth.** Apparent temperature, pressure, wind bearing and
  precipitation amount: are these attributes on the existing weather entity, or
  do they need separate sensors? `WeatherWidget` currently hardcodes
  `weather.home` while accepting and ignoring a `device_id`.
- **The seven-day strip** needs the daily forecast service, not the hourly one
  the current code calls.
- **Comfort bands.** Per-room temperature ranges and humidity ceilings need
  real numbers from the family, not defaults.
