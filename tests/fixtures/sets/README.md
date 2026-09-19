# Fixture sets

Each directory here is one complete recording: `states.json`,
`forecast_hourly.json` and `forecast_daily.json`, exactly the three files
`tools/capture_snapshot.py` writes. `FixtureSource` points at one of them.

`tests/fixtures/*.json` — one level up — is where the **real** capture lands.
These sets are the ones a real capture cannot give you.

## `nominal/`

**Synthetic.** Invented by the developer, not recorded, because the live
capture (PLAN.md slice 2.2) has not been run yet. Shapes follow the documented
Home Assistant payloads: a `climate` entity carrying `current_temperature`,
`current_humidity` and `hvac_action`; a `weather` entity whose state is the
condition; `sun.sun` with `next_rising` and `next_setting`; forecast entries
keyed `datetime` / `temperature` / `templow` / `precipitation`.

It is good enough to develop a layout against and it is **not evidence**. When
the real capture lands, the entity ids and the attribute set in it are the
truth, and anything here that disagrees is wrong.

## `hostile/`

Every unpleasant shape INTENT.md section 7 asks for, in one recording, because
these could never come off a live instance on the day you need them:

| Entity | What is wrong with it |
| --- | --- |
| `climate.…_7` (lille bad) | absent entirely — a renamed or deleted entity |
| `climate.…_9` (gang) | a string where a whole state object belongs |
| `climate.…_3` (marius) | `unavailable`, with `attributes: null` |
| `climate.…_5` (stort bad) | `unknown`, and `"unavailable"` inside the attributes |
| `climate.…_6` (køkken) | a dict where a temperature belongs; `hvac_action` is a number |
| `climate.…_4` (sune) | `"kold"` where a float belongs; no `hvac_action`, state `off` |
| `climate.…_10` (garage) | `true` where a float belongs; `hvac_action: preheating` |
| `climate.…_1` (soveværelse) | every attribute present and `null` |
| `sensor.…_humidity_2` | `"44,0"` — a decimal comma on the wire |
| `sensor.…_humidity_5` | `"72 %"` — the unit inside the value |
| `sensor.…_humidity_4` | the empty string |
| `weather.home` | `unavailable`, and almost no attributes |
| `sun.sun` | `next_rising` is prose, `next_setting` is null |

The forecasts are an empty hourly list and a daily list holding a bare string,
an entry of nulls and prose, and an entry with nothing but a date.

The whole set must produce a `Snapshot` and zero tracebacks. That is what
`tests/test_sources_fixture.py` asserts.
