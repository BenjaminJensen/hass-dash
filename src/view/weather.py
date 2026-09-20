"""The weather now: the hero, and the six-slot strip under it.

The top of the left column, and the half of the screen that answers "what do I
put on" (INTENT.md section 1). The hero is the one place on the panel where
size does the work - the current temperature is the largest thing on the glass,
because it is the number a person reads from the far end of the hall and
everything else is detail they step closer for.

**Where the red is.** Exactly two places, both from INTENT.md section 3: the
condition text when it is actually raining or snowing, and the precipitation
slot when there is precipitation to report. Both are therefore full-only for
every input, not only when they happen to be red today. Everything else here -
the icon, the big number, the apparent temperature, the day's high and low, and
five of the six slots - is provably red-free and stays partial-eligible, which
between them is most of the moving content on the screen.

**Whole degrees, deliberately.** The room table renders 23,1 because a tenth of
a degree indoors is the difference between comfortable and not. Outdoors it is
noise: nobody has ever chosen a different coat for 17,4 rather than 17,0.
"""

from __future__ import annotations

from domain import format_da
from domain.derive import apparent_temperature, is_night, is_precipitating
from domain.models import SunTimes, Weather
from view.boxes import HERO_ICON_SIZE, SlotBox, hero_boxes, strip_boxes
from view.drawlist import (
    Align,
    Box,
    Colour,
    DrawItem,
    TextStyle,
    UpdateClass,
    VAlign,
    draw_icon,
    draw_text,
)
from view.icons import condition_icon

#: Danish for "feels like", the line INTENT.md section 3 sketches as
#: "Føles som 15°".
APPARENT_LABEL = "Føles som"

#: The strip's labels, in the order the strip reads: three across, then three
#: more. "LUFTFUGT" is short for luftfugtighed - humidity of the air.
LABEL_SUNRISE = "SOL OP"
LABEL_SUNSET = "SOL NED"
LABEL_WIND = "VIND"
LABEL_HUMIDITY = "LUFTFUGT"
LABEL_PRESSURE = "TRYK"
LABEL_PRECIPITATION = "NEDBØR"

#: What separates the day's high from its low: "18° / 9°".
RANGE_SEPARATOR = " / "

PADDING = 2


def hero(weather: Weather, sun: SunTimes, box: Box) -> tuple[DrawItem, ...]:
    """The icon, the temperature, the condition, and the two detail readings."""
    boxes = hero_boxes(box)
    items: list[DrawItem] = []

    icon = condition_icon(weather.condition, is_night(sun))
    if icon is not None:
        items.append(
            draw_icon(
                "weather.icon",
                boxes.icon,
                icon,
                UpdateClass.PARTIAL,
                size=HERO_ICON_SIZE,
            )
        )

    items.append(
        draw_text(
            "weather.temperature",
            boxes.temperature,
            format_da.temperature(weather.temperature, places=0),
            TextStyle.HERO_TEMPERATURE,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
        )
    )
    items.append(
        draw_text(
            "weather.condition",
            boxes.condition,
            format_da.condition(weather.condition),
            TextStyle.HERO_CONDITION,
            UpdateClass.FULL,
            colour=Colour.RED if is_precipitating(weather) else Colour.BLACK,
            align=Align.LEFT,
        )
    )
    items.append(
        draw_text(
            "weather.apparent",
            boxes.apparent,
            f"{APPARENT_LABEL} {format_da.temperature(apparent_temperature(weather), places=0)}",
            TextStyle.HERO_DETAIL,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
        )
    )
    items.append(
        draw_text(
            "weather.range",
            boxes.range,
            _range(weather),
            TextStyle.HERO_DETAIL,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
        )
    )

    return tuple(items)


def strip(weather: Weather, sun: SunTimes, box: Box) -> tuple[DrawItem, ...]:
    """The six readings a hero has no room for, in two rows of three.

    The sun's times come from `SunTimes` unaltered: both fields are the *next*
    transition, which is what a person wants at 22.00 as much as at 08.00, and
    reinterpreting them as today's sunrise and sunset is the exact bug the
    domain model was renamed to prevent (INTENT.md section 5).
    """
    slots = strip_boxes(box)
    wind = format_da.wind_speed(weather.wind_speed)
    direction = format_da.wind_direction(weather.wind_bearing)
    precipitating = (weather.precipitation or 0) > 0

    readings = (
        ("sunrise", LABEL_SUNRISE, format_da.clock(sun.next_rising), False),
        ("sunset", LABEL_SUNSET, format_da.clock(sun.next_setting), False),
        ("wind", LABEL_WIND, _wind(wind, direction), False),
        ("humidity", LABEL_HUMIDITY, format_da.humidity(weather.humidity), False),
        ("pressure", LABEL_PRESSURE, format_da.pressure(weather.pressure), False),
        (
            "precipitation",
            LABEL_PRECIPITATION,
            format_da.precipitation(weather.precipitation),
            precipitating,
        ),
    )

    items: list[DrawItem] = []
    for slot, (key, label, value, red) in zip(slots, readings):
        items.extend(_slot(slot, key, label, value, red))

    return tuple(items)


def _slot(boxes: SlotBox, key: str, label: str, value: str, red: bool) -> tuple[DrawItem, ...]:
    """One label over one value.

    Only the precipitation slot is full-only, and it is full-only whether or not
    it is raining - the update class is a property of the layout, not of
    today's weather (INTENT.md section 4).
    """
    region = f"strip.{key}"
    update = UpdateClass.FULL if key == "precipitation" else UpdateClass.PARTIAL

    return (
        draw_text(
            region,
            boxes.label,
            label,
            TextStyle.SLOT_LABEL,
            update,
            align=Align.LEFT,
            valign=VAlign.TOP,
            padding=PADDING,
        ),
        draw_text(
            region,
            boxes.value,
            value,
            TextStyle.SLOT_VALUE,
            update,
            colour=Colour.RED if red else Colour.BLACK,
            align=Align.LEFT,
            valign=VAlign.TOP,
            padding=PADDING,
        ),
    )


def _wind(speed: str, direction: str) -> str:
    """ "6,4 m/s SV", or just the speed when the bearing is missing."""
    if direction == format_da.PLACEHOLDER:
        return speed
    return f"{speed} {direction}"


def _range(weather: Weather) -> str:
    """Today's high and low, as the forecast's first day reports them."""
    high = format_da.temperature(weather.temperature_high, places=0)
    low = format_da.temperature(weather.temperature_low, places=0)
    return f"{high}{RANGE_SEPARATOR}{low}"
