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
make clean     # Remove test outputs and caches
```

**On Windows PowerShell:** Use the `docker compose` commands directly (listed above). The Makefile is not available on Windows.

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

Then read `tests/fixtures/capture_report.md`.

## Architecture Notes

- This container is for development tooling (pytest, ruff, linting).
- Hardware-specific runtime access (GPIO/SPI/e-paper) is not expected to work inside the container by default.
- See [ARCHITECTURE.md](ARCHITECTURE.md) for design overview.