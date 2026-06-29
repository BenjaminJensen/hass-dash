# Architectural Refactoring

This directory contains the refactored architecture for the Home Assistant e-paper dashboard.

## Structure

```
src/
├── core/
│   ├── hass_client.py      # Abstract HASS interface + real implementation
│   ├── hass_mock.py        # Mock HASS for testing
│   └── __init__.py
├── rendering/
│   ├── renderer.py         # Abstract renderer + PIL implementation
│   └── __init__.py
├── components/
│   ├── widget.py           # Base widget class
│   ├── weather_widget.py   # Weather component
│   ├── sun_widget.py       # Sun/sunrise/sunset component
│   ├── rooms_widget.py     # Rooms component
│   └── __init__.py
├── dashboard.py            # Main orchestrator
└── [legacy files...]       # Original code (to be refactored)

tests/
├── test_widgets.py         # Widget tests with mock data
└── __init__.py
```

## Key Design Principles

### 1. **Dependency Injection**
All components receive their dependencies (HASS client, renderer) in `__init__`, not as globals:
```python
widget = WeatherWidget(mock_hass, renderer)
```

### 2. **Abstract Interfaces**
Contracts defined with ABC (Abstract Base Classes):
- `HASSClient` - switch between real HASS or mock
- `Renderer` - switch between PIL (testing) or hardware
- `Widget` - base for all dashboard components

### 3. **Testability**
No external dependencies needed:
```python
mock_hass = MockHASSClient()
renderer = PILRenderer()
widget = WeatherWidget(mock_hass, renderer)
```

### 4. **Self-Contained Components**
Each widget owns:
- **Data fetching** from HASS
- **Caching** with TTL
- **Rendering** logic
- **Data accessors** for inspection

## Running Tests

All tools run in the Docker container for consistency.

### Build container
```bash
docker compose build tools
```

### Run pytest
```bash
docker compose run --rm tools pytest tests/ -v
```

Tests use fixtures for dependency injection and run with mock data (no HASS required).

### Lint and format with ruff
```bash
# Check for linting issues
docker compose run --rm --entrypoint ruff tools check src/ tests/

# Auto-fix issues
docker compose run --rm --entrypoint ruff tools check src/ tests/ --fix

# Format code
docker compose run --rm --entrypoint ruff tools format src/ tests/
```

**Note:** The `--entrypoint ruff` override is needed because the container's default entrypoint is bash.

### Shortcuts (macOS/Linux with make)
```bash
make build     # Build container
make test      # Run pytest
make lint      # Run ruff check
make lint-fix  # Run ruff check --fix
make format    # Run ruff format
```

See [Makefile](Makefile) for all available commands.

## Key Architecture Points

1. **Render implementation** - Enhance widget render() methods with better layout
2. **Hardware renderer** - Create EPDRenderer class for actual e-paper display
3. **Integration** - Migrate existing display.py logic to component render() methods
4. **Configuration** - Create a dashboard.yml for layout and positioning
5. **Scheduling** - Add async update loop for production runtime

## Migration from Old Architecture

### Old (Tightly Coupled)
```python
client = get_hass_client()
with Image.open(...) as im:
    draw = ImageDraw.Draw(im)
    weather_display(draw, client, hass_sun)  # Function takes multiple args
    room_display(draw, client)
```

### New (Decoupled)
```python
dashboard = Dashboard(renderer)
dashboard.add_widget(WeatherWidget(mock_hass, renderer))
dashboard.add_widget(SunWidget(mock_hass, renderer))
dashboard.run()  # Updates and renders all
```
