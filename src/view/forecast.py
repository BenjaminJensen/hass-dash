"""What the weather is about to do: the hourly curve, and the days below it.

The bottom half of the left column. Where `weather.py` answers "what is it like
now", this answers "and is that about to change" - which is the question that
decides whether the coat comes off the hook on the way out or not.

**The curve is the next 24 hours, not today from 00 to 24.** INTENT.md section
3 asked for the latter and this provider cannot supply it: the hourly forecast
starts at the current hour and runs forward (PLAN.md slice 2.2), so half of
today is simply not in the payload and drawing it would mean pulling history
out of the recorder API for hours nobody is dressing for. The consequence is
that the now-marker section 3 sketched is gone with it - the curve *starts* at
now, and a marker on its left edge would be decoration. Red used decoratively
destroys red used semantically (section 2), so the curve's only red is the
precipitation it was always allowed.

**Six days, not seven**, for the same reason: this provider returns six.

**Why the plot is one region.** The temperature line is black and the
precipitation bars are red, and they share a rectangle. A partial refresh
rewrites the black plane across its whole window, so a window containing red
cannot be refreshed in the partial class without disturbing it. One region, one
update class, and that class is full - which costs nothing, because a forecast
that changed in the last five minutes was not worth redrawing anyway.
"""

from __future__ import annotations

from domain import format_da
from domain.derive import curve_hours, forecast_days, temperature_bounds
from domain.models import DailyPoint, HourlyPoint
from view.boxes import (
    CURVE_AXIS_EVERY,
    CURVE_POINT_STEP,
    CURVE_POINTS,
    CURVE_TITLE_SPLIT,
    DAY_ICON_SIZE,
    CurveBoxes,
    DayBox,
    curve_boxes,
    day_boxes,
)
from view.drawlist import (
    Align,
    Box,
    Colour,
    DrawItem,
    Edge,
    TextStyle,
    UpdateClass,
    VAlign,
    draw_fill,
    draw_icon,
    draw_line,
    draw_rule,
    draw_text,
)
from view.icons import condition_icon

#: The curve's title, with the span it actually covers filled in.
CURVE_LABEL = "NÆSTE {hours} TIMER"

#: An en dash between the curve's own low and high, as Danish sets a range.
RANGE_SEPARATOR = "–"

#: The millimetres of rain in one hour that fill the bar band completely. Four
#: is a downpour in this climate; scaling to the wettest hour in the forecast
#: instead would make a drizzle look like a storm on a dry week.
BAR_FULL_SCALE = 4.0

#: A bar is this wide, centred on its hour, and never shorter than this - a
#: trace of rain that renders as nothing reads as a dry hour.
BAR_WIDTH = 10
BAR_MINIMUM_HEIGHT = 6

#: An hourly point with neighbours on neither side still happened. Drawn as a
#: dot rather than dropped, because a gap in a line is information and a
#: silently missing reading is not.
DOT_SIZE = 3

LINE_THICKNESS = 2
PADDING = 4
DAY_SEPARATOR = "/"


def curve(hourly: tuple[HourlyPoint, ...], box: Box) -> tuple[DrawItem, ...]:
    """The temperature line, the precipitation bars, and the hours beneath."""
    boxes = curve_boxes(box)
    points = curve_hours(hourly, CURVE_POINTS)
    low, high = temperature_bounds(points)

    items: list[DrawItem] = list(_title(boxes, low, high))
    items.extend(_plot(points, boxes, low, high))
    items.extend(_axis(points, boxes))
    return tuple(items)


def days(daily: tuple[DailyPoint, ...], box: Box) -> tuple[DrawItem, ...]:
    """One column per forecast day: weekday, icon, high and low.

    Days the forecast does not reach are not drawn at all. An empty column with
    two placeholders in it claims the provider said something about Thursday.
    """
    columns = day_boxes(box)
    items: list[DrawItem] = []

    for index, (day, column) in enumerate(zip(forecast_days(daily, len(columns)), columns)):
        items.extend(_day(day, column, index))

    return tuple(items)


def _title(boxes: CurveBoxes, low: float | None, high: float | None) -> tuple[DrawItem, ...]:
    """What the curve covers, and the range it is scaled to.

    The range is the curve's own low and high rather than the day's forecast
    extremes, so the line genuinely touches the top and bottom of the plot and
    a reader can tell what the shape is worth.
    """
    label, value = boxes.title.columns(CURVE_TITLE_SPLIT, boxes.title.width - CURVE_TITLE_SPLIT)

    return (
        draw_text(
            "curve.title",
            label,
            CURVE_LABEL.format(hours=CURVE_POINTS),
            TextStyle.CURVE_TITLE,
            UpdateClass.PARTIAL,
            align=Align.LEFT,
            padding=PADDING + 4,
        ),
        draw_text(
            "curve.title",
            value,
            _range(low, high),
            TextStyle.CURVE_TITLE,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=PADDING + 4,
        ),
    )


def _plot(
    points: tuple[HourlyPoint, ...],
    boxes: CurveBoxes,
    low: float | None,
    high: float | None,
) -> tuple[DrawItem, ...]:
    """The baseline, the bars, and the line - in that order, so the line wins."""
    items: list[DrawItem] = [
        draw_rule("curve.plot", boxes.plot, Edge.BOTTOM, UpdateClass.FULL, thickness=1)
    ]
    items.extend(_bars(points, boxes))
    items.extend(_line(points, boxes, low, high))
    return tuple(items)


def _bars(points: tuple[HourlyPoint, ...], boxes: CurveBoxes) -> tuple[DrawItem, ...]:
    """Precipitation, red, growing up from the baseline. INTENT.md section 3."""
    band = boxes.bars
    items: list[DrawItem] = []

    for index, point in enumerate(points):
        millimetres = point.precipitation
        if millimetres is None or millimetres <= 0:
            continue

        fraction = min(millimetres / BAR_FULL_SCALE, 1.0)
        height = max(int(fraction * band.height), BAR_MINIMUM_HEIGHT)
        centre = _x(index, boxes.plot)
        left = max(band.x, min(centre - BAR_WIDTH // 2, band.right - BAR_WIDTH))

        items.append(
            draw_fill(
                "curve.plot",
                Box(left, band.bottom - height, BAR_WIDTH, height),
                Colour.RED,
                UpdateClass.FULL,
            )
        )

    return tuple(items)


def _line(
    points: tuple[HourlyPoint, ...],
    boxes: CurveBoxes,
    low: float | None,
    high: float | None,
) -> tuple[DrawItem, ...]:
    """The temperature, as one polyline per run of hours that reported one."""
    if low is None or high is None:
        return ()

    items: list[DrawItem] = []
    for run in _runs(points):
        plotted = [
            (_x(index, boxes.plot), _y(point.temperature, low, high, boxes.line))
            for index, point in run
        ]
        if len(plotted) == 1:
            x, y = plotted[0]
            items.append(
                draw_fill(
                    "curve.plot",
                    Box(x, y, DOT_SIZE, DOT_SIZE),
                    Colour.BLACK,
                    UpdateClass.FULL,
                )
            )
        else:
            items.append(
                draw_line(
                    "curve.plot",
                    boxes.line,
                    tuple(plotted),
                    UpdateClass.FULL,
                    thickness=LINE_THICKNESS,
                )
            )

    return tuple(items)


def _axis(points: tuple[HourlyPoint, ...], boxes: CurveBoxes) -> tuple[DrawItem, ...]:
    """The hour under every sixth point, with a tick joining it to the plot.

    Every sixth point lands on a multiple of eight because the horizontal step
    is sixteen pixels, which is what lets these be partial-eligible boxes at
    all - see `view/boxes.py`.
    """
    items: list[DrawItem] = []

    for index in range(0, len(points), CURVE_AXIS_EVERY):
        x = _x(index, boxes.plot)
        width = min(CURVE_AXIS_EVERY * CURVE_POINT_STEP, boxes.plot.right - x)
        items.append(
            draw_text(
                "curve.axis",
                Box(x, boxes.axis.y, width, boxes.axis.height),
                format_da.hour(points[index].time),
                TextStyle.CURVE_AXIS,
                UpdateClass.PARTIAL,
                align=Align.LEFT,
                valign=VAlign.TOP,
            )
        )

    return tuple(items)


def _day(day: DailyPoint, boxes: DayBox, index: int) -> tuple[DrawItem, ...]:
    """One column of the strip. Nothing here can be red."""
    region = f"day.{index}"
    items: list[DrawItem] = [
        draw_text(
            region,
            boxes.name,
            format_da.weekday_short(day.date),
            TextStyle.DAY_NAME,
            UpdateClass.PARTIAL,
            align=Align.CENTER,
            valign=VAlign.TOP,
        )
    ]

    icon = condition_icon(day.condition)
    if icon is not None:
        items.append(draw_icon(region, boxes.icon, icon, UpdateClass.PARTIAL, size=DAY_ICON_SIZE))

    high = format_da.temperature(day.temperature_high, places=0)
    low = format_da.temperature(day.temperature_low, places=0)
    items.append(
        draw_text(
            region,
            boxes.values,
            f"{high}{DAY_SEPARATOR}{low}",
            TextStyle.DAY_VALUE,
            UpdateClass.PARTIAL,
            align=Align.CENTER,
        )
    )

    return tuple(items)


def _runs(points: tuple[HourlyPoint, ...]) -> list[list[tuple[int, HourlyPoint]]]:
    """Contiguous stretches of hours that reported a temperature.

    A missing hour breaks the line rather than being interpolated across. The
    forecast did not say what happens at 14.00; drawing a straight line through
    it would say it for them.
    """
    runs: list[list[tuple[int, HourlyPoint]]] = []
    current: list[tuple[int, HourlyPoint]] = []

    for index, point in enumerate(points):
        if point.temperature is None:
            if current:
                runs.append(current)
                current = []
            continue
        current.append((index, point))

    if current:
        runs.append(current)
    return runs


def _x(index: int, plot: Box) -> int:
    """Where the nth hour sits. A constant step, not a division - see `_axis`."""
    return plot.x + index * CURVE_POINT_STEP


def _y(value: float, low: float, high: float, box: Box) -> int:
    """A temperature mapped into the plot, warm at the top."""
    if high <= low:
        return box.y + box.height // 2

    fraction = (value - low) / (high - low)
    return int(box.bottom - 1 - fraction * (box.height - 1))


def _range(low: float | None, high: float | None) -> str:
    """ "9°–18°", the scale the curve is drawn against."""
    return (
        f"{format_da.temperature(low, places=0)}"
        f"{RANGE_SEPARATOR}"
        f"{format_da.temperature(high, places=0)}"
    )
