#!/usr/bin/env python3
"""Record one snapshot of the live Home Assistant instance, and audit house.yml.

Run this **outside** the tools container, from a machine that can reach Home
Assistant:

    python3 tools/capture_snapshot.py

It does two jobs. It writes recorded payloads to `tests/fixtures/` so the rest
of the project can be developed and tested against real data rather than
invented data. And it writes a report answering the open questions in
`INTENT.md` section 11: which humidity sensor really belongs to which room,
what can back the outdoor row, which weather attributes actually exist, and
what the daily forecast service returns.

It reads and never writes: only GET on states, and the forecast service, which
returns a response rather than changing anything. Nothing here touches the
panel.

Only the standard library is used for I/O, so no environment needs preparing -
except PyYAML, which the configuration loader needs.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "src"))

#: Domains worth recording whole, because they are what this dashboard is made of.
INTERESTING_DOMAINS = frozenset({"weather", "sun", "climate"})

#: Sensor device classes worth recording, for the same reason.
INTERESTING_DEVICE_CLASSES = frozenset({"temperature", "humidity", "pressure"})

#: The weather depth INTENT.md section 3 asks for, to check against reality.
WANTED_WEATHER_ATTRIBUTES = (
    "temperature",
    "apparent_temperature",
    "humidity",
    "pressure",
    "wind_speed",
    "wind_bearing",
    "precipitation_unit",
)


# --------------------------------------------------------------------------
# Talking to Home Assistant
# --------------------------------------------------------------------------


def read_env(path: Path) -> dict[str, str]:
    """A deliberately small .env reader: KEY=VALUE, # comments, optional quotes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")

    return values


def request(url: str, token: str, payload: dict | None = None) -> Any:
    """One authenticated request. POST when a payload is given, otherwise GET."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if data else "GET",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_states(base_url: str, token: str) -> dict[str, dict]:
    """Every entity the token can see, keyed by entity id."""
    raw = request(f"{base_url}/api/states", token)
    return {item["entity_id"]: item for item in raw if "entity_id" in item}


def fetch_forecast(base_url: str, token: str, entity_id: str, kind: str) -> list[dict]:
    """The hourly or daily forecast, dug out of whatever shape HA returns.

    `weather.get_forecasts` replaced the old `get_forecast` and nests its result
    under the entity id. The fallbacks below exist because this API has already
    moved once and may move again.
    """
    url = f"{base_url}/api/services/weather/get_forecasts?return_response=true"
    try:
        response = request(url, token, {"entity_id": entity_id, "type": kind})
    except urllib.error.HTTPError as error:
        print(f"  ! {kind} forecast failed: HTTP {error.code}", file=sys.stderr)
        return []

    service_response = response.get("service_response", response)
    entry = service_response.get(entity_id, service_response)
    forecast = entry.get("forecast") if isinstance(entry, dict) else None
    return forecast if isinstance(forecast, list) else []


# --------------------------------------------------------------------------
# Choosing what to keep, and reporting on it - pure, so it is testable
# --------------------------------------------------------------------------


def device_class(state: dict) -> str | None:
    return (state.get("attributes") or {}).get("device_class")


def friendly_name(state: dict) -> str:
    return (state.get("attributes") or {}).get("friendly_name", "")


def is_interesting(entity_id: str, state: dict) -> bool:
    """Whether an entity belongs in the recorded fixture.

    The whole instance is not recorded. This is a household's Home Assistant and
    the fixtures are committed; a dashboard about climate has no business
    keeping a copy of everyone's phone battery level.
    """
    domain = entity_id.split(".", 1)[0]
    if domain in INTERESTING_DOMAINS:
        return True
    return domain == "sensor" and device_class(state) in INTERESTING_DEVICE_CLASSES


def select_states(states: dict[str, dict], keep: set[str]) -> dict[str, dict]:
    """The interesting entities, plus everything the configuration names."""
    return {
        entity_id: state
        for entity_id, state in sorted(states.items())
        if entity_id in keep or is_interesting(entity_id, state)
    }


def labelled_refs(config: Any) -> list[tuple[str, str, Any]]:
    """Every reference in the file as (room, role, ref), so the table says who is broken."""
    rows: list[tuple[str, str, Any]] = []
    for room in config.rooms:
        for role in ("temperature", "humidity", "climate"):
            ref = getattr(room, role)
            if ref is not None:
                rows.append((room.name, role, ref))
        for device in room.devices:
            rows.append((room.name, f"device/{device.key}", device.source))
    rows.append(("-", "weather", config.weather))
    rows.append(("-", "sun", config.sun))
    return rows


def _line(room: str, role: str, ref: Any, state: dict | None) -> str:
    if state is None:
        return f"| {room} | {role} | `{ref}` | **MISSING** | | |"
    attributes = state.get("attributes") or {}
    value = attributes.get(ref.attribute) if ref.attribute else state.get("state")
    unit = attributes.get("unit_of_measurement", "")
    return (
        f"| {room} | {role} | `{ref}` | {value} | {unit} | {attributes.get('friendly_name', '')} |"
    )


def _count(number: int, singular: str, plural: str) -> str:
    return f"{number} {singular}" if number == 1 else f"{number} {plural}"


def build_report(
    config: Any,
    states: dict[str, dict],
    hourly: list[dict],
    daily: list[dict],
    captured_at: str,
) -> str:
    """The answers to INTENT.md section 11, as far as the wire can give them."""
    out: list[str] = [
        "# Capture report",
        "",
        f"Captured {captured_at} from the live Home Assistant instance by",
        "`tools/capture_snapshot.py`. This file answers the open questions in",
        "`INTENT.md` section 11 from the wire rather than from guesswork.",
        "",
        "## Entities named by house.yml",
        "",
        "Anything marked MISSING is a typo or a renamed entity, and the",
        "dashboard will show a placeholder for it forever.",
        "",
        "| Room | Role | Entity | Value | Unit | Name |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    rows = labelled_refs(config)
    missing: list[str] = []
    for room, role, ref in rows:
        state = states.get(ref.entity_id)
        if state is None:
            missing.append(f"{room} / {role}: `{ref}`")
        out.append(_line(room, role, ref, state))

    out += ["", f"**{len(missing)} of {len(rows)} configured entities are missing.**"]
    if missing:
        out += ["", "Resolve each against the inventories below:"]
        out += [f"- {entry}" for entry in missing]

    out += [
        "",
        "## Humidity sensors on the instance",
        "",
        "`rooms.widget.yml` pointed `sophie` and `gang` at the same sensor. Use",
        "the names below to settle which sensor belongs to which room.",
        "",
        "| Entity | State | Name |",
        "| --- | --- | --- |",
    ]
    for entity_id, state in sorted(states.items()):
        if device_class(state) == "humidity":
            out.append(f"| `{entity_id}` | {state.get('state')} | {friendly_name(state)} |")

    configured = set(config.entity_ids)
    out += [
        "",
        "## Temperature sensors the configuration does not use",
        "",
        "If one of these is outdoors, it should back the `ude` row instead of",
        "the weather provider.",
        "",
        "| Entity | State | Name |",
        "| --- | --- | --- |",
    ]
    for entity_id, state in sorted(states.items()):
        if device_class(state) == "temperature" and entity_id not in configured:
            out.append(f"| `{entity_id}` | {state.get('state')} | {friendly_name(state)} |")

    weather = states.get(config.weather.entity_id)
    out += ["", f"## Weather depth on `{config.weather.entity_id}`", ""]
    if weather is None:
        out.append("The configured weather entity does not exist.")
    else:
        attributes = weather.get("attributes") or {}
        out += ["| Attribute | Present | Value |", "| --- | --- | --- |"]
        for name in WANTED_WEATHER_ATTRIBUTES:
            present = "yes" if name in attributes else "**no**"
            out.append(f"| `{name}` | {present} | {attributes.get(name, '')} |")
        extra = sorted(set(attributes) - set(WANTED_WEATHER_ATTRIBUTES))
        out += ["", f"Other attributes present: {', '.join(f'`{k}`' for k in extra) or 'none'}."]

    for kind, forecast in (("hourly", hourly), ("daily", daily)):
        out += ["", f"## {kind.capitalize()} forecast", ""]
        if not forecast:
            out.append("Returned nothing. The strip that depends on it cannot be built yet.")
            continue
        keys = sorted({key for entry in forecast for key in entry})
        out += [
            f"{_count(len(forecast), 'entry', 'entries')}. Keys across all entries: "
            + ", ".join(f"`{key}`" for key in keys),
            "",
            "First entry:",
            "",
            "```json",
            json.dumps(forecast[0], indent=2, ensure_ascii=False),
            "```",
        ]

    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="Home Assistant base URL (default: HASS_URL from .env)")
    parser.add_argument("--token", help="long-lived access token (default: HASS_TOKEN from .env)")
    parser.add_argument("--out", type=Path, default=FIXTURES, help="where to write the fixtures")
    parser.add_argument(
        "--all", action="store_true", help="record every entity, not just the climate ones"
    )
    args = parser.parse_args(argv)

    env = read_env(REPO_ROOT / ".env")
    base_url = (args.url or env.get("HASS_URL") or "").rstrip("/")
    token = args.token or env.get("HASS_TOKEN") or ""

    if not base_url or not token:
        print(
            "Need a URL and a token. Put HASS_URL and HASS_TOKEN in .env, or pass\n"
            "--url and --token. The token is a long-lived access token from your\n"
            "Home Assistant profile page.",
            file=sys.stderr,
        )
        return 2

    try:
        from config.loader import ConfigError, load_house
    except ModuleNotFoundError as error:
        print(f"Missing dependency: {error.name}. Try: pip install pyyaml", file=sys.stderr)
        return 2

    try:
        config = load_house()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2

    print(f"Reading {base_url} ...")
    try:
        states = fetch_states(base_url, token)
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code} from /api/states - is the token valid?", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"Could not reach {base_url}: {error.reason}", file=sys.stderr)
        return 1

    print(f"  {len(states)} entities visible")
    hourly = fetch_forecast(base_url, token, config.weather.entity_id, "hourly")
    daily = fetch_forecast(base_url, token, config.weather.entity_id, "daily")
    print(f"  {len(hourly)} hourly and {len(daily)} daily forecast entries")

    kept = states if args.all else select_states(states, set(config.entity_ids))
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "states.json", kept)
    _write(args.out / "forecast_hourly.json", hourly)
    _write(args.out / "forecast_daily.json", daily)
    (args.out / "capture_report.md").write_text(
        build_report(config, states, hourly, daily, captured_at), encoding="utf-8"
    )

    print(f"  {len(kept)} entities recorded to {args.out}")
    print(f"Read {args.out / 'capture_report.md'} - it answers INTENT.md section 11.")
    return 0


def _write(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
