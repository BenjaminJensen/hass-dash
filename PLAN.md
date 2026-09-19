# Plan

How the dashboard described in [`INTENT.md`](INTENT.md) gets built, in the order
it gets built, with the reasoning for the order.

[`INTENT.md`](INTENT.md) is the arbiter of *what* and *why*; this file is only
*when* and *in what slice*. Where they disagree, `INTENT.md` wins and this file
is stale. [`current-state.md`](current-state.md) is a snapshot of the code as it
was before this plan and dies at M10.

---

## 0. Verified starting point

Checked on 2026-09-19 against `3bc2720`, by running the tools container, not by
reading:

| Check | Result |
| --- | --- |
| `docker compose run --rm tools pytest tests/ -q` | **15 passed** in 0.20 s |
| `docker compose run --rm --entrypoint ruff tools check src/ tests/` | All checks passed |
| `src/hass.py`, `src/epd_7in5b_V2_dash.py` | confirmed `ImportError` — import `hass_rooms` / `hass_weather` / `hass_sun`, all deleted in `a5fbbec` |
| `src/display.py` | only importer is the broken entry point above |
| Documented single-test command (quoted form) | **fails** — `exec: "pytest tests/…": no such file or directory`. The container has no `bash -lc` entrypoint any more (changed in `8892b32`); the unquoted form works |
| `PILRenderer` | mode `"1"` only — there is no red plane anywhere in the codebase |

So: the tooling is healthy, the test suite is green, and nothing in it exercises
a runnable dashboard. That is the ground this plan builds from.

## Strategy

**Strangler, not big-bang.** The new tree grows beside the old one. Every commit
leaves Ruff clean and the suite green. The old widget layer is deleted at M10,
when its replacement is on screen — not before, because it is the only thing
currently holding the suite up.

**Bottom-up, with one early vertical slice.** Domain first (no dependencies,
trivially testable), then sources and view in parallel, then render. But before
the screen is fully designed, M4 cuts a *walking skeleton* straight through all
the layers to produce one real BMP. The layout in `INTENT.md` §3 puts eleven
room rows plus a summary into roughly 400×446 px and claims readability at three
metres. That claim should be tested with real fonts in week one, not discovered
at M5.

**Hardware last, and full-refresh before partial.** Nothing in the test suite may
touch GPIO or SPI. Partial refresh is deferred to M9 on purpose — see the note
there; it may turn out not to be worth building.

**Blocked on a human, not on code:** the comfort bands (`INTENT.md` §11) need
real numbers from the family. Everything else in §11 is answered empirically by
slice 2.2.

## Milestones

**Progress:** M0 (`24927d4`), M1 (`a542a03`), M2 and M3 are done, on branch
`rewrite/intent-architecture`. M4 is next, and slice 2.2 is still waiting on
one command being run against the live instance.

| # | Milestone | Size | Depends on | Ends with |
| --- | --- | --- | --- | --- |
| M0 ✅ | Hygiene and ground clearing | S | — | Dead files gone, repo commands true |
| M1 ✅ | Domain core | M | M0 | Pure model + derivations, honestly tested |
| M2 ✅ | Config and captured ground truth | M | M1 | `house.yml` + recorded HA fixtures |
| M3 ✅ | Sources | M | M2 | HA behind a port, hostile inputs survived |
| M4 | Walking skeleton | M | M1 | **A real 800×480 three-colour BMP on disk** |
| M5 | Complete the screen | L | M4 | Every region of §3 rendered |
| M6 | Refresh policy | M | M1 | §4 contract as a pure, clock-injected function |
| M7 | App and composition root | S | M3, M5, M6 | `--source fixture --target bmp` runs the loop |
| M8 | Hardware, full refresh | M | M7 | On the wall |
| M9 | Partial refresh | M | M8 | Decided with numbers in hand |
| M10 | Retire the old, align the docs | S | M8 | One architecture, described accurately |

M3 and M4/M5 are independent after M2 and can be worked in either order — the
view layer is developed against hand-built domain objects, not against a source.

---

### M0 — Hygiene and ground clearing (S)

Cheap, and each item blocks something later.

- **0.1** Re-encode `requirements.txt` from UTF-16 LE/CRLF to UTF-8/LF. It is
  currently invisible to `grep` and diffs badly; every later slice that adds a
  dependency touches it. Rebuild the container to confirm `pip` is still happy.
- **0.2** `.gitignore` ends with `*.bmp`, while 33 BMP assets are tracked by
  force-add. M4 adds rendered output *and* possibly new icons. Keep output
  ignored, un-ignore the asset tree (`!assets/**/*.bmp`), and verify with
  `git check-ignore -v`.
- **0.3** Delete the files proven dead above: `src/hass.py`,
  `src/epd_7in5b_V2_dash.py`, `src/display.py`, `rooms.yml`. This removes the
  only Pi entry point, which is correct — it has not run since `a5fbbec` and
  `src/app.py` replaces it at M7. The widget layer, `dashboard.py` and
  `rooms.widget.yml` stay until M10; the suite still covers them.
- **0.4** Correct the single-test command in `AGENTS.md` and `README.md` to the
  unquoted form that actually works. *This edits the governing policy file, so
  it needs your nod rather than mine.*

**Done when:** 15 tests still green, Ruff clean, CI green, `~350` lines gone.

### M1 — Domain core (M)

`src/domain/`. Plain dataclasses and pure functions. No I/O, no PIL, no HA
vocabulary. Every field explicitly nullable.

- **1.1** `models.py` — `Room` (identity, climate, comfort band, devices),
  `DeviceState`, `Weather`, `HourlyPoint`, `DailyPoint`, `SunTimes`,
  `HouseSummary`, and a `Snapshot` that carries one cycle's worth of everything.
  Devices are modelled and rendered by nobody, per §5.
- **1.2** `derive.py` — `house_summary()` (count, means, min, max, spread),
  `alert_state(room)` (in-band / too cold / too hot, plus humidity ceiling), and
  `is_night(sun_times, now)`.
- **1.3** `format_da.py` — `23,1°`, `14.32`, Danish weekday and month names, and
  one canonical placeholder for `None`. Use `zoneinfo` rather than `pytz`;
  `localize.py` moves here and loses its `main()`.

**The night-detection bug is repaid here, not patched.** The existing widget
computes `next_rising > next_setting`, which is true *during the day*, and its
test asserts only `isinstance(x, bool)`. The new function gets cases for day,
night, either timestamp missing, and a DST changeover.

**Done when:** every derivation has a test that would fail if the logic were
inverted, and every model field has a `None` case.

### M2 — Configuration and captured ground truth (M)

- **2.1** `house.yml` — one schema-validated file: room key, display name, icon,
  display order, entity ids for temperature/humidity/climate, comfort band,
  humidity ceiling, optional devices. **No pixel coordinates.** Loader raises a
  clear, fatal error on a bad config; a bad config is a developer error, unlike
  a missing sensor, which is a normal runtime state.
- **2.2** `tools/capture_snapshot.py` — a one-shot script, run against the live
  HA instance *outside* the container, that dumps entity states and the hourly
  and daily forecasts to `tests/fixtures/`. This is the slice that answers
  `INTENT.md` §11: the duplicate `_humidity_9` on `sophie`/`gang`, what backs
  the "Ude" row, whether apparent temperature / pressure / wind bearing /
  precipitation exist as attributes, and what the daily forecast service
  actually returns. Answer them from the wire, not from guesswork.
- **2.3** Comfort bands per room — needs real numbers from the family. Ship
  defaults with an explicit `TODO` until they arrive; it blocks nothing except
  the truthfulness of the red.

**Done when:** loader tests cover a good config and several bad ones, and the
fixtures are committed.

### M3 — Sources (M)

`src/sources/`. The only place that knows Home Assistant exists.

- **3.1** `port.py` — a `Protocol` with one method: fetch one `Snapshot` per
  cycle.
- **3.2** `fixture.py` — replays the recorded payloads, including the unpleasant
  ones: absent entity, `unavailable`, `unknown`, a string where a float was
  expected, an empty forecast list.
- **3.3** `homeassistant.py` — the REST adapter. Maps entity ids to domain
  objects using the house config. Swallows and *reports* per-entity failure; a
  dead sensor yields `None`, never an exception.
- **3.4** A test asserting that no module outside `sources/` and `config/`
  references `homeassistant`, `entity_id` or an attribute name. §2's "HA is a
  source, not a foundation" is worth enforcing mechanically rather than by
  discipline. `config/` is exempt because mapping rooms to entity ids is what
  configuration *is* (§6); nothing it exposes reaches `domain/` or above.

**Done when:** every hostile fixture produces a `Snapshot` full of `None`s and
zero tracebacks.

### M4 — Walking skeleton (M)

The first slice you can look at. Deliberately narrow and deliberately early.

- **4.1** `src/view/drawlist.py` — `DrawItem` (primitive, box, colour, update
  class), `Box`, `Colour` (black/red/white), `UpdateClass` (full/partial).
  Invariants, asserted in tests: red implies full; a region that *could* be red
  for some input is full for *all* inputs (§4); a partial-eligible box has its
  x-edges on multiples of 8, because `display_Partial` floors `Xstart` and
  rounds `Xend` to byte boundaries.
- **4.2** `src/view/boxes.py` — the computed box model for 800×480. Header, left
  column, right column, and the nested boxes inside each.
- **4.3** Two regions only: the header, and the room table with its summary.
- **4.4** `src/render/bmp.py` — executes a draw list into two PIL `"1"` planes
  (black, red) and composites them into a three-colour BMP for the eye, plus a
  mono preview showing what a partial-only refresh would show.

**Done when:** a BMP exists, it has been looked at, and the eleven-row right
column is either legible at three metres or the box model has been adjusted
until it is. Per `AGENTS.md`, this is the inspection step, and it is the point
of putting this milestone this early.

### M5 — Complete the screen (L)

One pure `domain -> list[DrawItem]` function per region, each independently
tested: weather hero (icon, the largest number on the screen, condition text,
apparent temperature, high/low); the six-slot strip (sunrise, sunset, wind,
outdoor humidity, pressure, precipitation); today's curve 00–24 with the now
marker and precipitation bars; the seven-day strip; and `screen.py` composing
everything.

Tests assert content, position, colour and update class — not pixels, so they
survive a font change. One test walks the whole draw list and asserts red
appears **only** in the places §3 permits.

**Done when:** the fixture snapshot renders the full screen and it has been
inspected as a BMP.

### M6 — Refresh policy (M)

`src/refresh/policy.py` — a pure function of `(now, last_full, partials_since_full,
dirty regions, quiet hours)` returning *none / partial / full*. It encodes §4
exactly: 180 s hard floor between refreshes of any class; full every 30 min,
tightened to 15 min in the 06:00–08:30 window; 5 partials per full cycle; quiet
hours overnight; and the 24 h keep-alive that overrides quiet hours.

Tested against a frozen clock over a simulated 48 hours, including a DST
changeover and a quiet-hours boundary. No imports from `render/` and nothing
that knows a panel exists.

### M7 — App and composition root (S)

`src/app.py` — build config, source, view and renderer; drive the loop from the
policy. Flags: `--source fixture|hass`, `--target bmp|epd`, `--once`, `--out`.
`.env` for `HASS_URL` / `HASS_TOKEN`. Structured logging of what was refreshed
and why. Last-good-frame fallback, because §2 says a source failure may never
blank the screen.

**Done when:** `--source fixture --target bmp --once` renders the screen inside
the container, and the loop obeys M6 under a fast-forwarded clock.

### M8 — Hardware, full refresh (M)

- **8.1** `EPDRenderer` — wake, `init()`, `display(black, red)`, `sleep()`, as
  one indivisible unit of work, every cycle without exception. Both planes go
  through the driver's `getbuffer()`; the double inversion documented in
  `HARDWARE.md` §4 is respected, never reimplemented.
- **8.2** `epdconfig` is imported lazily inside the renderer, and a test asserts
  nothing under `tests/` can pull it in at module scope.
- **8.3** Pi bring-up: venv with system site packages, one render, photograph it,
  compare against the BMP.
- **8.4** systemd unit with a restart policy, and the last-refresh timestamp
  persisted to disk so a restart loop cannot violate the 180 s floor or lose the
  24 h keep-alive.

This is the milestone the container cannot validate. Its verification is manual
and will be reported as manual.

### M9 — Partial refresh (M) — decide, then build

**Do not build this before counting.** After M5, count the boxes that are
provably red-free for all inputs. Room temperature and humidity cells can go red
on alert, so they are full-only; the condition text, the precipitation value and
bars, and the now-marker are all red-eligible too. The honest expectation is
that partial refresh ends up carrying the updated-at clock and little else —
in exchange for a second init sequence, 8-pixel window snapping, and the
5-round degradation rule.

If the count justifies it: `init_part()` / `display_Partial()` against 8-aligned
windows, driven by diffing successive draw lists, with the partial counter
feeding M6's forced full refresh. If it does not: say so, keep the update-class
metadata in the draw list — it costs nothing and documents the constraint — and
leave the panel on a pure full-refresh cadence.

### M10 — Retire the old, align the docs (S)

Delete `src/components/`, `src/dashboard.py`, `src/localize.py`,
`rooms.widget.yml` and `tests/test_widgets.py`. Keep `assets/`, the vendored
`epd7in5b_V2.py` and `epdconfig.py`, and the Docker/Ruff/pytest/CI setup.

`ARCHITECTURE.md` currently documents the widget layer and becomes wrong the
moment M4 lands — rewrite it against the built architecture. Trim `README.md` to
the real development loop. Delete `current-state.md`; a dated snapshot that no
longer matches is worse than no snapshot. Add a fixture-render smoke step to CI.

---

## What §11's open questions block

| Question | Blocks | Answered by |
| --- | --- | --- |
| Duplicate `_humidity_9` on `sophie` / `gang` | Correct room humidity | 2.2 |
| What backs the "Ude" row | Room table's last row | 2.2 |
| Apparent temp / pressure / wind bearing / precipitation | The six-slot strip, the curve's bars | 2.2 |
| Daily forecast service shape | Seven-day strip | 2.2 |
| Comfort bands per room | Truthful red, not layout | The family (2.3) |

Four of the five collapse into one script. Only the comfort bands need a human.

## Risks

**The right column may not fit.** Eleven rows plus a summary in ~400×446 px, read
at three metres. M4 exists to find this out early; if it does not fit, the
options are fewer rooms on screen or a denser two-line layout, and that is a
decision for you, not a silent adjustment.

**Partial refresh may be nearly worthless here.** Stated fully at M9. Better to
find out from the region count than after building the second init path.

**Hardware cannot be validated in the container.** Everything up to M7 can be
proven in CI; M8 is a bench step, and the plan does not pretend otherwise.

**Icon assets are pre-rendered mono BMPs** at 50 and 100 px. They are fine for
the black plane; anything red is drawn, not iconified.

## Validation, per `AGENTS.md`

Run after **every** change, not on request:

```
docker compose run --rm --entrypoint ruff tools check src/ tests/
docker compose run --rm tools pytest tests/ -v
docker compose run --rm tools pytest tests/test_view_rooms.py -v   # unquoted; see 0.4
```

Anything touching rendering also gets its BMP looked at before it is called
done.

## Log

**M3** — `src/sources/`: a port, a fixture source, the REST adapter, and the
boundary test. +109 tests. Four decisions worth remembering:

*The two sources share one mapping.* `mapping.py` does every coercion and both
`fixture.py` and `homeassistant.py` feed it. Separate translations would mean
the fixture tests a mapping the wall never runs, which is the specific way a
fixture suite goes green while the real thing breaks.

*Per-entity failure and whole-source failure are different things.* A dead
sensor yields `None` and a line in `source_errors`; an unreachable instance
raises `SourceUnavailable` and the caller keeps its last good frame. Building a
snapshot full of confident placeholders out of a dead network would be a lie,
and M7's fallback needs the two told apart.

*`unavailable` is not an error and `"kold"` is.* A Zigbee sensor that has not
checked in is having an ordinary Tuesday and reporting it would fill the log
every night. A value that is *present but unparseable* is a shape change, which
is the class of surprise this layer exists to absorb, so it gets a line naming
the entity and the value. A missing entity gets one too: it means a rename, and
it shows a placeholder forever until a human fixes the config.

*The boundary test reads the AST, not the text.* `domain/models.py` says in
prose that it holds no Home Assistant vocabulary, and `homeassistant.py`
explains why it refuses to depend on `homeassistant_api`. A grep-based version
would fail on both. Naming the thing you refuse to depend on is not depending on
it. The legacy widget layer is exempted by an explicit file list rather than a
pattern, so M10's deletions make the list shrink instead of quietly widening.

Verified by deliberately leaking `hvac_action` into `domain/derive.py` and
watching the test name the file and the identifier, because a boundary test that
cannot fail is worse than no boundary test.

**The fixture sets are two, and only one of them is honest.**
`tests/fixtures/sets/hostile/` is thirteen entities broken thirteen different
ways and is the M3 exit condition. `tests/fixtures/sets/nominal/` is
**synthetic** — invented, because slice 2.2 has still not been run. Its shapes
follow the documented payloads and its values are guesses. When the real capture
lands it is the truth and anything in `nominal/` that disagrees is wrong.

**M2** — `house.yml`, `src/config/`, and `tools/capture_snapshot.py`. +141 tests
in the suite. Four decisions worth remembering:

*Display order is file order.* There is no `order:` key, and the loader rejects
one by name. Two places to state the same ordering is one place too many, and
the old file had both.

*Two rooms may not read the same entity.* This is now a fatal config error
rather than a curiosity. It is the `sophie` / `gang` bug from §11: one of those
rooms has been showing the other's air, and a schema that permits it would let
it happen again.

*A room that states a comfort band replaces the defaults outright* rather than
merging key by key, so `comfort: {}` is how the outdoor row opts out of being
judged. One place to read a room's real band.

*The capture tool records a filtered instance, not all of it.* The fixtures are
committed; a climate dashboard has no business keeping a copy of everyone's
phone battery. Climate domains and temperature/humidity/pressure sensors only,
plus anything the config names, with `--all` to override.

The tool's pure half — what to keep, what to report — is unit-tested, and the
whole thing was run end to end against a stand-in HTTP server, because the
first real run should not be the first run. What has *not* happened is a run
against the actual house; see "The next commit".

**M0** (`24927d4`) — `requirements.txt` re-encoded to UTF-8/LF, `.gitignore`
un-ignores `assets/**/*.bmp`, four dead files deleted (−490 lines), the broken
single-test command corrected in `AGENTS.md` and `README.md`. No behaviour
changed, because there was no runnable behaviour to change.

**M1** (`a542a03`) — the domain core, +950 lines and 72 new tests. Two
decisions worth remembering: `SunTimes` names its fields `next_rising` /
`next_setting` because the misleading names *were* the night-detection bug, and
`Room` carries `is_outdoor` because the "Ude" row sorts last and leaves the
house summary — a property of the model, not of each layout function.

Also pinned there: number formatting keeps Python's own round-half-even on
binary floats, so `1.15` renders as `1,1`. Invisible at three metres, and
imposing decimal rounding would buy nothing but a dependency.

## The next commit

**First, one command, by you:**

```bash
python3 tools/capture_snapshot.py     # outside the container; needs .env
```

Then read `tests/fixtures/capture_report.md` and commit the fixtures. That
settles four of the five open questions in `INTENT.md` §11 and unblocks the
weather half of M5. Until it has been run, three humidity entity ids and the
whole `ude` row in `house.yml` are marked UNCONFIRMED and are a guess.

M3 was built without it, against a synthetic fixture set, because the sources
layer needed hostile input far more than it needed real input — and the hostile
shapes were never going to come off a live instance anyway. That trade has one
open edge: `tests/fixtures/sets/nominal/` asserts attribute names this project
has never actually seen on the wire. `TestRecordedCapture` in
`tests/test_sources_fixture.py` **skips** today and starts checking every
configured entity against the instance the moment the capture exists.

Then M4 — the walking skeleton, which does not depend on anything still open.
