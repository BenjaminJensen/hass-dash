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
real numbers from the family. Slice 2.2 has now answered everything else — and
made the bands *more* urgent, not less: with the placeholder numbers, eight of
the eleven rooms render red. See the M2.2 log entry.

## Milestones

**Progress:** M0 (`24927d4`), M1 (`a542a03`), M2, M3, M4, M5, M6 and M7 are
done, on branch `rewrite/intent-architecture`. **M8 is complete and proven on
the panel:** 8.1, 8.2 and 8.4 are green in CI, and 8.3 was photographed on
2026-09-20 — the frame reached the glass, the red plane is red, and nothing is
inverted. Two things still wait on a human - slice 2.3's comfort bands, and the
viewing distance M4 measured - and with the panel now lit, both are the only
things between here and a wall that tells the truth.

| # | Milestone | Size | Depends on | Ends with |
| --- | --- | --- | --- | --- |
| M0 ✅ | Hygiene and ground clearing | S | — | Dead files gone, repo commands true |
| M1 ✅ | Domain core | M | M0 | Pure model + derivations, honestly tested |
| M2 ✅ | Config and captured ground truth (2.3 open) | M | M1 | `house.yml` + recorded HA fixtures |
| M3 ✅ | Sources | M | M2 | HA behind a port, hostile inputs survived |
| M4 ✅ | Walking skeleton | M | M1 | **A real 800×480 three-colour BMP on disk** |
| M5 ✅ | Complete the screen | L | M4 | Every region of §3 rendered |
| M6 ✅ | Refresh policy | M | M1 | §4 contract as a pure, clock-injected function |
| M7 ✅ | App and composition root | S | M3, M5, M6 | `--source fixture --target bmp` runs the loop |
| M8 ✅ | Hardware, full refresh | M | M7 | On the wall |
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

### M5 — Complete the screen (L) ✅

One pure `domain -> list[DrawItem]` function per region, each independently
tested: weather hero (icon, the largest number on the screen, condition text,
apparent temperature, high/low); the six-slot strip (sunrise, sunset, wind,
outdoor humidity, pressure, precipitation); the temperature curve with
precipitation bars; the day strip; and `screen.py` composing everything.

Tests assert content, position, colour and update class — not pixels, so they
survive a font change. One test walks the whole draw list and asserts red
appears **only** in the places §3 permits.

**Done when:** the fixture snapshot renders the full screen and it has been
inspected as a BMP. ✅ — see the log.

### M6 — Refresh policy (M) ✅

`src/refresh/policy.py` — a pure function of `(now, monotonic, state, dirty,
policy)` returning *none / partial / full* with the reason it chose. It encodes
§4 exactly: 180 s hard floor between refreshes of any class; full every 30 min,
tightened to 15 min in the 06:00–08:30 window; 5 partials per full cycle; quiet
hours overnight; and the 24 h keep-alive that overrides quiet hours.

Tested against a frozen clock over a simulated 48 hours, including a DST
changeover and a quiet-hours boundary. No imports from `render/` and nothing
that knows a panel exists.

**Done when:** the vendor's limits hold as invariants over a simulated two days,
not as assertions on one decision. ✅ — see the log.

### M7 — App and composition root (S) ✅

`src/app.py` — build config, source, view and renderer; drive the loop from the
policy. Flags: `--source fixture|hass`, `--target bmp|epd`, `--once`, `--out`.
`.env` for `HASS_URL` / `HASS_TOKEN`. Structured logging of what was refreshed
and why. Last-good-frame fallback, because §2 says a source failure may never
blank the screen.

**Done when:** `--source fixture --target bmp --once` renders the screen inside
the container, and the loop obeys M6 under a fast-forwarded clock. ✅ — see the
log.

### M8 — Hardware, full refresh (M) ✅

- **8.1** ✅ `EPDRenderer` — wake, `init()`, `display(black, red)`, `sleep()`, as
  one indivisible unit of work, every cycle without exception. Both planes go
  through the driver's `getbuffer()`; the double inversion documented in
  `HARDWARE.md` §4 is respected, never reimplemented.
- **8.2** ✅ `epdconfig` is imported lazily inside the renderer, and a test asserts
  nothing under `tests/` can pull it in at module scope.
- **8.3** ✅ Pi bring-up: a **fresh** venv, one render, photograph it, compare
  against the BMP. Done on 2026-09-20 against the live house; the runbook is
  `deploy/README.md` and the result is in the log below.
- **8.4** ✅ systemd unit with a restart policy, and the last-refresh timestamp
  persisted to disk so a restart loop cannot violate the 180 s floor or lose the
  24 h keep-alive. The floor is measured against a **monotonic** clock: the
  board has no RTC, so wall time jumps after a cold boot (`HARDWARE.md` §6).

This is the milestone the container cannot validate. Its verification is manual
and will be reported as manual.

**The target was surveyed on 2026-09-20 (`HARDWARE.md` §6), and most of 8.3's
unknowns are already discharged.** arm64 means Pillow installs from a wheel;
SPI is enabled and group-accessible without `sudo`; the time zone is already
`Europe/Copenhagen`; and the vendored driver has been run on the board and
clears the panel, which settles the wiring, the power and `gpiozero`'s pin
factory under Bookworm in one stroke. What the survey *added* to this
milestone:

- **Neither Python environment on the device is usable as-is.** The system
  interpreter has Pillow 9.4.0 but no PyYAML; the existing `~/py_envs` venv has
  neither, is built `include-system-site-packages = false`, and carries the
  `HomeAssistant-API` / `aiohttp` / `pydantic` stack that `sources/` was written
  to do without. 8.3 builds a new venv rather than reusing it.
- **The on-device checkout is dirty** — roughly 350 substantive uncommitted
  lines on `main`, over CRLF churn. It is all pre-rewrite work against the old
  coordinate-based `rooms.yml`, so nothing is at risk, but 8.3 clones fresh
  instead of pulling onto it.
- **A full desktop is running** — `lightdm`, X, CUPS, bluetooth, `wayvnc` —
  roughly a third of the 906 MiB. Not a blocker at 28 MB per frame, but it is
  the obvious reclaim if the appliance ever needs the memory, and
  `lightdm` plus `NetworkManager-wait-online` sit in front of anything 8.4 adds
  to boot.
- **`HASS_URL` must not end in `/api`.** The device's existing `.env` does;
  `HomeAssistantSource` appends `/api/states` itself, so that value produces
  `/api/api/states`. The old code wanted the suffix and the new code does not,
  which makes this a silent 404 on first run rather than a config error.

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

M8 built the seam either way. `EPDRenderer.partial_capable` is `False` and
`app.policy_for()` turns that into a cadence with no partial budget, so "no" is
already the shipped behaviour and "yes" is that flag, the second init path, and
a real diff in `render/`. Deciding not to build it changes no code.

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

**M8** — `src/render/epd.py`, `src/refresh/store.py`, `deploy/`. +184 tests,
**991 in the suite**. Three of the four slices are code and are green; the
fourth is a photograph nobody has taken yet. `--target epd` now builds
anywhere, refuses to pretend anywhere, and drives the panel only on the board.

**What is proven and what is not, stated plainly.** Proven in CI: the cycle is
init → display → sleep, every time, with sleep in a `finally`; both planes go
through the driver's own `getbuffer()`; a full-only cadence produces the same
**38 full refreshes a day** M6 and M7 counted, and zero partials; a restart
inherits the floor and the keep-alive, and a reboot does not inherit the
monotonic clock. **Proven on the glass on 2026-09-20 (8.3):** the red plane is
red and the black plane is black, so the two registers are not swapped; nothing
is inverted, which the white-on-black `Ude` row would have exposed first; and
the wiring in `HARDWARE.md` §5 is the wiring on the desk. The photograph was
taken a minute after a file render of the same house and differs from it
exactly where live data moved — `17.33` against `17.32`, `Stort bad` 24,4°
against 24,6° — so it is a fetch, not a replay.

**Five decisions worth remembering.**

*The target declares what it can do, and the cadence follows from that.* The
panel has no partial path to red at all, so pairing it with the default policy
would have filled every gap between full refreshes with decisions that end in
an exception. Instead `RenderTarget` grew `partial_capable`, `policy_for()`
turns a `False` into `Policy(max_partials=0)`, and `EPDRenderer.show()` refuses
a partial outright as a second line of defence. The rejected alternative was to
quietly promote a partial to a full refresh: that is 193 frames a day instead
of 38, **84 minutes of flashing instead of 16**, in a hallway. A budget of zero
is the honest way to say "this one cannot do partials"; a longer partial
interval would have said "it does them rarely", which is false.

*A failed `sleep()` is logged and swallowed; every other failure propagates.*
Sleep runs in a `finally` because §3's damage story is unrepairable and a panel
left powered is the way it happens. But after a failed `init()` the SPI device
was never opened, so `sleep()` raises too — and an exception from a `finally`
replaces the exception that caused it. The real failure is the one worth
keeping, so the cleanup's own failure gets a traceback in the log and nothing
else. A test drives exactly that pair and asserts which one survives.

*Importing the driver is not a declaration that hardware exists — it is a claim
on it.* `epd7in5b_V2` runs `epdconfig = RaspberryPi()` at module scope, which
takes five GPIO pins through `gpiozero` and opens `spidev`. So the import lives
inside one function, reached by `importlib` rather than an `import` statement,
and `tests/test_hardware_boundary.py` checks it from three sides: no module in
`src/` or `tests/` imports it at module scope, only `render/epd.py` names it at
all, and a **real interpreter** imports `app` and `EPDRenderer()` and reports
what came with them. The last one is the only one that could catch a transitive
import, which is the way this rule would actually be broken.

*A restart and a reboot are different, and `boot_id` is what tells them apart.*
`time.monotonic()` on Linux counts from boot, so its readings stay comparable
across a *process* restart and become meaningless across a *machine* one. The
state file records which boot wrote it; within that boot the readings are
restored and the second process waits for the cadence like any other tick,
which is what stops a crash loop spending 26 seconds of high voltage on every
restart. Across a boot they are dropped and the floor is **assumed rather than
calculated** — the first frame waits out a full 180 s, because after a reboot
no clock on the board can say how long ago the last refresh was, and the panel
is holding its previous image the whole time anyway. Where the downside is
unrepairable damage, three minutes of patience is the cheap side of the trade.
A reading from the *future* is treated as a different boot too: a forward-only
counter cannot produce one, so the file came from another machine, and
restoring it would park the floor beyond the end of time.

*SIGTERM becomes an exception, or the unit is the thing that damages the
panel.* systemd stops a service with SIGTERM and Python's default handler ends
the process where it stands — which, 12 seconds into a 26-second refresh, is a
panel left in a high voltage state with nothing to put it down. `main()`
installs a handler that raises instead, so the stop unwinds through
`EPDRenderer.show()`'s `finally`, and the unit's `TimeoutStopSec=45s` gives the
cycle time to finish first. This was not in the slice as written; it is the
part of "a systemd unit" that §3 makes load-bearing.

**`--state` is opt-in and has no default path, which is a deliberate
inconvenience.** A state file in the repository root would make the second
`--once` in a row decide to do nothing — correct behaviour, and useless from a
command whose entire job is to produce a BMP to look at. So the deployment
passes `--state` and a workstation does not, and `make run` behaves exactly as
it did at M7.

**A frame the wrong size is refused rather than drawn.** `getbuffer()` answers
a size it does not recognise with a warning and a blank buffer, which reaches
the wall as a cleared screen and leaves nothing in the log to explain it. That
is the worst failure mode available here — the screen's job is to be trusted at
a glance, and a blank one looks like a quiet house rather than a broken program
— so the planes are measured against `panel.width`/`panel.height` before the
panel is woken.

**Nothing new was rendered, and nothing needed to be.** `EPDRenderer` calls the
same `BMPRenderer.planes()` M4 built; the composite and its masks are the only
part it does not use. The fixture render was run and looked at anyway, to
confirm the frame is byte-for-byte the one M5 inspected. It is.

**M7** — `src/app.py`. +40 tests, **807 in the suite**. There is now one
program: `docker compose run --rm --entrypoint python tools src/app.py --once`
builds the config, fetches a snapshot, composes the screen, validates the draw
list and writes the BMP, and the same file with no `--once` drives the panel
from M6's policy until it is stopped.

**The loop reproduces M6's arithmetic exactly, which is the point of building
it separately.** Driven over a simulated day at a 30-second tick, the loop
performs **38 full refreshes and 155 partials** — the same numbers the policy's
own 48-hour simulation predicted, arrived at by a different route. M6 counted
decisions; this counts frames that reached a target, and they agree.

**Five decisions worth remembering.**

*Decide, then fetch — never the other way round.* The policy is a function of
two clocks and a small state, and §4 is explicit that it must not be a function
of the data: red lags on purpose. So a tick that is going to do nothing never
opens a socket. Over a day that is 2880 wakes and **193 requests**, instead of
2880 requests to be told 2687 times that nothing is happening — and it also
means the readings on the glass were taken in the same second as the refresh,
rather than up to thirty minutes before it.

*A stale frame keeps its own timestamp.* When the source is unreachable the
previous draw list is redrawn unchanged, header included, so the "opdateret
17.12" in the corner goes on saying 17.12 while the clock moves. Re-rendering
the last good snapshot with the current time was the alternative and it is the
one lie this screen must not tell: a fresh clock over stale readings is
indistinguishable, at three metres, from a house that has stopped changing. The
frame ages visibly instead, and a test asserts the draw list is byte-identical
across the outage.

*The composition root gets an exemption from the boundary test, two words
wide.* `app.py` has to import `sources/` and has to be able to spell
`--source hass`; selecting concrete implementations is the entire job of a
composition root and §6 puts it at the top of the diagram for that reason. So
the M3 boundary scan now excludes `app.py` from the general sweep and applies a
*narrower* rule to it: it may name the adapter, and every other piece of HA
vocabulary — `entity_id`, `current_humidity`, `unavailable` — still applies. The
rule caught a real leak while it was being written: a log line keyed
`unavailable=` on the source-failure path, which is a Home Assistant state value
that had wandered two layers up. It reads `down=` now.

*`record()` runs after the write, and the monotonic clock is read again there.*
A refresh that raised halfway through did not happen: it does not reset the
partial budget, does not move the keep-alive, and does not advance the floor.
Taking a second monotonic reading after `show()` returns also puts the floor's
180 seconds where they belong — counted from when the panel *finished*, which
for a full refresh is 26 seconds after it started. A test drives a target that
fails every cycle and asserts the loop keeps treating the next frame as the
first one.

*"Why not" is logged on change, not on every tick.* A NONE decision every 30
seconds would bury the refreshes the log exists to explain, and logging nothing
would make "the screen stopped updating at 22:00" unreconstructable. So a
decision not to refresh is logged when the *reason* changes — one line entering
quiet hours, none while sitting in them. Source errors get the same treatment,
which turns "this is still broken" into "this broke" and "this was fixed".

**The dirty set is still the placeholder, and it is doing no harm.** Every
region of the last frame, split by the update class the layout declared for it,
rather than a diff of two draw lists. It over-reports, and the direction of the
error is the safe one: a region called dirty that did not change costs a redraw
inside a refresh that was going to happen anyway. M9 replaces it with a real
diff in `render/`, where §6 says it belongs.

**`--target epd` is accepted by the parser and refused by the builder,** with a
message naming M8. The flag is in the CLI now so that M8 is a new class and one
line in `build_target()`, and an honest refusal beats a stub that pretends to
drive a panel.

**Rendered and looked at.** `--once` against the recorded house produces the
same frame M5 inspected — the app changed who calls `screen()`, not what it
draws — with the header now stamped by the live clock instead of a pinned one.

**M6** — `src/refresh/policy.py`. +57 tests, **767 in the suite**. §4 is now a
pure function of two clocks and a small state, and the vendor's limits are
invariants asserted over a simulated two days rather than assertions about one
decision.

**The day it produces, counted rather than imagined.** From midnight, with the
default policy: **38 full refreshes and 155 partials** — the first frame, then
silence until 06:00, ten fifteen-minute cycles through the morning window, then
half-hourly until 21:45 and quiet again. That is **988 seconds of flashing per
day**, a little over sixteen minutes, which is the entire budget §4 spends to
keep the wall true.

**Five decisions worth remembering.**

*Two clocks, and each rule takes the one it is entitled to.* The plan's
signature was `(now, last_full, …)`; it is `(now, monotonic, …)` instead,
because the board has no RTC and `HARDWARE.md` §6 is explicit about the
consequence. Durations — the 180 s floor, the 30- and 15-minute cycles, the
5-minute partial — are counted on a monotonic clock, so a wall-time jump can
neither permit a refresh inside the vendor floor nor stall the panel. Times of
day — quiet hours, the morning window — are read off wall time, which is what
wall time is for. The 24 h keep-alive is the one duration measured on the wall
clock, deliberately: it is the rule that has to survive a reboot, and a
monotonic clock restarts at zero while a persisted timestamp does not. Two
tests drive the split from both sides — a backwards jump that must not defeat
the floor, and an NTP landing that must fire the keep-alive exactly once
instead of a storm.

*The first frame is always full, including at 03:00 and including after a
restart that has the timestamp on disk.* Not because quiet hours are negotiable
but because a partial refresh writes changed regions onto whatever the panel is
already holding, and a process with no previous frame has no diff to write. The
floor still applies to it, which is what stops M8.4's restart loop.

*A sixth partial is refused, not promoted to an early full.* The vendor rule is
about performing partials, not about sitting on them, so the honest answer to a
spent budget is to wait — and by construction the next full is at most one
partial interval away, because §4's "exactly 5 partials per full cycle" is
`full_interval == (max_partials + 1) × partial_interval` and that arithmetic is
now a test.

*Red lagging is asserted, not argued.* Two 48-hour runs, identical but for a
permanently alerting room, produce byte-identical refresh timings. §4 accepts
that a room crossing into alert waits for the next full cycle; this is the
version of that sentence that fails if someone later makes dirty full-only
regions urgent.

*One consistency check was deleted for being unfalsifiable.* `policy_violations()`
holds §4's prose as arithmetic — nothing may schedule inside the floor, the
morning window may only tighten, the budget is the vendor's five. A check that
quiet hours could not "swallow" the keep-alive failed its own test and turned
out to be unprovable-by-construction: the keep-alive is decided *before* quiet
hours, so no night can starve it. It was replaced by a test that demonstrates
the rule order doing that job, with quiet hours stretched to 23 of the 24 hours.

**One number §4 does not fix, chosen here.** The contract says quiet hours are
"overnight" and stops. They are **22:00–06:00**, ending exactly where the
morning window begins so the two tile with no gap and no minute belonging to
both. It errs towards the panel ageing rather than towards informing a dark
hallway, and it is one line in `Policy` if the family disagrees.

**Nothing was rendered, so nothing was looked at.** Per `AGENTS.md` this is the
milestone with no visual verification step: the policy imports no PIL, touches
no draw list and produces no pixels.

**M5** — `src/view/weather.py`, `src/view/forecast.py`, `src/view/icons.py`,
the left column's box model, and four new derivations. +175 tests, **706 in the
suite**. Every region of `INTENT.md` §3 is on the glass, and both the dry
capture and the wet synthetic set have been rendered and looked at.

**The design works, and the wet frame is the proof.** Rendered against the
recorded house — a dry, grey Saturday — the frame spends red in 19 regions, all
but one of them a room alerting against a placeholder comfort band. Rendered
against the rainy `nominal` set, it spends red in **six**: the condition text
(`Regn`), the precipitation value, the bars under the curve, one cold room and
one humid bathroom. That second frame is what §2 asks for — red meaning "act",
and meaning it rarely. The first frame is what slice 2.3 costs.

**Three answers the capture forced, taken here.**

*Apparent temperature is computed.* `weather.home` publishes no
`apparent_temperature`, so §3's "Føles som 15°" is derived in
`domain/derive.py` from the temperature, humidity and wind it does publish,
using the Bureau of Meteorology formula. A source that ever starts publishing
one wins over the arithmetic, and any missing input yields no number at all
rather than a "feels like" built from two thirds of one.

*The curve is the next 24 hours, and the now-marker is gone with it.* The
hourly forecast starts at the current hour, so the curve *begins* at now and a
marker on its left edge would be decoration — which §2 says destroys red used
semantically. The hours are labelled every six instead. §3 has been amended.

*The day strip is six days.* This provider returns six.

**Four decisions worth remembering.**

*The draw list grew a `LINE` primitive, and it has to stay inside its box.* A
temperature curve is not expressible as a rectangle, so `LINE` is the one
primitive carrying geometry of its own. `violations()` therefore checks that
every point lies inside the item's box: a region is a refresh window, and ink
outside the window is ink nothing will ever repaint.

*The curve plots on a 16-pixel step, not on `width // 23`.* The step is what
makes every sixth point land on a multiple of 8, which is what lets the hour
labels hanging off those points be partial-eligible boxes at all. An arbitrary
step would have quietly made the axis full-only.

*The whole plot is one full-only region.* The temperature line is black and the
precipitation bars are red and they share a rectangle. One region is one update
class, and there is no partial path to red — so the line waits for the full
cycle too. It costs nothing: a forecast that moved in the last five minutes was
not worth redrawing.

*Widths are tested, not eyeballed.* A fit test measures the longest string each
style can produce against the box it has to fit — and it caught a real defect
before the BMP did: `Føles som -12°` overflowed its cell by four pixels, which
would have clipped on exactly the winter night nobody stands close enough to
guess at a half-word. The hero's split is now set by those two numbers.

**Partial refresh gained ground, and it is still not obviously worth building.**
The split moved from 33/25 at M4 to **53 partial-eligible against 28 full-only**
on the same recorded frame. The whole weather column rides a partial refresh
except three regions — the condition text, the precipitation slot and the plot.
But the full-only 28 are still the ones that matter to a person walking past,
and the M9 decision is unchanged in shape: partial carries the clock, the
labels, the summary and now the forecast, and not one room reading.

**M4** — `src/view/`, `src/render/`, `tools/render_fixture.py`. +170 tests,
531 in the suite. A real 800×480 three-colour BMP exists, it has been looked at,
and it answered the question the milestone was placed this early to ask.

**The right column fits, and three metres does not.** This is the risk the plan
named, and the numbers are now in hand rather than estimated. Eleven rooms plus
a column header and a summary cap the row at 30 px, which caps the value font at
a 17 px cap height — 3,5 mm on a panel whose dot pitch is 0,205 mm.

| Distance | Cap height | Verdict |
| --- | --- | --- |
| 1,0 m | 12,0 arcmin | comfortable, including the summary statistics |
| 1,5 m | 8,0 arcmin | readable at a glance |
| 2,0 m | 6,0 arcmin | marginal — the red is what carries, not the digits |
| 3,0 m | 4,0 arcmin | **below the 20/20 threshold of 5 arcmin** |

Working backwards instead: a comfortable 10–12 arcmin at three metres needs a
43–51 px cap height, so a 63–75 px row, so **six or seven rows fill the entire
panel** — with no header, no summary, and no weather column. `INTENT.md` §3 puts
weather on the left half as priority one, so three metres and eleven rooms
cannot both be true on a 7,5" panel. The layout was pushed to the largest type
the space allows; the remaining lever is content, not typography.

**So: a decision for you, not a silent adjustment.** Either the hallway
distance becomes ~1,5 m, or the room table sheds rows. Nothing downstream was
blocked by it — M5 filled the left column either way — but it should be settled
before M8 puts it on a wall.

**Red is not scarce today, and that is slice 2.3.** The recorded snapshot draws
red in 18 regions across 9 of the 11 rooms. Rendered, it is a wall of red boxes,
which is `INTENT.md` §2's failure mode stated exactly: red used everywhere is
red used nowhere. The layout is correct and the numbers are placeholders. This
is now visible rather than arithmetic.

**Partial refresh can carry more than expected — and still not much.** The
region count M9 has to be decided on, from the live snapshot: **33 regions are
partial-eligible, 25 are full-only.** But the split is not where it looked: the
full-only 25 are exactly the room value cells and alert markers, and the
partial-eligible 33 are names, labels, rules, the outdoor row, the summary block
and the clock. So a partial refresh can carry the whole house summary and the
updated-at time, and none of the individual room readings. `test_view_screen.py`
pins those counts so they cannot drift unnoticed.

**The Pi is not the constraint, and it is worth saying so now.** The target was
surveyed over SSH after M4 landed: a **Raspberry Pi 3 Model B Rev 1.2** —
1,2 GHz Cortex-A53, **906 MiB of RAM**, arm64 Bookworm, Python 3.11.2. Not the
3B+ with 2 GB assumed while M4 was being built; the correction makes the
margins smaller, not tight. Measured in the container: 0,2 ms to turn a
snapshot into a draw list, 12 ms to execute it into the two planes, 3 ms to
composite — 28 MB peak RSS for the whole process, against roughly 600 MB free
on the device. Even at ten times slower on the A53, a frame costs well under a
second against a panel that takes 26. The composite and its two masks are the largest
allocation and exist only for the BMP target: `EPDRenderer` will take
`planes()` straight to `getbuffer()` and never build them. Nothing here needs a
lighter representation, and the SD card sees no writes per cycle once the target
is the panel rather than a file.

Four decisions worth remembering:

*A region is a refresh window, and one window is one update class.* Items carry
a region name, `violations()` rejects a region that mixes classes, and
`inconsistent_regions()` takes the draw lists of many inputs and names any
region whose class depends on the data. That last one is how §4's "if a region
could be red for some input, it is full-only for all inputs" became a test
rather than a discipline — `TestTheRefreshContract` drives the room table over
comfortable, too hot, too cold, too humid, both and missing, and asserts nothing
moved.

*The inverted outdoor row is reported, never judged.* White text on black has
nowhere to put red, so the layout does not colour that row by alert state — and
that is exactly why it is the one row whose values a partial refresh can carry.
It matches the configuration, where `ude` opts out of a comfort band with
`comfort: {}`. Written down in `view/rooms.py` because a band set on an inverted
row would otherwise be computed and silently ignored.

*A rule is drawn on the edge of its box, not given thin geometry.* Every
partial-eligible box has to be byte-aligned on x, and a two-pixel-wide box can
never be. So the column divider is an eight-pixel box carrying a two-pixel rule.
The refresh window is the layout's business; the thin geometry is the
renderer's.

*Text is placed from the font's metrics, not from its own ink extent.* Centring
on ink drops "23,1" a pixel below "Stue" and the whole table ripples. Two tests
hold it: one that two descender-free strings share a baseline, and one that the
comma in "23,1" hangs below that baseline instead of moving it.

**And a documentation defect this surfaced.** `HARDWARE.md` §4's table said
`display()` writes `0x10` for black and `0x13` for red, and two paragraphs later
that `display_Partial()` writes `0x13` and has no path to red. Both are accurate
readings of the vendored driver and together they are confusing: partial mode is
entered via `0x91` and pre-fills `0x10` blank, and the driver's own comment on
that write reads "Write Black and White image to RAM". Same register, different
role by mode. `HARDWARE.md` now says so, and flags it as a bench check before
M9 builds anything on it. Nothing in `render/bmp.py` depends on the resolution.


**2.2 — the capture, run 2026-09-19 against the live instance.** All 24
configured entities exist; the three `UNCONFIRMED` humidity ids and the `ude`
row were all guessed correctly, and those markers can come out of `house.yml`.
Six findings the wire settled, four of which change later milestones:

*Every climate entity reports the same humidity.* All ten report
`current_humidity: 72.0` — one house-wide average broadcast on every channel —
while the per-room sensors read 64 to 75. The source layer's humidity fallback
to the thermostat was therefore **removed**: it would have put the house average
in a room's row and called it that room's air, which is the `sophie` / `gang`
bug wearing a different hat. Temperature still falls back, because
`current_temperature` genuinely differs per room (23,0 to 25,2) and is the only
temperature source — no room names a temperature sensor.

*Wind arrives in km/h.* `format_da.wind_speed()` renders m/s, so 23 km/h would
have been drawn as `23,0 m/s` — a storm rather than a stiff breeze, on a screen
whose job is deciding a coat. The source now normalises via `wind_speed_unit`,
and an unrecognised unit yields `None` rather than a number a factor of 3,6 out.

*`apparent_temperature` does not exist on this instance.* §3's "Føles som 15°"
has no source. `dew_point`, `cloud_coverage`, `uv_index` and `wind_gust_speed`
*are* present. Either the slot gets computed from temperature, wind and
humidity, or §3 loses it. **Answered at M5: computed.** See the M5 log.

*The daily forecast returns six days, not seven.* §3's seven-day strip can only
be a six-day strip from this provider.

*The hourly forecast starts at the current hour* and runs 48 h forward. §3 asks
for "today's curve from 00 to 24"; the first half of today is simply not in the
payload. The curve is a *next-24-hours* curve, or it needs history from the
recorder API.

*There is an outdoor sensor, and it is broken.*
`sensor.ude_sensor_ude_temperature` reads 23,2° against the forecast's 17,7°,
and `…_ude_humidity` has been pinned at exactly 100,0 since 2026-09-09. The
`ude` row correctly stays on the weather provider.

**And the finding that blocks nothing but matters most:** with the placeholder
comfort bands, **eight of the eleven rooms draw red** — the house sits at 64-75
% RH against a 60 % ceiling, and at 23-25 °C against a 24 °C ceiling. Red used
everywhere is red used nowhere (§2). Slice 2.3 is now the difference between a
dashboard that shouts once and one that shouts always.

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

**M8.3 happened on 2026-09-20, and the runbook survived contact.**
[`deploy/README.md`](deploy/README.md) was followed as written — fresh clone
beside the dirty on-device checkout, venv with `--system-site-packages` against
`deploy/requirements-device.txt`, one frame to a file before any electricity,
then one frame to the panel. Both credential traps were real and both were
handled: the revoked token was reminted, and `HASS_URL` is now refused at
startup with the corrected URL in the message rather than 404-ing as a broken
instance. One piece of friction, since fixed: the runbook cloned beside the old
checkout under a different name while `deploy/hass-dash.service` hardcodes
`/home/ben/hass-dash`. Resolved by taking the name instead — the pre-rewrite
tree is now `~/hass-dash-old` — which surfaced a second trap worth recording. A
venv stores its own absolute path in `pyvenv.cfg`, `bin/activate` and every
console-script shebang, and none of them follow a `mv`; `bin/python` does
survive, because it resolves its prefix from its own location, so the
dashboard and the unit keep working while `bin/pip` silently stops executing.
The runbook now says to build the venv where it will live, and to delete and
rebuild it if the directory ever moves.

The photograph answered three of its four questions and confirmed the fourth
was never about the panel. Red is red and black is black, so the `0x10`/`0x13`
registers are not swapped. Nothing is inverted — the white-on-black `Ude` row
is the tell, and it reads correctly, so the double inversion stayed where it
belongs. And the five red rooms are the placeholder comfort bands, exactly as
predicted from the file render, not the house being uncomfortable.

The fourth question — legibility from where people stand — cannot be answered
by a photograph taken at desk distance. It is still the M4 question and it is
now the last thing before the panel is hung.

**Two answers from you. Both block the screen being true, and one now blocks
the wall:**

*The comfort bands (slice 2.3).* Real numbers from the family, per room. This
is now the last thing between the screen and truthful red, and M5 has made the
cost of not having them unmistakable: side by side, the recorded house draws red
in 19 regions and the rainy synthetic house draws it in six. The difference is
not the weather, it is that one of them has honest thresholds. Until these are
real, every red mark on the wall is guesswork wearing the one colour reserved
for "act".

*The viewing distance, or the room count.* See the M4 log. Eleven rooms are
comfortable at ~1,5 m and unreadable at 3 m, and no amount of typography changes
that on a 7,5" panel. Either the stated distance moves or the table sheds rows.

*This is now the more urgent of the two, and it is the only thing left before
the panel is hung.* 8.3 proved the frame reaches the glass; it could not prove
the glass is readable from a hallway, because it was photographed on a desk.
It costs nothing to move a decision that is about a hallway; it costs a layout
change to discover it from the hallway.

**Then M9, and it should be decided before it is built.** The region count from
M5 stands: 53 partial-eligible against 28 full-only, and the full-only 28 are
every room reading on the screen. M8 has now put the panel on a full-only
cadence and a day of it costs 16 minutes of flashing, so the question M9 has to
answer is narrower than it was — not "is partial refresh worth building" but
"is carrying the clock, the labels and the forecast worth a second init path,
8-pixel window snapping, and the `0x13` question `HARDWARE.md` §4 flags for the
bench". If the answer is no, `partial_capable` stays `False`, the update-class
metadata stays where it is, and that is the whole of M9.
