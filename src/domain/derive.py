"""Pure derivations over the domain model.

Everything here is a function of its arguments alone: no clock, no I/O, no
configuration lookup. That is what makes the alert rules and the house summary
testable without a display, a source or a Home Assistant instance.
"""

from __future__ import annotations

from statistics import mean, median

from domain.models import (
    HouseSummary,
    HumidityAlert,
    Room,
    RoomAlert,
    SunTimes,
    TemperatureAlert,
)


def is_night(sun: SunTimes) -> bool | None:
    """True when the sun is currently below the horizon.

    Both timestamps are in the future, so whichever comes first tells us the
    present state: if the sun will rise before it sets, it must be down now.

    This is the inverse of what the retired SunWidget computed. Its test
    asserted only `isinstance(result, bool)`, which passes for either answer -
    hence the real assertions in tests/test_domain_derive.py.

    Returns None when either timestamp is missing, because "we do not know" is
    a distinct answer from "it is daytime" and the caller may want a
    placeholder rather than a wrong icon.
    """
    if sun.next_rising is None or sun.next_setting is None:
        return None

    return sun.next_rising < sun.next_setting


def temperature_alert(room: Room) -> TemperatureAlert:
    """Classify a room's temperature against its comfort band.

    The band is inclusive: a room sitting exactly on a bound is in comfort, not
    alerting. An unset bound is not checked, and a room with neither bound set
    is UNKNOWN rather than OK - we have not judged it, so red must not follow.
    """
    temperature = room.climate.temperature
    if temperature is None:
        return TemperatureAlert.UNKNOWN

    low = room.comfort.min_temperature
    high = room.comfort.max_temperature
    if low is None and high is None:
        return TemperatureAlert.UNKNOWN

    if low is not None and temperature < low:
        return TemperatureAlert.TOO_COLD
    if high is not None and temperature > high:
        return TemperatureAlert.TOO_HOT

    return TemperatureAlert.OK


def humidity_alert(room: Room) -> HumidityAlert:
    """Classify a room's humidity against its ceiling.

    The ceiling is inclusive in the same sense: exactly at the ceiling is not
    yet an alert.
    """
    humidity = room.climate.humidity
    ceiling = room.comfort.max_humidity
    if humidity is None or ceiling is None:
        return HumidityAlert.UNKNOWN

    return HumidityAlert.TOO_HUMID if humidity > ceiling else HumidityAlert.OK


def room_alert(room: Room) -> RoomAlert:
    """Both alert axes for one room."""
    return RoomAlert(temperature=temperature_alert(room), humidity=humidity_alert(room))


def indoor_rooms(rooms: tuple[Room, ...]) -> tuple[Room, ...]:
    """The rooms that count as "the house" - everything except the outdoors."""
    return tuple(room for room in rooms if not room.is_outdoor)


def ordered_rooms(rooms: tuple[Room, ...]) -> tuple[Room, ...]:
    """Rooms in display order, with the outdoor row last whatever its order.

    The outdoor row is drawn last and inverted so the eye reads it as "not part
    of the house", so its position is a property of the model rather than
    something each layout has to remember.
    """
    return tuple(sorted(rooms, key=lambda room: (room.is_outdoor, room.order, room.key)))


def house_summary(rooms: tuple[Room, ...]) -> HouseSummary:
    """Aggregate the indoor rooms into the summary block.

    Statistics are computed over the rooms that actually reported; the counts
    record how many were asked. A house where every sensor is dead yields a
    summary of Nones rather than a zero, because zero would be a lie.
    """
    indoor = indoor_rooms(rooms)
    temperatures = [
        room.climate.temperature for room in indoor if room.climate.temperature is not None
    ]
    humidities = [room.climate.humidity for room in indoor if room.climate.humidity is not None]

    return HouseSummary(
        room_count=len(indoor),
        reporting_count=len(temperatures),
        temperature_mean=mean(temperatures) if temperatures else None,
        temperature_min=min(temperatures) if temperatures else None,
        temperature_max=max(temperatures) if temperatures else None,
        temperature_spread=(max(temperatures) - min(temperatures)) if temperatures else None,
        humidity_mean=mean(humidities) if humidities else None,
        humidity_min=min(humidities) if humidities else None,
        humidity_max=max(humidities) if humidities else None,
        humidity_median=median(humidities) if humidities else None,
    )
