"""The computed box model for 800x480.

There are no pixel coordinates in `house.yml` and there is no place to put one
(INTENT.md section 6). The screen is subdivided here instead: constants for the
few decisions that are genuinely arbitrary, and arithmetic for everything that
follows from them. A room added to the configuration changes the row height and
nothing else.

Every box that a partial-eligible item can use has its x edges on multiples of
8, because `display_Partial` snaps its window to whole bytes. That is why the
column divider is an 8-pixel-wide box carrying a 2-pixel rule rather than a
2-pixel-wide box: the thin geometry is the renderer's business, the refresh
window is the layout's.
"""

from __future__ import annotations

from dataclasses import dataclass

from view.drawlist import Box

#: The panel. HARDWARE.md section 1.
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480

#: Inverted date bar across the top.
HEADER_HEIGHT = 36
HEADER_DATE_WIDTH = 480

#: The left column stops here; the 8 pixels to its right carry the rule.
DIVIDER_X = 392
DIVIDER_WIDTH = 8

#: Right column: "RUM / TEMP / RF" header, then rooms, then the house summary.
COLUMN_HEAD_HEIGHT = 26
SUMMARY_HEIGHT = 84

#: The four cells of a room row, tiling the right column left to right. The
#: trailing 8 pixels are the right margin, so these must sum to 392.
MARKER_WIDTH = 24
NAME_WIDTH = 184
TEMPERATURE_WIDTH = 96
HUMIDITY_WIDTH = 88
RIGHT_MARGIN = 8

#: The left column's four regions, top to bottom (INTENT.md section 3). The
#: days strip takes whatever is left, so these three and 444 decide it.
HERO_HEIGHT = 140
STRIP_HEIGHT = 88
CURVE_HEIGHT = 128

#: The left column's own margins. Content runs 8..384, both multiples of 8, so
#: every box cut from it can be a legal partial window. The right margin also
#: keeps text off the column rule the divider carries.
LEFT_MARGIN = 8
LEFT_GUTTER = 8

#: The hero: a 100 px icon, then two rows split at the same x. The big number
#: and the condition sit on the left of that split and the two small readings
#: on the right, so neither row has a hole in it - a 72 px "18" leaves 150 px of
#: white beside it, and white beside the largest thing on the screen reads as a
#: missing value rather than as space.
#:
#: The split is set by the two longest strings either side of it rather than by
#: eye: "Torden og regn" is 146 px and "Føles som -12°" is 108 px, and a winter
#: night is exactly when nobody is standing close enough to guess at a clipped
#: word. `tests/test_render_bmp.py` measures both against these numbers.
HERO_ICON_WIDTH = 104
HERO_ICON_SIZE = 100
HERO_SPLIT = 152
HERO_TEMPERATURE_HEIGHT = 100
HERO_LINE_HEIGHT = 34

#: The six-slot strip: three columns, two rows, a label over a value. The row
#: is taller than the label and the value need, because the slack is the only
#: thing separating the bottom of one row's value from the top of the next
#: row's label.
STRIP_COLUMNS = (120, 128, 128)
STRIP_LABEL_HEIGHT = 16

#: The curve: a title line, the plot, and the hour labels under it.
CURVE_TITLE_HEIGHT = 26
CURVE_AXIS_HEIGHT = 24
CURVE_TITLE_SPLIT = 192

#: 24 hours plotted at a fixed 16 px step rather than at `width // 23`. The
#: step is what makes every sixth point land on a multiple of 8, and the axis
#: labels hang off those points - so an arbitrary step would put the hour
#: labels in boxes that cannot be partial windows. 8 + 23 x 16 = 376, which is
#: inside the 8..384 content column with a pixel to spare for the line's width.
CURVE_POINTS = 24
CURVE_POINT_STEP = 16
CURVE_AXIS_EVERY = 6

#: The bottom of the plot is reserved for precipitation bars, so the
#: temperature line never runs through them.
CURVE_BAR_HEIGHT = 26

#: The days strip: six 64 px columns starting at the column's left edge, which
#: leaves the same 8 px gutter as everything above it. A weekday, a 50 px icon
#: and one line of high/low.
DAY_COUNT = 6
DAY_WIDTH = 64
DAY_ICON_SIZE = 50
DAY_NAME_HEIGHT = 16
DAY_VALUE_HEIGHT = 22


@dataclass(frozen=True)
class HeaderBoxes:
    """The inverted bar: the date on the left, the updated-at clock on the right."""

    box: Box
    date: Box
    meta: Box


@dataclass(frozen=True)
class HeroBoxes:
    """The weather hero: the icon, the big number, and the three readings.

    Two rows of two, split at the same x, so the column has a left edge and a
    right edge and nothing floats between them.
    """

    box: Box
    icon: Box
    temperature: Box
    condition: Box
    apparent: Box
    range: Box


@dataclass(frozen=True)
class SlotBox:
    """One of the six-slot strip's cells: a label over a value."""

    box: Box
    label: Box
    value: Box


@dataclass(frozen=True)
class CurveBoxes:
    """The temperature curve: a title, the plot area, and the hour labels.

    `bars` is the bottom band of the plot, where precipitation is drawn. It
    overlaps `plot` deliberately - they are one refresh window, because the
    bars are red and the line beside them cannot be refreshed without them.
    """

    box: Box
    title: Box
    plot: Box
    bars: Box
    line: Box
    axis: Box


@dataclass(frozen=True)
class DayBox:
    """One day of the forecast strip: weekday, icon, high and low."""

    box: Box
    name: Box
    icon: Box
    values: Box


@dataclass(frozen=True)
class LeftBoxes:
    """Weather, for dressing. INTENT.md section 3's left half."""

    box: Box
    hero: Box
    strip: Box
    curve: Box
    days: Box

    @property
    def content(self) -> Box:
        """The column inside its margins - what every region actually fills."""
        return Box(
            self.box.x + LEFT_MARGIN,
            self.box.y,
            self.box.width - LEFT_MARGIN - LEFT_GUTTER,
            self.box.height,
        )


@dataclass(frozen=True)
class RowCells:
    """One room row, cut into the cells the eye scans across."""

    box: Box
    marker: Box
    name: Box
    temperature: Box
    humidity: Box

    @property
    def title(self) -> Box:
        """Marker and name together, for a line that has no marker to show."""
        return Box(self.box.x, self.box.y, MARKER_WIDTH + NAME_WIDTH, self.box.height)


@dataclass(frozen=True)
class SummaryBoxes:
    """The block beneath the rooms: what the house is doing as one number each."""

    box: Box
    headline: Box
    temperature_stats: Box
    humidity_stats: Box


@dataclass(frozen=True)
class RoomTableBoxes:
    """The right column, cut up for a known number of rooms."""

    box: Box
    head: Box
    rows: tuple[Box, ...]
    summary: SummaryBoxes


@dataclass(frozen=True)
class ScreenBoxes:
    """Every box on the screen, computed once per render."""

    screen: Box
    header: HeaderBoxes
    divider: Box
    left: LeftBoxes
    right: Box


def screen_boxes(width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT) -> ScreenBoxes:
    """Subdivide the panel into a header and two columns."""
    screen = Box(0, 0, width, height)

    header = screen.top(HEADER_HEIGHT)
    date, meta = header.columns(HEADER_DATE_WIDTH, width - HEADER_DATE_WIDTH)

    body = screen.below(HEADER_HEIGHT)
    left = Box(0, body.y, DIVIDER_X, body.height)
    divider = Box(DIVIDER_X, body.y, DIVIDER_WIDTH, body.height)
    right = Box(divider.right, body.y, width - divider.right, body.height)

    return ScreenBoxes(
        screen=screen,
        header=HeaderBoxes(box=header, date=date, meta=meta),
        divider=divider,
        left=left_boxes(left),
        right=right,
    )


def left_boxes(box: Box) -> LeftBoxes:
    """The weather column's four regions, tiling the column exactly."""
    hero = box.top(HERO_HEIGHT)
    rest = box.below(HERO_HEIGHT)
    strip = rest.top(STRIP_HEIGHT)
    rest = rest.below(STRIP_HEIGHT)
    curve = rest.top(CURVE_HEIGHT)
    days = rest.below(CURVE_HEIGHT)

    return LeftBoxes(box=box, hero=hero, strip=strip, curve=curve, days=days)


def hero_boxes(box: Box) -> HeroBoxes:
    """The icon on the left, then two rows split at `HERO_SPLIT`.

    Whatever the two rows do not use is left at the bottom of the hero, where
    it becomes the gap above the strip rather than padding inside a box.
    """
    content = _content(box)
    icon, text = content.columns(HERO_ICON_WIDTH, content.width - HERO_ICON_WIDTH)

    top = text.top(HERO_TEMPERATURE_HEIGHT)
    bottom = text.below(HERO_TEMPERATURE_HEIGHT).top(HERO_LINE_HEIGHT)
    temperature, extremes = top.columns(HERO_SPLIT, top.width - HERO_SPLIT)
    condition, apparent = bottom.columns(HERO_SPLIT, bottom.width - HERO_SPLIT)

    return HeroBoxes(
        box=box,
        icon=icon,
        temperature=temperature,
        condition=condition,
        apparent=apparent,
        range=extremes,
    )


def strip_boxes(box: Box) -> tuple[SlotBox, ...]:
    """Six slots, three across and two down, in reading order."""
    content = _content(box)
    half = content.height // 2
    rows = (content.top(half), content.below(half).top(half))

    return tuple(_slot(cell) for row in rows for cell in row.columns(*STRIP_COLUMNS))


def _slot(box: Box) -> SlotBox:
    return SlotBox(
        box=box,
        label=box.top(STRIP_LABEL_HEIGHT),
        value=box.below(STRIP_LABEL_HEIGHT),
    )


def curve_boxes(box: Box) -> CurveBoxes:
    """A title line, the plot, and the axis - with the plot inside the margins.

    The title and the axis span the whole column because they are text with
    their own padding; only the plot has to align with the data it draws.
    """
    title = box.top(CURVE_TITLE_HEIGHT)
    axis = box.bottom_slice(CURVE_AXIS_HEIGHT)
    middle = Box(box.x, title.bottom, box.width, axis.y - title.bottom)
    plot = _content(middle)

    return CurveBoxes(
        box=box,
        title=title,
        plot=plot,
        bars=plot.bottom_slice(CURVE_BAR_HEIGHT),
        line=plot.top(plot.height - CURVE_BAR_HEIGHT),
        axis=axis,
    )


def day_boxes(box: Box, count: int = DAY_COUNT) -> tuple[DayBox, ...]:
    """`count` equal columns from the column's left edge, byte-aligned by width.

    The width is a constant rather than a division, because 64 is a multiple of
    8 and `box.width // count` is not - and an unaligned day column cannot be a
    partial window however tidily it divides.
    """
    columns = Box(box.x, box.y, DAY_WIDTH * count, box.height).columns(*([DAY_WIDTH] * count))
    return tuple(_day(column) for column in columns)


def _day(box: Box) -> DayBox:
    name = box.top(DAY_NAME_HEIGHT)
    values = box.bottom_slice(DAY_VALUE_HEIGHT)
    return DayBox(
        box=box,
        name=name,
        icon=Box(box.x, name.bottom, box.width, values.y - name.bottom),
        values=values,
    )


def _content(box: Box) -> Box:
    """A left-column box inside the column's margins."""
    return Box(
        box.x + LEFT_MARGIN,
        box.y,
        box.width - LEFT_MARGIN - LEFT_GUTTER,
        box.height,
    )


def room_table(box: Box, room_count: int) -> RoomTableBoxes:
    """Cut the right column for `room_count` rows.

    The row height is whatever divides evenly into the space the column header
    and the summary leave behind. Any remainder becomes a gap above the summary
    rather than being smeared across the rows, because eleven rows of equal
    height read as a table and eleven rows of nearly-equal height read as a
    mistake.
    """
    head = box.top(COLUMN_HEAD_HEIGHT)
    summary = box.bottom_slice(SUMMARY_HEIGHT)

    available = box.height - COLUMN_HEAD_HEIGHT - SUMMARY_HEIGHT
    row_height = available // room_count if room_count else 0
    rows = Box(box.x, head.bottom, box.width, row_height * room_count).stack(room_count, row_height)

    return RoomTableBoxes(box=box, head=head, rows=rows, summary=summary_boxes(summary))


def summary_boxes(box: Box) -> SummaryBoxes:
    """Headline, then one statistics line per axis.

    The top 2 pixels are left to the rule that separates the summary from the
    last room, so the headline does not sit on the line.
    """
    body = box.below(2)
    headline = body.top(36)
    rest = body.below(36)
    half = rest.height // 2

    return SummaryBoxes(
        box=box,
        headline=headline,
        temperature_stats=rest.top(half),
        humidity_stats=rest.below(half),
    )


def row_cells(box: Box) -> RowCells:
    """Marker, name, temperature, humidity - and an 8-pixel right margin."""
    marker, name, temperature, humidity = box.columns(
        MARKER_WIDTH, NAME_WIDTH, TEMPERATURE_WIDTH, HUMIDITY_WIDTH
    )
    return RowCells(box=box, marker=marker, name=name, temperature=temperature, humidity=humidity)
