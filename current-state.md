# Current State

Snapshot taken **2026-09-19** against commit `8892b32`, after ~2.5 months of no
commits. Verified by building the tools container and running the full suite,
Ruff, and a live render — not by reading code alone.

## What this project is

A Home Assistant e-paper dashboard for a **Waveshare 7.5" B/V2** panel
(800×480, black/white/red), driven from a Raspberry Pi over GPIO/SPI.

A floorplan of the house is the background bitmap
(`assets/hass-dash-house.bmp`); live data is overlaid at fixed pixel
coordinates:

- per-room temperature and humidity (10 rooms)
- current weather with condition icon
- a 5-slot hourly forecast strip
- sunrise / sunset times

The deployment is Danish: `Europe/Copenhagen` is hardcoded in
[`src/localize.py`](src/localize.py), and room names are Danish.

## Health

| Check | Command | Result |
| --- | --- | --- |
| Tests | `make test` | **15 passed** in 0.13s |
| Ruff lint | `make lint` | All checks passed |
| Ruff format | `docker compose run --rm --entrypoint ruff tools format --check src/ tests/` | 22 files already formatted |
| CI | `.github/workflows/ci.yml` | Mirrors all three, on push / PR / manual dispatch |

Nothing has rotted during the dormancy. The containerized tooling still works
out of the box.

## The headline: it cannot actually run

The architectural refactor (`a8c9244`, `a5fbbec`) completed the new component
layer but never reconnected the runtime. Two independent gaps:

### 1. The Pi entry point has broken imports

Commit `a5fbbec` ("Ruff fixes and deletion of old") deleted `src/hass_weather.py`,
`src/hass_rooms.py`, and `src/hass_sun.py` — but two surviving files still
import them:

- [`src/epd_7in5b_V2_dash.py`](src/epd_7in5b_V2_dash.py) — the actual Pi entry point
- [`src/hass.py`](src/hass.py) — a demo runner

Both raise `ImportError` on startup. They are pre-refactor code that survived
the cleanup by accident.

### 2. Nothing wires up the new architecture

[`Dashboard`](src/dashboard.py) is a clean orchestrator, but no `main()`
anywhere constructs it with a `RealHASSClient`, a renderer, and the four
widgets. There is no CLI, no scheduling loop.

There is also **no `EPDRenderer`**.
[`PILRenderer`](src/rendering/renderer.py) is the only implementation of the
`Renderer` ABC, and it only saves a BMP to disk. `ARCHITECTURE.md` lists the
hardware renderer as a next step; it was never written. So the `Renderer`
abstraction currently has no path to the panel.

The panel is black/white/**red** capable, but the red channel is unused — the
old code passed a blank second buffer to `epd.display()`.

## Known bugs

### Night detection is inverted

[`src/components/sun_widget.py`](src/components/sun_widget.py) computes:

```python
self.is_night = self.sunrise > self.sunset
```

Home Assistant's `next_rising` and `next_setting` are **both future**
timestamps. During the day the next sunset comes first, so
`next_rising > next_setting` is true — and the widget reports night. The
condition is backwards.

The test that should catch this
([`tests/test_widgets.py::TestSunWidget::test_sun_night_detection`](tests/test_widgets.py))
only asserts `isinstance(is_night, bool)`, which is a no-op. The mock `sun.sun`
entity in [`src/core/hass_mock.py`](src/core/hass_mock.py) is also
self-inconsistent (`state: above_horizon` alongside `elevation: -26.44`), which
is why nothing looks wrong locally.

### Night icons are unreachable

`get_icon_for_condition(condition, is_night)` supports night variants, but:

- [`WeatherWidget`](src/components/weather_widget.py) never passes `is_night`
- [`WeatherForecastWidget`](src/components/weather_forecast_widget.py) takes it
  once at construction and never refreshes it

Nothing plumbs `SunWidget.is_night_time()` into either widget, so
`weather-night-partly-cloudy` never renders.

### Duplicate humidity sensor in room config

In both `rooms.yml` and `rooms.widget.yml`, `sophie` and `gang` point at the
same entity:

```yaml
sensor.0x5cc7c1fffede1ef5_humidity_9
```

Both rooms therefore display an identical humidity value. `sophie` plausibly
wants `_humidity_8`, but this needs confirming against the real sensor layout.

### `WeatherWidget.device_id` is accepted and ignored

The constructor takes `device_id`, then hardcodes `"weather.home"` in
`_fetch_data()`.

## Cruft to clear

- **`rooms.yml` is dead.** Superseded by `rooms.widget.yml`. It uses the old
  list format, omits domain prefixes, and contains malformed entries such as
  `entity_id: 10 (11)`. Nothing reads it.
- **`src/display.py` is dead.** Its `draw_*` functions are superseded by widget
  `render()` methods, and it loads fonts from `/usr/share/fonts`, which do not
  exist in the tools container. Its only importer is the broken EPD entry point.
- **`requirements.txt` is UTF-16 LE with CRLF line endings**, despite commit
  `8892b32`'s message about removing UTF-16 guardrails. `pip` copes with the
  BOM, but the file is invisible to `grep` and diffs badly.
- **`.gitignore` ends with `*.bmp`**, yet 33 BMP assets are tracked (they were
  force-added). Any new icon or background will be silently ignored by `git add`.

## Suggested first move

Closing the refactor is one focused task:

1. Write `EPDRenderer` against the existing `Renderer` ABC, wrapping
   `epd7in5b_V2.EPD`.
2. Add a `main()` that builds a `Dashboard` with `RealHASSClient` and the four
   widgets, reading `HASS_URL` / `HASS_TOKEN` from `.env`.
3. Rewrite `src/epd_7in5b_V2_dash.py` as a thin shell around that.
4. Delete `src/hass.py`, `src/display.py`, and `rooms.yml`.

That restores a runnable dashboard and drops roughly 350 lines. Fixing the
night-detection inversion — and giving it a test with assertions — is a small
independent change that can land first.

Per [`AGENTS.md`](AGENTS.md), run Ruff and the tests after every change, and
inspect `test_output.bmp` for anything touching rendering.
