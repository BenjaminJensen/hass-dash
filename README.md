# Setup

The script uses the gpiozero and spi packages installed on the system.

## Development Workflow

All development tools (testing, linting) run in the Docker container to maintain consistency and avoid local setup issues.

### Build the Tools Container

```bash
docker compose build tools
```

### Run Tests (pytest)

```bash
docker compose run --rm tools pytest tests/ -v
```

Run a specific test class or test function:
```bash
docker compose run --rm tools pytest tests/test_widgets.py::TestRoomsWidget -v
docker compose run --rm tools pytest tests/test_widgets.py::TestRoomsWidget::test_rooms_render -v
```

Note: do not quote the pytest command. The `tools` service has no shell entrypoint, so a quoted command is passed to `exec` as a single filename and fails.

Run with coverage:
```bash
docker compose run --rm tools pytest tests/ --cov=src --cov-report=html
```

### Lint Code (ruff)

Check for linting issues:
```bash
docker compose run --rm --entrypoint ruff tools check src/ tests/ tools/
```

Fix linting issues automatically:
```bash
docker compose run --rm --entrypoint ruff tools check src/ tests/ tools/ --fix
```

Format code:
```bash
docker compose run --rm --entrypoint ruff tools format src/ tests/ tools/
```

### Makefile Shortcuts (macOS/Linux only)

If you're on macOS or Linux (or using WSL on Windows), you can use the Makefile for shortcuts:

```bash
make build     # docker compose build tools
make test      # docker compose run --rm tools pytest tests/ -v
make lint      # docker compose run --rm --entrypoint ruff tools check src/ tests/ tools/
make lint-fix  # docker compose run --rm --entrypoint ruff tools check src/ tests/ tools/ --fix
make format    # docker compose run --rm --entrypoint ruff tools format src/ tests/ tools/
make render    # render the recorded snapshot to screen.bmp
make clean     # Remove test outputs and caches
```

**On Windows PowerShell:** Use the `docker compose` commands directly (listed above). The Makefile is not available on Windows.

### Render the screen

The development target is a BMP on disk, not the panel (`INTENT.md` §7).
`tools/render_fixture.py` replays a recorded snapshot through the real
configuration, view and renderer and writes two files:

```bash
docker compose run --rm --entrypoint python tools tools/render_fixture.py
```

- `screen.bmp` — the three-colour composite. **This is the file to look at**
  when a change touches rendering. (`test_output.bmp` belongs to the legacy
  widget suite, which M10 deletes.)
- `screen-preview.bmp` — the black plane alone, which is everything a partial
  refresh can carry. Anything red is missing from it on purpose.

Both are gitignored. Useful flags: `--fixtures tests/fixtures/sets/hostile` to
render a house where every sensor is broken, and `--at 2026-09-19T12:32:00+00:00`
to pin the clock so two renders are byte-identical.

The tool validates the draw list before drawing anything and exits non-zero if
the layout breaks the refresh contract, so a bad update class fails here rather
than on the wall.

### Run the dashboard

`src/app.py` is the composition root: it builds the configuration, a source, the
view and a renderer, and drives the loop from the refresh policy. One frame and
exit:

```bash
docker compose run --rm --entrypoint python tools src/app.py --once
```

Or the loop, which is what runs on the wall:

```bash
docker compose run --rm --entrypoint python tools src/app.py --source hass
```

| Flag | Default | |
| --- | --- | --- |
| `--source fixture\|hass` | `fixture` | recorded payloads, or the live instance |
| `--target bmp\|epd` | `bmp` | a file on disk, or the panel — `epd` needs the Pi |
| `--once` | off | one cycle, then exit — with fresh state that is always a full refresh |
| `--out` | `screen.bmp` | where the BMP target writes; the preview goes beside it |
| `--state` | off | remember the last refresh here, so a restart cannot re-flash the panel |
| `--house`, `--fixtures`, `--env` | repository root | |
| `--verbose` | off | log every decision, including the ones to do nothing |

`--target epd` builds anywhere and only fails when it tries to draw: the
vendored driver claims GPIO pins the moment it is imported, so that import
waits for the first frame. In this container that first frame is an
`ImportError` and the process exits 1. Putting it on real hardware is
[`deploy/README.md`](deploy/README.md).

`--state` is off by default, and deliberately: a state file would make the
second `--once` in a row decide to do nothing, which is correct and useless
from a command whose job is to produce a BMP to look at. The deployment passes
it; a workstation does not.

It logs one `key=value` line per refresh — what class, why, how many regions
changed, and how long the write took — plus a line when a decision *not* to
refresh changes, so entering quiet hours is visible without a line every tick:

```
refresh=full reason=morning_cadence changed=53 source=hass:… target=bmp:screen.bmp ms=61
refresh=none reason=quiet_hours
```

The loop decides before it fetches. A tick that is not going to refresh never
asks Home Assistant anything, which is why a day of the loop is roughly 190
requests rather than 2880. If a fetch fails, the previous frame stays on the
glass with its original timestamp — the header ages visibly rather than putting
a fresh clock on stale readings (`INTENT.md` §2).

`--source hass` needs `HASS_URL` and `HASS_TOKEN`; see
[Capturing real Home Assistant data](#capturing-real-home-assistant-data) for
the `.env` format. A real environment variable wins over the file.

### On the Pi

The same program, with `--target epd` and a systemd unit in front of it. The
bring-up runbook — a fresh venv, the two credential traps the device survey
found, one frame to a file before any electricity, and what to look for in the
photograph — is [`deploy/README.md`](deploy/README.md). None of it can be
validated in this container, which is why it is a runbook and not a test.

### Local Python Environment (Optional)

For IDE support and local development, create a virtual environment:

```bash
python -m venv venv --system-site-packages
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

However, all commits and CI should use the containerized tools.

## Configuration

[`house.yml`](house.yml) is the single house configuration: which rooms exist,
what they are called, which Home Assistant entities back them, and what counts
as comfortable in each. Rooms appear on screen in the order they appear in the
file. It carries no pixel coordinates — layout is computed from a box model, and
the loader rejects coordinate keys by name.

A bad configuration is fatal and reports every problem at once:

```bash
docker compose run --rm tools python -c "import sys; sys.path.insert(0, 'src'); from config.loader import load_house; print(len(load_house().rooms), 'rooms')"
```

## Capturing real Home Assistant data

`tools/capture_snapshot.py` records one snapshot of the live instance into
`tests/fixtures/`, and writes a report auditing `house.yml` against what
actually exists — which entities are missing, which humidity sensor belongs to
which room, what can back the outdoor row, and what the forecast service
returns.

It runs **outside** the container, because the container cannot reach Home
Assistant. It only reads.

```bash
python3 tools/capture_snapshot.py
```

Credentials come from `.env` in the repository root (which is gitignored):

```
HASS_URL=http://homeassistant.local:8123
HASS_TOKEN=<long-lived access token from your HA profile page>
```

`HASS_URL` is the base only — **no `/api` suffix**. The source appends
`/api/states` itself, so a trailing `/api` produces `/api/api/states` and a 404
that looks like an empty instance. The pre-rewrite code wanted the suffix, so
an existing `.env` carried over from it needs editing.

Then read `tests/fixtures/capture_report.md`.

## Architecture Notes

- This container is for development tooling (pytest, ruff, linting).
- Hardware-specific runtime access (GPIO/SPI/e-paper) is not expected to work inside the container by default.
- See [ARCHITECTURE.md](ARCHITECTURE.md) for design overview.