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

#: The left column's four regions, top to bottom (INTENT.md section 3). Nothing
#: draws into them until M5; they are computed here so that the milestone is a
#: set of render functions rather than a second pass at the box model.
HERO_HEIGHT = 130
STRIP_HEIGHT = 84
CURVE_HEIGHT = 150


@dataclass(frozen=True)
class HeaderBoxes:
    """The inverted bar: the date on the left, the updated-at clock on the right."""

    box: Box
    date: Box
    meta: Box


@dataclass(frozen=True)
class LeftBoxes:
    """Weather, for dressing. Empty until M5."""

    box: Box
    hero: Box
    strip: Box
    curve: Box
    days: Box


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
