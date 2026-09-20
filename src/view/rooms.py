"""The room table: eleven rows and a summary, in the right-hand column.

The half of the screen that answers "why does the bathroom smell damp again"
(INTENT.md section 1). One row per room, in configuration order, with the
outdoor row last and inverted so the eye reads it as not part of the house.

**Where the red is, and what it costs.** A room's temperature and humidity
cells are marked full-only for every room and every reading, not only when they
happen to be alerting - the update class is a property of the layout, not of
today's numbers (INTENT.md section 4). Names, labels, rules and the whole
summary block are provably red-free and stay partial-eligible.

**The inverted row is reported, never judged.** White text on a black row has
nowhere to put red, so this function does not colour the outdoor row's cells by
alert state - which is also why they can be partial-eligible. That matches the
configuration, where the outdoor row opts out of having a comfort band at all;
if a band were ever set on an inverted row it would be computed and ignored,
and this is the line that decides so.
"""

from __future__ import annotations

from domain.derive import house_summary, ordered_rooms, room_alert
from domain.format_da import PLACEHOLDER, decimal, humidity, temperature
from domain.models import HouseSummary, HumidityAlert, Room, TemperatureAlert
from view.boxes import RoomTableBoxes, SummaryBoxes, row_cells
from view.drawlist import (
    Align,
    Box,
    Colour,
    DrawItem,
    Edge,
    TextStyle,
    UpdateClass,
    draw_fill,
    draw_outline,
    draw_rule,
    draw_text,
)

#: Too hot points up, too cold points down. Both exist in Liberation Sans.
MARKER_TOO_HOT = "▲"
MARKER_TOO_COLD = "▼"

#: Danish column labels. "RF" is relativ fugtighed - relative humidity.
LABEL_ROOMS = "RUM"
LABEL_TEMPERATURE = "TEMP"
LABEL_HUMIDITY = "RF"
LABEL_HOUSE = "HUSET"
LABEL_ROOM_COUNT = "RUM"
LABEL_MIN = "MIN"
LABEL_MAX = "MAKS"
LABEL_SPREAD = "SPREDN."
LABEL_MEDIAN = "MEDIAN"

#: Thin space either side of the middle dot, as Danish typography sets it.
SEPARATOR = " · "

NAME_PADDING = 6
VALUE_PADDING = 6
BADGE_INSET = 3


def room_table(rooms: tuple[Room, ...], boxes: RoomTableBoxes) -> tuple[DrawItem, ...]:
    """The whole right column for one snapshot's worth of rooms.

    Rows beyond the boxes the layout allocated are dropped rather than drawn
    off the bottom of the panel: a room added to the configuration without a
    re-run of the box model should lose a row, not corrupt the summary.
    """
    items: list[DrawItem] = list(column_head(boxes.head))

    drawn = list(zip(ordered_rooms(rooms), boxes.rows))
    for index, (room, box) in enumerate(drawn):
        items.extend(room_row(room, box, last=index == len(drawn) - 1))

    items.extend(summary_block(house_summary(rooms), boxes.summary))
    return tuple(items)


def column_head(box: Box) -> tuple[DrawItem, ...]:
    """ "RUM   TEMP   RF" and the rule under it. Static, so partial-eligible.

    "RUM" sits over the names rather than at the column edge, because the
    marker cell to its left is empty until a room alerts and a label floating
    above nothing reads as a fourth column.
    """
    cells = row_cells(box)
    region = "rooms.head"

    return (
        draw_text(
            region,
            cells.name,
            LABEL_ROOMS,
            TextStyle.COLUMN_LABEL,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
            padding=NAME_PADDING,
        ),
        draw_text(
            region,
            cells.temperature,
            LABEL_TEMPERATURE,
            TextStyle.COLUMN_LABEL,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=VALUE_PADDING,
        ),
        draw_text(
            region,
            cells.humidity,
            LABEL_HUMIDITY,
            TextStyle.COLUMN_LABEL,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=VALUE_PADDING,
        ),
        draw_rule(region, box, Edge.BOTTOM, UpdateClass.PARTIAL, thickness=2),
    )


def room_row(room: Room, box: Box, last: bool = False) -> tuple[DrawItem, ...]:
    """One room: marker, name, temperature, humidity."""
    cells = row_cells(box)
    alert = room_alert(room)
    inverted = room.is_outdoor

    items: list[DrawItem] = []
    ink = Colour.WHITE if inverted else Colour.BLACK
    name_class = UpdateClass.PARTIAL
    value_class = UpdateClass.PARTIAL if inverted else UpdateClass.FULL

    if inverted:
        items.append(draw_fill(f"room.{room.key}.row", box, Colour.BLACK, UpdateClass.PARTIAL))
    elif not last:
        items.append(
            draw_rule(
                f"room.{room.key}.rule",
                Box(box.x, box.bottom - 1, box.width, 1),
                Edge.TOP,
                UpdateClass.PARTIAL,
            )
        )

    marker = _marker(alert.temperature) if not inverted else None
    if marker is not None:
        items.append(
            draw_text(
                f"room.{room.key}.marker",
                cells.marker,
                marker,
                TextStyle.ROOM_MARKER,
                UpdateClass.FULL,
                colour=Colour.RED,
                align=Align.CENTER,
            )
        )

    items.append(
        draw_text(
            f"room.{room.key}.name",
            cells.name,
            room.name,
            TextStyle.ROOM_NAME,
            name_class,
            colour=ink,
            align=Align.LEFT,
            padding=NAME_PADDING,
        )
    )

    temperature_red = not inverted and alert.temperature in (
        TemperatureAlert.TOO_COLD,
        TemperatureAlert.TOO_HOT,
    )
    items.append(
        draw_text(
            f"room.{room.key}.temperature",
            cells.temperature,
            temperature(room.climate.temperature),
            TextStyle.ROOM_VALUE,
            value_class,
            colour=Colour.RED if temperature_red else ink,
            align=Align.RIGHT,
            padding=VALUE_PADDING,
        )
    )

    humidity_red = not inverted and alert.humidity is HumidityAlert.TOO_HUMID
    region = f"room.{room.key}.humidity"
    if humidity_red:
        items.append(
            draw_outline(region, cells.humidity.inset(0, BADGE_INSET), Colour.RED, value_class)
        )
    items.append(
        draw_text(
            region,
            cells.humidity,
            humidity(room.climate.humidity),
            TextStyle.ROOM_VALUE,
            value_class,
            colour=Colour.RED if humidity_red else ink,
            align=Align.RIGHT,
            padding=VALUE_PADDING + BADGE_INSET,
        )
    )

    return tuple(items)


def summary_block(summary: HouseSummary, boxes: SummaryBoxes) -> tuple[DrawItem, ...]:
    """The house as one number per axis, plus the spread that reveals the truth.

    A mean on its own says the house is comfortable; the spread says one end of
    it is four degrees colder than the other. Neither number is ever red - an
    average is not something a person acts on - so the whole block is
    partial-eligible.
    """
    cells = row_cells(boxes.headline)

    return (
        draw_rule(
            "summary.rule",
            Box(boxes.box.x, boxes.box.y, boxes.box.width, 2),
            Edge.TOP,
            UpdateClass.PARTIAL,
            thickness=2,
        ),
        draw_text(
            "summary.headline",
            cells.title,
            _house_label(summary),
            TextStyle.SUMMARY_TITLE,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
            padding=NAME_PADDING,
        ),
        draw_text(
            "summary.headline",
            cells.temperature,
            temperature(summary.temperature_mean),
            TextStyle.SUMMARY_VALUE,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=VALUE_PADDING,
        ),
        draw_text(
            "summary.headline",
            cells.humidity,
            humidity(summary.humidity_mean),
            TextStyle.SUMMARY_VALUE,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=VALUE_PADDING,
        ),
        draw_text(
            "summary.temperature",
            boxes.temperature_stats,
            _temperature_stats(summary),
            TextStyle.SUMMARY_STAT,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
            padding=NAME_PADDING,
        ),
        draw_text(
            "summary.humidity",
            boxes.humidity_stats,
            _humidity_stats(summary),
            TextStyle.SUMMARY_STAT,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
            padding=NAME_PADDING,
        ),
    )


def _marker(alert: TemperatureAlert) -> str | None:
    """The red triangle, or nothing at all. Never a neutral marker.

    An arrow that is always there is decoration; red used decoratively destroys
    red used semantically (INTENT.md section 2).
    """
    if alert is TemperatureAlert.TOO_HOT:
        return MARKER_TOO_HOT
    if alert is TemperatureAlert.TOO_COLD:
        return MARKER_TOO_COLD
    return None


def _house_label(summary: HouseSummary) -> str:
    """ "HUSET - 10 RUM", or "HUSET - 8/10 RUM" when sensors are missing.

    The second form is the honest one and it appears without being asked for:
    a mean over eight rooms presented as a mean over ten is a small lie that
    nobody would ever catch.
    """
    if summary.reporting_count == summary.room_count:
        count = str(summary.room_count)
    else:
        count = f"{summary.reporting_count}/{summary.room_count}"

    return f"{LABEL_HOUSE}{SEPARATOR}{count} {LABEL_ROOM_COUNT}"


def _temperature_stats(summary: HouseSummary) -> str:
    parts = (
        f"{LABEL_TEMPERATURE} {LABEL_MIN} {temperature(summary.temperature_min)}",
        f"{LABEL_MAX} {temperature(summary.temperature_max)}",
        f"{LABEL_SPREAD} {_spread(summary.temperature_spread)}",
    )
    return SEPARATOR.join(parts)


def _humidity_stats(summary: HouseSummary) -> str:
    parts = (
        f"{LABEL_HUMIDITY} {LABEL_MIN} {humidity(summary.humidity_min)}",
        f"{LABEL_MAX} {humidity(summary.humidity_max)}",
        f"{LABEL_MEDIAN} {humidity(summary.humidity_median)}",
    )
    return SEPARATOR.join(parts)


def _spread(value: float | None) -> str:
    """A spread is a difference, so it carries no degree sign of its own."""
    return PLACEHOLDER if value is None else f"{decimal(value)}°"
