"""What the dashboard knows, independent of where it came from.

Plain dataclasses and nothing else: no I/O, no PIL, no Home Assistant
vocabulary. Every field is explicitly nullable because a dead sensor is a
normal state, not an error - it renders as a placeholder while the rest of the
screen carries on (INTENT.md section 2).

The dataclasses are frozen and hold tuples rather than lists, so a snapshot
cannot be mutated halfway through a render pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PowerState(Enum):
    """Whether a device is on, off, or not reporting."""

    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class HeatingAction(Enum):
    """What a room's heating is currently doing."""

    HEATING = "heating"
    IDLE = "idle"
    OFF = "off"
    UNKNOWN = "unknown"


class TemperatureAlert(Enum):
    """A room's temperature relative to its comfort band.

    UNKNOWN covers both "no reading" and "no band configured". Neither is a
    reason to draw red.
    """

    OK = "ok"
    TOO_COLD = "too_cold"
    TOO_HOT = "too_hot"
    UNKNOWN = "unknown"


class HumidityAlert(Enum):
    """A room's humidity relative to its ceiling."""

    OK = "ok"
    TOO_HUMID = "too_humid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ComfortBand:
    """The temperature range and humidity ceiling that decide a room's alerts.

    A bathroom and a bedroom do not share a definition of "too humid", so this
    is configured per room. An unset bound is simply not checked.
    """

    min_temperature: float | None = None
    max_temperature: float | None = None
    max_humidity: float | None = None


@dataclass(frozen=True)
class DeviceState:
    """A light, computer, appliance or anything else attached to a room.

    `kind` is deliberately an open string rather than an enum: devices are
    modelled from day one and rendered by nobody yet (INTENT.md section 5), and
    closing the vocabulary now would be guessing.
    """

    key: str
    name: str
    kind: str
    state: PowerState = PowerState.UNKNOWN


@dataclass(frozen=True)
class Climate:
    """A room's climate readings, each independently nullable."""

    temperature: float | None = None
    humidity: float | None = None
    setpoint: float | None = None
    action: HeatingAction = HeatingAction.UNKNOWN


@dataclass(frozen=True)
class Room:
    """The central concept: every room has climate, some rooms have devices.

    `is_outdoor` marks the row drawn last and inverted, and excluded from the
    house summary - the outdoors is not part of the house's health.
    """

    key: str
    name: str
    icon: str | None = None
    order: int = 0
    is_outdoor: bool = False
    climate: Climate = field(default_factory=Climate)
    comfort: ComfortBand = field(default_factory=ComfortBand)
    devices: tuple[DeviceState, ...] = ()


@dataclass(frozen=True)
class RoomAlert:
    """The derived alert state of one room. See derive.room_alert()."""

    temperature: TemperatureAlert = TemperatureAlert.UNKNOWN
    humidity: HumidityAlert = HumidityAlert.UNKNOWN

    @property
    def is_alerting(self) -> bool:
        """True when something about this room should be drawn in red."""
        return (
            self.temperature in (TemperatureAlert.TOO_COLD, TemperatureAlert.TOO_HOT)
            or self.humidity is HumidityAlert.TOO_HUMID
        )


@dataclass(frozen=True)
class Weather:
    """Current conditions, with enough depth to dress a family."""

    condition: str | None = None
    temperature: float | None = None
    apparent_temperature: float | None = None
    temperature_high: float | None = None
    temperature_low: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_bearing: float | None = None
    precipitation: float | None = None


@dataclass(frozen=True)
class HourlyPoint:
    """One point on today's temperature curve."""

    time: datetime | None = None
    temperature: float | None = None
    precipitation: float | None = None
    condition: str | None = None


@dataclass(frozen=True)
class DailyPoint:
    """One day of the forecast strip. Six of these, not seven - see derive."""

    date: datetime | None = None
    condition: str | None = None
    temperature_high: float | None = None
    temperature_low: float | None = None
    precipitation: float | None = None


@dataclass(frozen=True)
class SunTimes:
    """The sun's next transitions, named exactly as the source reports them.

    Both fields are *future* timestamps. That is the entire reason the previous
    implementation reported night during the day: it compared them as though
    they were today's sunrise and sunset, so "next rising is later than next
    setting" looked like night when it actually means day.

    Nothing may decide day from night by comparing these fields directly. Go
    through derive.is_night(), which exists so the trap is written down once
    and tested.
    """

    next_rising: datetime | None = None
    next_setting: datetime | None = None


@dataclass(frozen=True)
class HouseSummary:
    """Derived, never fetched. Indoor rooms only.

    `room_count` is how many indoor rooms are configured; `reporting_count` is
    how many of them actually returned a temperature. The two differing is how
    the summary stays honest when a sensor dies.
    """

    room_count: int = 0
    reporting_count: int = 0
    temperature_mean: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    temperature_spread: float | None = None
    humidity_mean: float | None = None
    humidity_min: float | None = None
    humidity_max: float | None = None
    humidity_median: float | None = None


@dataclass(frozen=True)
class Snapshot:
    """Everything one refresh cycle knows.

    `source_errors` carries what the source failed to fetch, so a failure can be
    logged and reasoned about without any layer above sources/ learning what a
    Home Assistant entity is.
    """

    taken_at: datetime | None = None
    rooms: tuple[Room, ...] = ()
    weather: Weather = field(default_factory=Weather)
    hourly: tuple[HourlyPoint, ...] = ()
    daily: tuple[DailyPoint, ...] = ()
    sun: SunTimes = field(default_factory=SunTimes)
    source_errors: tuple[str, ...] = ()
