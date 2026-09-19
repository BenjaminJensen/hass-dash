"""Read and validate `house.yml`.

A bad configuration is a developer error, so it is fatal and loud: the loader
collects *every* problem it can find and raises one `ConfigError` listing them,
rather than stopping at the first and making the file surrender its mistakes one
round-trip at a time.

This is the opposite of how missing *data* is treated. A sensor that returns
nothing is a normal runtime state and renders as a placeholder (INTENT.md
section 2); a room that names an entity that cannot exist is a typo, and the
dashboard should refuse to start rather than quietly show a placeholder forever.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from config.house import DeviceConfig, EntityRef, HouseConfig, RoomConfig
from domain.models import ComfortBand

#: Repository root / house.yml, resolved from this module's location.
DEFAULT_HOUSE_PATH = Path(__file__).resolve().parents[2] / "house.yml"

#: `domain.object_id`, as Home Assistant slugifies them: lowercase and digits.
ENTITY_ID = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")

#: Room keys are used as dictionary keys and in test names, so keep them plain.
ROOM_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

TOP_LEVEL_KEYS = frozenset({"weather", "sun", "defaults", "rooms"})
ROOM_KEYS = frozenset(
    {
        "key",
        "name",
        "icon",
        "is_outdoor",
        "temperature",
        "humidity",
        "climate",
        "comfort",
        "devices",
    }
)
DEVICE_KEYS = frozenset({"key", "name", "kind", "entity_id"})
COMFORT_KEYS = frozenset({"min_temperature", "max_temperature", "max_humidity"})
REF_KEYS = frozenset({"entity_id", "attribute"})

#: Keys that used to mean something and now mean a stale file.
RETIRED_KEYS = {
    "position": "layout is computed from a box model; coordinates are no longer configuration",
    "x": "layout is computed from a box model; coordinates are no longer configuration",
    "y": "layout is computed from a box model; coordinates are no longer configuration",
    "order": "rooms are shown in the order they appear in this file",
}


class ConfigError(Exception):
    """One or more problems with the house configuration."""

    def __init__(self, source: str, problems: list[str]):
        self.source = source
        self.problems = tuple(problems)
        listed = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{source} is not a valid house configuration:\n{listed}")


def load_house(path: str | Path | None = None) -> HouseConfig:
    """Read, parse and validate the house configuration."""
    location = Path(path) if path is not None else DEFAULT_HOUSE_PATH

    try:
        text = location.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(str(location), ["the file does not exist"]) from None
    except OSError as error:
        raise ConfigError(str(location), [f"the file could not be read: {error}"]) from None

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(str(location), [f"the file is not valid YAML: {error}"]) from None

    return parse_house(data, source=str(location))


def parse_house(data: Any, source: str = "house.yml") -> HouseConfig:
    """Validate an already-parsed mapping. `load_house` is the usual entry point."""
    errors: list[str] = []

    if data is None:
        raise ConfigError(source, ["the file is empty"])
    if not isinstance(data, dict):
        raise ConfigError(source, ["the top level must be a mapping"])

    _reject_unknown(data, TOP_LEVEL_KEYS, "top level", errors)

    weather = _required_ref(data.get("weather"), "weather", errors)
    sun = _required_ref(data.get("sun"), "sun", errors)
    defaults = _defaults(data.get("defaults"), errors)
    rooms = _rooms(data.get("rooms"), defaults, errors)

    if errors:
        raise ConfigError(source, errors)

    return HouseConfig(weather=weather, sun=sun, rooms=rooms)


def _reject_unknown(mapping: dict, allowed: frozenset[str], path: str, errors: list[str]) -> None:
    for key in mapping:
        if key in allowed:
            continue
        if key in RETIRED_KEYS:
            errors.append(f'{path}: "{key}" is no longer configuration - {RETIRED_KEYS[key]}')
        else:
            errors.append(f'{path}: unknown key "{key}"')


def _ref(value: Any, path: str, errors: list[str]) -> EntityRef | None:
    """An entity reference, written either as a bare id or as a mapping."""
    if isinstance(value, str):
        if not ENTITY_ID.match(value):
            errors.append(f'{path}: "{value}" is not an entity id (expected "domain.object_id")')
            return None
        return EntityRef(entity_id=value)

    if isinstance(value, dict):
        _reject_unknown(value, REF_KEYS, path, errors)
        entity_id = value.get("entity_id")
        if not isinstance(entity_id, str) or not ENTITY_ID.match(entity_id):
            errors.append(f"{path}.entity_id: missing or not an entity id")
            return None

        attribute = value.get("attribute")
        if attribute is not None and (not isinstance(attribute, str) or not attribute):
            errors.append(f"{path}.attribute: must be a non-empty string when given")
            return EntityRef(entity_id=entity_id)

        return EntityRef(entity_id=entity_id, attribute=attribute)

    errors.append(f"{path}: must be an entity id, or a mapping with entity_id and attribute")
    return None


def _required_ref(value: Any, path: str, errors: list[str]) -> EntityRef:
    if value is None:
        errors.append(f"{path}: required")
        return EntityRef(entity_id="")
    ref = _ref(value, path, errors)
    return ref if ref is not None else EntityRef(entity_id="")


def _number(value: Any, path: str, errors: list[str]) -> float | None:
    # bool is an int in Python and "max_humidity: yes" is a mistake, not a 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path}: must be a number")
        return None
    return float(value)


def _comfort(value: Any, path: str, errors: list[str]) -> ComfortBand | None:
    """A comfort band. Absent means "inherit the defaults"; empty means "no band"."""
    if value is None:
        return None
    if not isinstance(value, dict):
        errors.append(f"{path}: must be a mapping")
        return None

    _reject_unknown(value, COMFORT_KEYS, path, errors)

    bounds: dict[str, float | None] = {}
    for key in ("min_temperature", "max_temperature", "max_humidity"):
        raw = value.get(key)
        bounds[key] = None if raw is None else _number(raw, f"{path}.{key}", errors)

    low, high = bounds["min_temperature"], bounds["max_temperature"]
    if low is not None and high is not None and low > high:
        errors.append(f"{path}: min_temperature {low} is above max_temperature {high}")

    ceiling = bounds["max_humidity"]
    if ceiling is not None and not 0 <= ceiling <= 100:
        errors.append(f"{path}.max_humidity: {ceiling} is not a relative humidity (0-100)")

    return ComfortBand(min_temperature=low, max_temperature=high, max_humidity=ceiling)


def _defaults(value: Any, errors: list[str]) -> ComfortBand:
    if value is None:
        return ComfortBand()
    if not isinstance(value, dict):
        errors.append("defaults: must be a mapping")
        return ComfortBand()

    _reject_unknown(value, frozenset({"comfort"}), "defaults", errors)
    return _comfort(value.get("comfort"), "defaults.comfort", errors) or ComfortBand()


def _devices(value: Any, path: str, errors: list[str]) -> tuple[DeviceConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return ()

    devices: list[DeviceConfig] = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{item_path}: must be a mapping")
            continue

        _reject_unknown(raw, DEVICE_KEYS, item_path, errors)
        key = _text(raw.get("key"), f"{item_path}.key", errors)
        name = _text(raw.get("name"), f"{item_path}.name", errors)
        kind = _text(raw.get("kind"), f"{item_path}.kind", errors)
        source = _required_ref(raw.get("entity_id"), f"{item_path}.entity_id", errors)

        if key and name and kind:
            devices.append(DeviceConfig(key=key, name=name, kind=kind, source=source))

    return tuple(devices)


def _text(value: Any, path: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: required, and must be a non-empty string")
        return None
    return value


def _room(raw: Any, index: int, defaults: ComfortBand, errors: list[str]) -> RoomConfig | None:
    path = f"rooms[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{path}: must be a mapping")
        return None

    _reject_unknown(raw, ROOM_KEYS, path, errors)

    key = _text(raw.get("key"), f"{path}.key", errors)
    if key is not None and not ROOM_KEY.match(key):
        errors.append(f'{path}.key: "{key}" must be lowercase letters, digits and underscores')
        key = None

    name = _text(raw.get("name"), f"{path}.name", errors)

    icon = raw.get("icon")
    if icon is not None and not isinstance(icon, str):
        errors.append(f"{path}.icon: must be a string when given")
        icon = None

    is_outdoor = raw.get("is_outdoor", False)
    if not isinstance(is_outdoor, bool):
        errors.append(f"{path}.is_outdoor: must be true or false")
        is_outdoor = False

    refs: dict[str, EntityRef | None] = {}
    for field_name in ("temperature", "humidity", "climate"):
        value = raw.get(field_name)
        refs[field_name] = None if value is None else _ref(value, f"{path}.{field_name}", errors)

    if not any(refs.values()):
        errors.append(f"{path}: needs at least one of temperature, humidity or climate")

    comfort = _comfort(raw.get("comfort"), f"{path}.comfort", errors)
    # A room that states a band replaces the defaults outright rather than
    # merging key by key, so `comfort: {}` is how a room opts out of alerts.
    if "comfort" not in raw:
        comfort = defaults

    devices = _devices(raw.get("devices"), f"{path}.devices", errors)

    if key is None or name is None:
        return None

    return RoomConfig(
        key=key,
        name=name,
        order=index,
        icon=icon,
        is_outdoor=is_outdoor,
        temperature=refs["temperature"],
        humidity=refs["humidity"],
        climate=refs["climate"],
        comfort=comfort or ComfortBand(),
        devices=devices,
    )


def _rooms(value: Any, defaults: ComfortBand, errors: list[str]) -> tuple[RoomConfig, ...]:
    if not isinstance(value, list) or not value:
        errors.append("rooms: required, and must be a non-empty list")
        return ()

    rooms: list[RoomConfig] = []
    for index, raw in enumerate(value):
        room = _room(raw, index, defaults, errors)
        if room is not None:
            rooms.append(room)

    _reject_duplicates(rooms, errors)
    return tuple(rooms)


def _reject_duplicates(rooms: list[RoomConfig], errors: list[str]) -> None:
    """Two rooms may not share a key, and may not share a reading.

    The second rule is not pedantry: `rooms.widget.yml` pointed two rooms at the
    same humidity sensor, so one of them showed the other's air for months
    (INTENT.md section 11). Silent duplication is exactly the failure a
    schema-validated config exists to prevent.
    """
    seen_keys: dict[str, int] = {}
    for room in rooms:
        if room.key in seen_keys:
            errors.append(f'rooms[{room.order}].key: "{room.key}" is already used')
        else:
            seen_keys[room.key] = room.order

    owners: dict[EntityRef, str] = {}
    for room in rooms:
        for ref in room.entity_refs:
            owner = owners.get(ref)
            if owner is not None and owner != room.key:
                errors.append(
                    f'rooms[{room.order}] ("{room.key}"): {ref} is already read by "{owner}"'
                )
            else:
                owners.setdefault(ref, room.key)
