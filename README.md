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

Run with coverage:
```bash
docker compose run --rm tools pytest tests/ --cov=src --cov-report=html
```

### Lint Code (ruff)

Check for linting issues:
```bash
docker compose run --rm --entrypoint ruff tools check src/ tests/
```

Fix linting issues automatically:
```bash
docker compose run --rm --entrypoint ruff tools check src/ tests/ --fix
```

Format code:
```bash
docker compose run --rm --entrypoint ruff tools format src/ tests/
```

### Makefile Shortcuts (macOS/Linux only)

If you're on macOS or Linux (or using WSL on Windows), you can use the Makefile for shortcuts:

```bash
make build     # docker compose build tools
make test      # docker compose run --rm tools pytest tests/ -v
make lint      # docker compose run --rm --entrypoint ruff tools check src/ tests/
make lint-fix  # docker compose run --rm --entrypoint ruff tools check src/ tests/ --fix
make format    # docker compose run --rm --entrypoint ruff tools format src/ tests/
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

## Architecture Notes

- This container is for development tooling (pytest, ruff, linting).
- Hardware-specific runtime access (GPIO/SPI/e-paper) is not expected to work inside the container by default.
- See [ARCHITECTURE.md](ARCHITECTURE.md) for design overview.