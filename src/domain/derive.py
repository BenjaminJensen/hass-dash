"""Pure derivations over the domain model.

Everything here is a function of its arguments alone: no clock, no I/O, no
configuration lookup. That is what makes the alert rules and the house summary
testable without a display, a source or a Home Assistant instance.
"""

from __future__ import annotations

from math import ceil, exp, floor
from statistics import mean, median

from domain.models import (
    DailyPoint,
    HourlyPoint,
    HouseSummary,
    HumidityAlert,
    Room,
    RoomAlert,
    SunTimes,
    TemperatureAlert,
    Weather,
)

#: Conditions that mean water is falling right now, which is the one case
#: INTENT.md section 3 lets the condition text go red. Fog and wind are not
#: precipitation however unpleasant they are, and `exceptional` is a severity
#: flag rather than a kind of weather, so neither earns the colour.
PRECIPITATION_CONDITIONS = frozenset(
    {
        "rainy",
        "pouring",
        "snowy",
        "snowy-rainy",
        "hail",
        "lightning-rainy",
    }
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


def is_precipitating(weather: Weather) -> bool:
    """Whether the current condition is water actually falling.

    Deliberately not "is there precipitation in the forecast". The red is for
    the person standing in the hall deciding on a coat, and a condition of
    `rainy` is the only thing on this screen that says it is raining *now*
    (INTENT.md section 3).
    """
    condition = (weather.condition or "").strip().lower()
    return condition in PRECIPITATION_CONDITIONS


def apparent_temperature(weather: Weather) -> float | None:
    """What the air feels like, reported if the source knows and computed if not.

    The instance this house runs does not publish `apparent_temperature`
    (PLAN.md slice 2.2), but it does publish temperature, relative humidity and
    wind speed - which is exactly the input to the Australian Bureau of
    Meteorology's apparent temperature, the same formula Home Assistant's own
    integrations use where they compute one:

        AT = T + 0.33e - 0.70v - 4.00
        e  = RH/100 x 6.105 x exp(17.27T / (237.7 + T))

    with T in degrees Celsius, RH in percent and v in metres per second. The
    source's own value wins where it exists, so a future integration that
    starts publishing one is not quietly overruled by arithmetic.

    Returns None unless all three inputs are present. A "feels like" computed
    from two of them is a guess wearing the authority of a number.
    """
    if weather.apparent_temperature is not None:
        return weather.apparent_temperature

    temperature = weather.temperature
    humidity = weather.humidity
    wind = weather.wind_speed
    if temperature is None or humidity is None or wind is None:
        return None

    vapour = (humidity / 100) * 6.105 * exp(17.27 * temperature / (237.7 + temperature))
    return temperature + 0.33 * vapour - 0.70 * wind - 4.00


def curve_hours(hourly: tuple[HourlyPoint, ...], count: int = 24) -> tuple[HourlyPoint, ...]:
    """The points the temperature curve draws, from now forward.

    INTENT.md section 3 asked for today from 00 to 24. The provider's hourly
    forecast starts at the current hour and runs 48 hours forward, so the first
    half of today is simply not in the payload (PLAN.md slice 2.2) and drawing
    it would mean fetching history from the recorder API for the sake of hours
    nobody is dressing for. The curve is the next `count` hours instead, which
    is the half of the day the screen exists to inform.

    Points with no temperature are kept rather than dropped, so a gap in the
    forecast is a gap in the line rather than a shortened day.
    """
    return tuple(hourly[:count])


def forecast_days(daily: tuple[DailyPoint, ...], count: int = 6) -> tuple[DailyPoint, ...]:
    """The days the strip draws, today first.

    Six, not seven: this provider returns six days and INTENT.md section 3's
    seven-day strip cannot be drawn from six days of data (PLAN.md slice 2.2).
    The count is a parameter so a provider that returns more is not truncated
    by a constant buried in a layout function.
    """
    return tuple(daily[:count])


def temperature_bounds(points: tuple[HourlyPoint, ...]) -> tuple[float | None, float | None]:
    """The lowest and highest temperature across a run of hourly points.

    The curve's own scale, rather than the day's forecast high and low: a plot
    scaled to numbers that are not on it has a line that never touches its
    edges and a reader who cannot tell why.
    """
    values = [point.temperature for point in points if point.temperature is not None]
    if not values:
        return (None, None)
    return (min(values), max(values))


#: The degree steps a temperature gridline is allowed to fall on, coarsest
#: last. Nothing finer than a whole degree: a gridline labelled "14,5°" is a
#: number nobody reads at three metres (INTENT.md section 2). The coarse end is
#: further out than any Danish day needs, so that the grid stays inside its
#: line budget rather than falling off the end of this tuple.
TICK_STEPS = (1, 2, 5, 10, 20, 50)

#: At most four gridlines, because the plot band is under 60 px tall and a
#: label needs 14 of them. Three intervals is the densest grid that can still
#: be read rather than merely seen.
MAX_TICK_INTERVALS = 3


def temperature_scale(
    points: tuple[HourlyPoint, ...],
    steps: tuple[int, ...] = TICK_STEPS,
    maximum: int = MAX_TICK_INTERVALS,
) -> tuple[float | None, float | None, tuple[int, ...]]:
    """The band the curve is drawn against, and the gridlines across it.

    The band is the forecast's own range rounded outward to whole steps, and
    the gridlines are those steps. Rounding outward is what buys round numbers
    on the axis, and it costs the height between the extreme and its gridline -
    the line no longer touches the top and bottom of the band, as it did when
    the band *was* the range and a "9°-18°" readout in the title was the only
    thing saying what the shape was worth. The gridlines say it better.

    The step is the finest that keeps the grid to `maximum` intervals, so a day
    that moves three degrees is drawn against a three-degree grid rather than
    being flattened onto a ten-degree one.
    """
    low, high = temperature_bounds(points)
    if low is None or high is None:
        return (None, None, ())

    bands = [_band(low, high, step) for step in steps]
    step, bottom, top = next(
        (band for band in bands if (band[2] - band[1]) // band[0] <= maximum),
        bands[-1],
    )

    return (float(bottom), float(top), tuple(range(bottom, top + 1, step)))


def _band(low: float, high: float, step: int) -> tuple[int, int, int]:
    """One candidate scale: the step, and the range rounded outward onto it.

    A forecast that never moves would round to a band of no height, which has
    no top and no bottom to draw. It gets one step of room instead.
    """
    bottom = floor(low / step) * step
    top = ceil(high / step) * step
    return (step, bottom, top + step if top == bottom else top)
