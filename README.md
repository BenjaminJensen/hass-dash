# Setup

The script uses the gpiozero and spi packages installed on the system.

## Local Python Environment

```bash
python -m venv mv --system-site-packages
source mv/bin/activate
pip install -r requirements.txt
```

## Containerized Tooling (Ruff, pre-commit, etc.)

If your you do not have the toolstack localy , use the Docker tooling container.

1. Build the tooling image:

```bash
docker compose build tools
```

2. Run Ruff checks in the container:

```bash
docker compose run --rm tools "ruff check ."
```

3. Run Ruff format check in the container:

```bash
docker compose run --rm tools "ruff format --check ."
```

4. Run pre-commit in the container:

```bash
docker compose run --rm tools "pre-commit run --all-files"
```

Notes:
- This container is for development tooling and linting.
- Hardware-specific runtime access (GPIO/SPI/e-paper) is not expected to work inside the container by default.