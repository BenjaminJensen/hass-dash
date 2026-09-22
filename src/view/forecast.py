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
now, so there is nothing to mark. What is left of that idea is the title's
`NU 17°`: the reading the left-hand end of the line is standing on, and the one
piece of red the curve spends outside the rain.

**The plot has a grid, and the grid is the scale.** A line drawn between two
unlabelled edges says only that the day has a shape. Three or four temperature
gridlines and a three-hourly time grid say what the shape is worth, which is
what the title's old "9°-18°" readout was doing badly. The grid is dotted and
one pixel thick so that it stays behind the data; `domain.derive` picks what it
is a grid *of*.

**Six days, not seven**, for the same reason: this provider returns six.

**Why the plot is one region.** The temperature line is black and the
precipitation bars are red, and they share a rectangle. A partial refresh
rewrites the black plane across its whole window, so a window containing red
cannot be refreshed in the partial class without disturbing it. One region, one
update class, and that class is full - which costs nothing, because a forecast
that changed in the last five minutes was not worth redrawing anyway.

**The title and the hour labels are full now too, and for the same kind of
reason.** `NU 17°` puts red in the title, and a three-hourly axis puts its
labels on a 43-pixel pitch that no longer lands on byte boundaries. Both were
partial-eligible before and neither was ever refreshed on its own: they change
when the forecast beside them changes, and that is a full refresh. The tick
gutter is the one part of the curve that keeps the option, because it is black
and it is the only box here still aligned to 8.
"""

from __future__ import annotations

from domain import format_da
from domain.derive import curve_hours, forecast_days, temperature_scale
from domain.models import DailyPoint, HourlyPoint
from view.boxes import (
    CURVE_AXIS_EVERY,
    CURVE_HOURS,
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

#: The curve's title, with the span it actually covers filled in, and what the
#: hour at its left-hand end reads - which is where "now" is.
CURVE_LABEL = "TEMPERATUR NÆSTE {hours} TIMER"
NOW_LABEL = "NU {temperature}"

#: A gridline: one pixel of ink every five. Fine enough to read as texture
#: rather than as a line, which is the difference between a grid behind the
#: data and a grid competing with it.
GRID_DASH = 1
GRID_GAP = 4

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

#: Boxes to centre a label in, not measurements of the label. Two hour digits
#: are 14 px wide, so 32 leaves room either side without the neighbouring hour
#: reaching it.
LABEL_WIDTH = 32
TICK_HEIGHT = 16


def curve(
    hourly: tuple[HourlyPoint, ...],
    now: float | None,
    box: Box,
) -> tuple[DrawItem, ...]:
    """The temperature line and its grid, the rain bars, and the hours beneath.

    `now` is the current outdoor temperature rather than anything the forecast
    says about this hour: it is the number in the hero, repeated here because
    the left-hand end of the line is the only place on the plot a reader can
    anchor to.
    """
    boxes = curve_boxes(box)
    points = curve_hours(hourly, CURVE_POINTS)
    low, high, ticks = temperature_scale(points)

    items: list[DrawItem] = list(_title(boxes, now))
    items.extend(_ticks(boxes, ticks, low, high))
    items.extend(_plot(points, boxes, ticks, low, high))
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


def _title(boxes: CurveBoxes, now: float | None) -> tuple[DrawItem, ...]:
    """What the curve covers, and what it reads at the end you are standing on.

    INTENT.md section 2 lists "the 'you are here' marker on the day's curve"
    among the things red is *for*, and this is what is left of that marker once
    the curve starts at now: the reading the left-hand end of the line stands
    on. A placeholder is not a marker, though, so a curve with no reading
    behind it spends no red - which keeps "every sensor is dead" a screen with
    no red on it at all.
    """
    label, value = boxes.title.columns(CURVE_TITLE_SPLIT, boxes.title.width - CURVE_TITLE_SPLIT)

    return (
        draw_text(
            "curve.title",
            label,
            CURVE_LABEL.format(hours=CURVE_HOURS),
            TextStyle.CURVE_TITLE,
            UpdateClass.FULL,
            align=Align.LEFT,
            padding=PADDING + 4,
        ),
        draw_text(
            "curve.title",
            value,
            NOW_LABEL.format(temperature=format_da.temperature(now, places=0)),
            TextStyle.CURVE_TITLE,
            UpdateClass.FULL,
            colour=Colour.BLACK if now is None else Colour.RED,
            align=Align.RIGHT,
            padding=PADDING + 4,
        ),
    )


def _ticks(
    boxes: CurveBoxes,
    ticks: tuple[int, ...],
    low: float | None,
    high: float | None,
) -> tuple[DrawItem, ...]:
    """One temperature label per gridline, in the gutter left of the plot.

    Right-aligned against the plot's edge so the numbers form a column the eye
    can run down, and centred on their own line rather than sitting above it.
    """
    if low is None or high is None:
        return ()

    return tuple(
        draw_text(
            "curve.ticks",
            _tick_box(tick, low, high, boxes),
            format_da.temperature(tick, places=0),
            TextStyle.CURVE_AXIS,
            UpdateClass.PARTIAL,
            align=Align.RIGHT,
            padding=PADDING,
        )
        for tick in ticks
    )


def _plot(
    points: tuple[HourlyPoint, ...],
    boxes: CurveBoxes,
    ticks: tuple[int, ...],
    low: float | None,
    high: float | None,
) -> tuple[DrawItem, ...]:
    """Grid, axes, bars, line - in that order, so each one wins over the last."""
    items: list[DrawItem] = list(_grid(boxes, ticks, low, high))
    items.extend(
        (
            draw_rule("curve.plot", boxes.plot, Edge.BOTTOM, UpdateClass.FULL, thickness=1),
            draw_rule("curve.plot", boxes.plot, Edge.LEFT, UpdateClass.FULL, thickness=1),
        )
    )
    items.extend(_bars(points, boxes))
    items.extend(_line(points, boxes, low, high))
    return tuple(items)


def _grid(
    boxes: CurveBoxes,
    ticks: tuple[int, ...],
    low: float | None,
    high: float | None,
) -> tuple[DrawItem, ...]:
    """A dotted line across every gridline and up every labelled hour.

    The vertical lines are geometry and are drawn whatever the forecast said;
    the horizontal ones are the scale and need one. The first vertical is
    skipped because the plot's own left edge is already there, solid.
    """
    items: list[DrawItem] = [
        _dotted("curve.plot", Box(x, boxes.plot.y, 1, boxes.plot.height), Edge.LEFT)
        for x in _label_positions(boxes)[1:]
    ]

    if low is not None and high is not None:
        items.extend(
            _dotted(
                "curve.plot",
                Box(boxes.plot.x, _y(tick, low, high, boxes.line), boxes.plot.width, 1),
                Edge.TOP,
            )
            for tick in ticks
        )

    return tuple(items)


def _dotted(region: str, box: Box, edge: Edge) -> DrawItem:
    """One gridline. Black, hairline, and broken."""
    return draw_rule(
        region,
        box,
        edge,
        UpdateClass.FULL,
        thickness=1,
        dash=GRID_DASH,
        gap=GRID_GAP,
    )


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
    """The hour under every third point, centred on the gridline above it.

    Only hours the forecast actually reached are labelled, while the gridlines
    above them are drawn regardless: the grid is the plot's frame and the
    labels are its data, and a short forecast should shorten the second.
    """
    items: list[DrawItem] = []

    for index, x in enumerate(_label_positions(boxes)):
        point = index * CURVE_AXIS_EVERY
        if point >= len(points):
            break

        items.append(
            draw_text(
                "curve.axis",
                _label_box(x, boxes),
                format_da.hour(points[point].time),
                TextStyle.CURVE_AXIS,
                UpdateClass.FULL,
                align=Align.CENTER,
                valign=VAlign.TOP,
            )
        )

    return tuple(items)


def _label_positions(boxes: CurveBoxes) -> tuple[int, ...]:
    """The x of every labelled hour, from the first to the plot's right edge."""
    return tuple(_x(index, boxes.plot) for index in range(0, CURVE_POINTS, CURVE_AXIS_EVERY))


def _label_box(x: int, boxes: CurveBoxes) -> Box:
    """An hour label's box, centred on its gridline and kept in the column.

    The last hour needs the clamp: its box would otherwise end past the column
    rule, and a refresh window that reaches into the room table is worse than
    a label three pixels off its own gridline. The box is trimmed rather than
    slid, so the drift is the trim and not the whole overhang.
    """
    left = max(x - LABEL_WIDTH // 2, boxes.box.x)
    right = min(x + LABEL_WIDTH // 2, boxes.box.right)
    return Box(left, boxes.axis.y, right - left, boxes.axis.height)


def _tick_box(tick: int, low: float, high: float, boxes: CurveBoxes) -> Box:
    """A temperature label's box, centred on its gridline and kept in the gutter."""
    gutter = boxes.ticks
    centred = _y(tick, low, high, boxes.line) - TICK_HEIGHT // 2
    top = min(max(centred, gutter.y), gutter.bottom - TICK_HEIGHT)
    return Box(gutter.x, top, gutter.width, TICK_HEIGHT)


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
    """Where the nth hour sits: the span shared out, both ends on an edge.

    Rounded rather than stepped, so hour 24 lands on the plot's last pixel
    instead of a constant step's worth short of it. Neighbouring hours end up
    a pixel apart in width, which is a pixel nobody can see - whereas a curve
    that stops before its own axis does is visible from the other side of the
    hall.
    """
    return plot.x + round(index * (plot.width - 1) / CURVE_HOURS)


def _y(value: float, low: float, high: float, box: Box) -> int:
    """A temperature mapped into the plot, warm at the top."""
    if high <= low:
        return box.y + box.height // 2

    fraction = (value - low) / (high - low)
    return int(box.bottom - 1 - fraction * (box.height - 1))
