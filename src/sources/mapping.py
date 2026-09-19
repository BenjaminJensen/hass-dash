"""Home Assistant payloads in, a `Snapshot` out. Pure, and hostile-input proof.

Both sources share this module: `fixture.py` replays recorded payloads through
it and `homeassistant.py` sends freshly fetched ones. That is deliberate - if
the two had separate translations, the fixture would test a mapping the wall
never runs.

Nothing here does I/O and nothing here raises. Every value is coerced
defensively, because this is the layer that meets a generous and unstable API
(INTENT.md section 2): a temperature can arrive as a float, as the string
`"21.5"`, as `"unavailable"`, as `"unknown"`, as `None`, or as a dict that used
to be a number two releases ago. All but the first two become `None`.

The line between silence and a reported problem is drawn on purpose:

- A **missing entity** is reported. It means a typo or a rename, and it will
  show a placeholder forever until a human fixes the configuration.
- **`unavailable` / `unknown`** are not reported. A Zigbee sensor that has not
  checked in yet is doing something entirely normal, and reporting it would
  fill the log with noise every night.
- A value that is **present but unparseable** is reported. That is a shape
  change, which is exactly the class of surprise this layer exists to absorb.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.house import EntityRef, HouseConfig, RoomConfig
from domain.models import (
    Climate,
    DailyPoint,
    DeviceState,
    HeatingAction,
    HourlyPoint,
    PowerState,
    Room,
    Snapshot,
    SunTimes,
    Weather,
)

#: States that mean "this sensor has nothing to say right now" rather than a
#: value. Lowercased before comparison.
ABSENT_STATES = frozenset({"unavailable", "unknown", "none", "null", "nan", ""})

#: `hvac_action`, as the climate integration reports it. Anything outside this
#: map - "preheating", "defrosting", or whatever a future release invents -
#: becomes UNKNOWN rather than a guess.
HVAC_ACTIONS = {
    "heating": HeatingAction.HEATING,
    "idle": HeatingAction.IDLE,
    "off": HeatingAction.OFF,
}

POWER_STATES = {"on": PowerState.ON, "off": PowerState.OFF}

#: Where a room's readings come from when the configuration names a climate
#: entity but no separate sensor. A thermostat already knows the temperature of
#: the room it is in, so most rooms need no `temperature:` key at all.
CLIMATE_TEMPERATURE = "current_temperature"
CLIMATE_HUMIDITY = "current_humidity"
CLIMATE_SETPOINT = "temperature"


class Problems:
    """Collects what the source could not read, in the order it happened.

    Deduplicated, because one missing climate entity is one problem even though
    a room asks it for a temperature, a humidity and a setpoint.
    """

    def __init__(self) -> None:
        self._seen: dict[str, None] = {}

    def add(self, message: str) -> None:
        self._seen.setdefault(message, None)

    def missing(self, where: str, ref: EntityRef) -> None:
        self.add(f"{where}: {ref} does not exist")

    def unreadable(self, where: str, ref: EntityRef, value: Any) -> None:
        self.add(f"{where}: {ref} is {value!r}, which is not a number")

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(self._seen)


# --------------------------------------------------------------------------
# Coercion - the whole point of this module
# --------------------------------------------------------------------------


def is_absent(value: Any) -> bool:
    """Whether a raw value means "nothing to report" rather than a reading."""
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in ABSENT_STATES


def as_float(value: Any) -> float | None:
    """A number, or None. Never raises, whatever it is handed.

    `bool` is rejected on purpose: it is an `int` in Python, so a sensor that
    reports `true` would otherwise quietly become 1.0 degrees.
    """
    if is_absent(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def as_datetime(value: Any) -> datetime | None:
    """An ISO 8601 timestamp, or None.

    Home Assistant emits `+00:00`, but has emitted `Z` in places and may again,
    so both are accepted. A naive timestamp is passed through unchanged for
    `format_da.to_local()` to label.
    """
    if isinstance(value, datetime):
        return value
    if is_absent(value) or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def as_text(value: Any) -> str | None:
    """A non-empty string, or None."""
    if is_absent(value) or not isinstance(value, str):
        return None
    return value.strip() or None


# --------------------------------------------------------------------------
# Reading one reference out of a states payload
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Reader:
    """Reads references out of one `/api/states` payload, collecting problems.

    `states` is keyed by entity id, which is the shape both the REST endpoint
    (once indexed) and the recorded fixture use.
    """

    states: dict[str, dict]
    problems: Problems

    def raw(self, ref: EntityRef | None, where: str) -> Any:
        """The raw value behind a reference: an entity's state, or an attribute."""
        if ref is None:
            return None

        state = self.states.get(ref.entity_id)
        if state is None or not isinstance(state, dict):
            self.problems.missing(where, ref)
            return None

        if ref.attribute is not None:
            return self.attributes(ref.entity_id).get(ref.attribute)
        return state.get("state")

    def attributes(self, entity_id: str) -> dict:
        """An entity's attributes, always a dict even when the payload lies."""
        state = self.states.get(entity_id)
        attributes = state.get("attributes") if isinstance(state, dict) else None
        return attributes if isinstance(attributes, dict) else {}

    def number(self, ref: EntityRef | None, where: str) -> float | None:
        """A numeric reading behind a reference, reporting only real surprises."""
        raw = self.raw(ref, where)
        value = as_float(raw)
        if value is None and ref is not None and not is_absent(raw):
            self.problems.unreadable(where, ref, raw)
        return value

    def attribute_number(self, ref: EntityRef | None, attribute: str, where: str) -> float | None:
        """A numeric *attribute* of the entity a reference names.

        Used for the readings a climate entity carries alongside its state,
        which is how a thermostat backs a room that names no sensor.
        """
        if ref is None or ref.entity_id not in self.states:
            return None

        raw = self.attributes(ref.entity_id).get(attribute)
        value = as_float(raw)
        if value is None and not is_absent(raw):
            self.problems.unreadable(where, ref, raw)
        return value


# --------------------------------------------------------------------------
# Rooms
# --------------------------------------------------------------------------


def _climate(room: RoomConfig, reader: Reader) -> Climate:
    """One room's readings, preferring a dedicated sensor over the thermostat."""
    temperature = reader.number(room.temperature, f"{room.key}/temperature")
    if temperature is None:
        temperature = reader.attribute_number(
            room.climate, CLIMATE_TEMPERATURE, f"{room.key}/temperature"
        )

    humidity = reader.number(room.humidity, f"{room.key}/humidity")
    if humidity is None:
        humidity = reader.attribute_number(room.climate, CLIMATE_HUMIDITY, f"{room.key}/humidity")

    setpoint = reader.attribute_number(room.climate, CLIMATE_SETPOINT, f"{room.key}/setpoint")

    return Climate(
        temperature=temperature,
        humidity=humidity,
        setpoint=setpoint,
        action=_heating_action(room, reader),
    )


def _heating_action(room: RoomConfig, reader: Reader) -> HeatingAction:
    """What the heating is doing, from `hvac_action` where the entity reports it.

    Plenty of climate entities never send `hvac_action`. For those, a state of
    `off` is still a fact worth keeping - the radiator is off, we simply do not
    know whether an on one is currently calling for heat.
    """
    if room.climate is None:
        return HeatingAction.UNKNOWN

    action = as_text(reader.attributes(room.climate.entity_id).get("hvac_action"))
    if action is not None:
        return HVAC_ACTIONS.get(action.lower(), HeatingAction.UNKNOWN)

    mode = as_text(reader.raw(room.climate, f"{room.key}/climate"))
    if mode is not None and mode.lower() == "off":
        return HeatingAction.OFF
    return HeatingAction.UNKNOWN


def _devices(room: RoomConfig, reader: Reader) -> tuple[DeviceState, ...]:
    """Modelled from day one, rendered by nobody yet (INTENT.md section 5)."""
    states = []
    for device in room.devices:
        raw = as_text(reader.raw(device.source, f"{room.key}/device/{device.key}"))
        power = POWER_STATES.get(raw.lower(), PowerState.UNKNOWN) if raw else PowerState.UNKNOWN
        states.append(DeviceState(key=device.key, name=device.name, kind=device.kind, state=power))
    return tuple(states)


def _room(room: RoomConfig, reader: Reader) -> Room:
    return Room(
        key=room.key,
        name=room.name,
        icon=room.icon,
        order=room.order,
        is_outdoor=room.is_outdoor,
        climate=_climate(room, reader),
        comfort=room.comfort,
        devices=_devices(room, reader),
    )


# --------------------------------------------------------------------------
# Weather, forecasts and the sun
# --------------------------------------------------------------------------


def _weather(config: HouseConfig, reader: Reader, daily: list) -> Weather:
    """Current conditions, with today's high and low borrowed from the forecast.

    A weather entity reports what it is now; the high and low of the day are
    only in the daily forecast's first entry. Borrowing them here keeps the
    view from having to know that.
    """
    ref = config.weather
    where = "weather"
    condition = as_text(reader.raw(ref, where))
    attributes = reader.attributes(ref.entity_id)

    today = daily[0] if daily and isinstance(daily[0], dict) else {}

    def attribute(name: str) -> float | None:
        return reader.attribute_number(ref, name, where)

    return Weather(
        condition=condition,
        temperature=attribute("temperature"),
        apparent_temperature=attribute("apparent_temperature"),
        temperature_high=as_float(today.get("temperature")),
        temperature_low=as_float(today.get("templow")),
        humidity=attribute("humidity"),
        pressure=attribute("pressure"),
        wind_speed=attribute("wind_speed"),
        wind_bearing=as_float(attributes.get("wind_bearing")),
        precipitation=as_float(today.get("precipitation")),
    )


def _hourly(forecast: Any) -> tuple[HourlyPoint, ...]:
    if not isinstance(forecast, list):
        return ()
    return tuple(
        HourlyPoint(
            time=as_datetime(entry.get("datetime")),
            temperature=as_float(entry.get("temperature")),
            precipitation=as_float(entry.get("precipitation")),
            condition=as_text(entry.get("condition")),
        )
        for entry in forecast
        if isinstance(entry, dict)
    )


def _daily(forecast: Any) -> tuple[DailyPoint, ...]:
    if not isinstance(forecast, list):
        return ()
    return tuple(
        DailyPoint(
            date=as_datetime(entry.get("datetime")),
            condition=as_text(entry.get("condition")),
            temperature_high=as_float(entry.get("temperature")),
            temperature_low=as_float(entry.get("templow")),
            precipitation=as_float(entry.get("precipitation")),
        )
        for entry in forecast
        if isinstance(entry, dict)
    )


def _sun(config: HouseConfig, reader: Reader) -> SunTimes:
    """The sun's next transitions.

    Both are future timestamps and neither is today's sunrise or sunset. The
    names are the source's own, kept deliberately, because renaming them to
    `sunrise` / `sunset` is what produced the inverted night detection the
    rewrite is repaying (INTENT.md section 5).
    """
    ref = config.sun
    if ref.entity_id not in reader.states:
        reader.problems.missing("sun", ref)
        return SunTimes()

    attributes = reader.attributes(ref.entity_id)
    return SunTimes(
        next_rising=as_datetime(attributes.get("next_rising")),
        next_setting=as_datetime(attributes.get("next_setting")),
    )


# --------------------------------------------------------------------------
# The whole snapshot
# --------------------------------------------------------------------------


def build_snapshot(
    config: HouseConfig,
    states: Any,
    hourly: Any = None,
    daily: Any = None,
    taken_at: datetime | None = None,
    extra_errors: tuple[str, ...] = (),
) -> Snapshot:
    """One cycle's worth of everything, from whatever the payloads turned out to be.

    `states` is keyed by entity id. Anything else - a list, None, a string -
    is treated as an empty instance, which produces a snapshot full of `None`s
    and a problem per configured entity rather than a traceback.
    """
    problems = Problems()
    for message in extra_errors:
        problems.add(message)

    if not isinstance(states, dict):
        problems.add("states payload is not a mapping of entity id to state")
        states = {}

    reader = Reader(
        states={k: v for k, v in states.items() if isinstance(k, str)}, problems=problems
    )

    daily_points = _daily(daily)
    rooms = tuple(_room(room, reader) for room in config.rooms)

    return Snapshot(
        taken_at=taken_at,
        rooms=rooms,
        weather=_weather(config, reader, daily if isinstance(daily, list) else []),
        hourly=_hourly(hourly),
        daily=daily_points,
        sun=_sun(config, reader),
        source_errors=problems.as_tuple(),
    )
