"""Layout as a value: what to draw, where, in which colour, at which cost.

The inversion from the retired widget layer. A widget used to fetch its own
data and paint straight onto a shared canvas, which made two things impossible:
knowing which pixels changed, and knowing whether a region can ever be red.
Both are required by the refresh contract (INTENT.md section 4), so layout
stops being a side effect and becomes a list of `DrawItem` you can diff, assert
on, and reason about with no display in the room.

Three invariants live here rather than in anyone's head, and `violations()`
checks all three:

*Red implies full.* `display_Partial()` writes only the black plane; there is
no partial path to red (HARDWARE.md section 4). An item drawn red can only
reach the glass on a full refresh.

*One region, one update class.* A region is a refresh window. A window
containing both a partial-eligible label and a full-only value is a window that
cannot be refreshed in either class without lying about the other.

*A partial region is byte-aligned on x.* `display_Partial` floors `Xstart` and
rounds `Xend` up to multiples of 8. An unaligned window silently grows, and the
pixels it grows over get repainted from a buffer that was never told about
them. Aligning every partial-eligible box means any union of them is aligned
too.

The fourth rule - *a region that could be red for some input is full for all
inputs* - cannot be checked from one draw list, because one list is one input.
`inconsistent_regions()` checks it across the draw lists of many inputs, which
is how the tests drive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: `display_Partial` snaps its x window to whole bytes. Y is unconstrained.
BYTE_ALIGNMENT = 8


class Colour(Enum):
    """The three the panel has. `WHITE` is ink removed, not ink added."""

    BLACK = "black"
    RED = "red"
    WHITE = "white"


class UpdateClass(Enum):
    """Which refresh an item needs to reach the glass.

    `FULL` is the safe default throughout: an item nobody has thought about
    waits for the 26-second cycle rather than quietly claiming a partial path
    it may not have.
    """

    FULL = "full"
    PARTIAL = "partial"


class Primitive(Enum):
    """What to draw. Deliberately few.

    `RULE` draws a thin line along one edge of its box rather than being given
    the thin geometry directly, so that the box stays a legal refresh window -
    a 2-pixel-wide box could never satisfy the byte alignment rule.

    `LINE` is the one primitive that carries geometry of its own, because a
    temperature curve is not expressible as a rectangle. Its points are still
    required to lie inside its box, so the box remains an honest refresh
    window - see `violations()`.
    """

    FILL = "fill"
    OUTLINE = "outline"
    RULE = "rule"
    TEXT = "text"
    ICON = "icon"
    LINE = "line"


class Align(Enum):
    """Horizontal placement of content inside its box."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VAlign(Enum):
    """Vertical placement of content inside its box."""

    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class Edge(Enum):
    """Which side of a box a `RULE` is drawn on."""

    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class TextStyle(Enum):
    """A named role, not a font.

    The view says "this is a room value"; `render/fonts.py` decides that means
    Liberation Sans Bold at 25 px. Keeping the mapping out of here is what lets
    the layout tests survive a font change (INTENT.md section 7).
    """

    HEADER_DATE = "header_date"
    HEADER_META = "header_meta"
    COLUMN_LABEL = "column_label"
    ROOM_NAME = "room_name"
    ROOM_VALUE = "room_value"
    ROOM_MARKER = "room_marker"
    SUMMARY_TITLE = "summary_title"
    SUMMARY_VALUE = "summary_value"
    SUMMARY_STAT = "summary_stat"
    HERO_TEMPERATURE = "hero_temperature"
    HERO_CONDITION = "hero_condition"
    HERO_DETAIL = "hero_detail"
    SLOT_LABEL = "slot_label"
    SLOT_VALUE = "slot_value"
    CURVE_TITLE = "curve_title"
    CURVE_AXIS = "curve_axis"
    DAY_NAME = "day_name"
    DAY_VALUE = "day_value"


@dataclass(frozen=True)
class Box:
    """A rectangle in screen coordinates, and the unit of refresh.

    The helpers all return new boxes that tile or nest exactly, so a layout is
    built by subdividing rather than by adding coordinates up by hand - which
    is how the old floorplan layout drifted.
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def is_byte_aligned(self) -> bool:
        """True when both x edges fall on multiples of 8. See the module docstring."""
        return self.x % BYTE_ALIGNMENT == 0 and self.right % BYTE_ALIGNMENT == 0

    def inset(self, dx: int, dy: int | None = None) -> Box:
        """A smaller box inside this one, for padding content away from an edge."""
        dy = dx if dy is None else dy
        return Box(self.x + dx, self.y + dy, self.width - 2 * dx, self.height - 2 * dy)

    def top(self, height: int) -> Box:
        """The top slice, full width."""
        return Box(self.x, self.y, self.width, height)

    def bottom_slice(self, height: int) -> Box:
        """The bottom slice, full width."""
        return Box(self.x, self.bottom - height, self.width, height)

    def below(self, height: int) -> Box:
        """What is left after removing `height` from the top."""
        return Box(self.x, self.y + height, self.width, self.height - height)

    def columns(self, *widths: int) -> tuple[Box, ...]:
        """Tile left to right. Any width left over is simply not returned."""
        boxes = []
        x = self.x
        for width in widths:
            boxes.append(Box(x, self.y, width, self.height))
            x += width
        return tuple(boxes)

    def stack(self, count: int, height: int) -> tuple[Box, ...]:
        """`count` rows of `height`, tiling downward from the top edge."""
        return tuple(Box(self.x, self.y + i * height, self.width, height) for i in range(count))


@dataclass(frozen=True)
class DrawItem:
    """One thing to draw, and everything the renderer needs to draw it.

    `region` is the refresh window this item belongs to. Items sharing a region
    are refreshed together and must therefore share an update class; the region
    name is also what makes the "could be red" rule checkable, because it is
    stable across inputs while the values inside it are not.
    """

    region: str
    primitive: Primitive
    box: Box
    colour: Colour = Colour.BLACK
    update: UpdateClass = UpdateClass.FULL
    text: str = ""
    style: TextStyle = TextStyle.ROOM_NAME
    align: Align = Align.LEFT
    valign: VAlign = VAlign.MIDDLE
    padding: int = 0
    thickness: int = 1
    edge: Edge = Edge.BOTTOM
    icon: str = ""
    icon_size: int = 50
    points: tuple[tuple[int, int], ...] = ()


def draw_fill(region: str, box: Box, colour: Colour, update: UpdateClass) -> DrawItem:
    """Flood the whole box - the inverted header and the outdoor row."""
    return DrawItem(region=region, primitive=Primitive.FILL, box=box, colour=colour, update=update)


def draw_outline(
    region: str,
    box: Box,
    colour: Colour,
    update: UpdateClass,
    thickness: int = 2,
) -> DrawItem:
    """A hollow rectangle - the humidity badge."""
    return DrawItem(
        region=region,
        primitive=Primitive.OUTLINE,
        box=box,
        colour=colour,
        update=update,
        thickness=thickness,
    )


def draw_rule(
    region: str,
    box: Box,
    edge: Edge,
    update: UpdateClass,
    colour: Colour = Colour.BLACK,
    thickness: int = 1,
) -> DrawItem:
    """A separator along one edge of a box. The box stays the refresh window."""
    return DrawItem(
        region=region,
        primitive=Primitive.RULE,
        box=box,
        colour=colour,
        update=update,
        thickness=thickness,
        edge=edge,
    )


def draw_text(
    region: str,
    box: Box,
    text: str,
    style: TextStyle,
    update: UpdateClass,
    colour: Colour = Colour.BLACK,
    align: Align = Align.LEFT,
    valign: VAlign = VAlign.MIDDLE,
    padding: int = 0,
) -> DrawItem:
    """A string placed inside a box, not at a coordinate.

    Placement is by alignment so that a font change moves nothing: the box is
    the contract and the glyphs arrange themselves inside it.
    """
    return DrawItem(
        region=region,
        primitive=Primitive.TEXT,
        box=box,
        colour=colour,
        update=update,
        text=text,
        style=style,
        align=align,
        valign=valign,
        padding=padding,
    )


def draw_icon(
    region: str,
    box: Box,
    icon: str,
    update: UpdateClass,
    size: int = 50,
    colour: Colour = Colour.BLACK,
    align: Align = Align.CENTER,
    valign: VAlign = VAlign.MIDDLE,
) -> DrawItem:
    """A pre-rendered mono bitmap from `assets/`, placed inside a box."""
    return DrawItem(
        region=region,
        primitive=Primitive.ICON,
        box=box,
        colour=colour,
        update=update,
        icon=icon,
        icon_size=size,
        align=align,
        valign=valign,
    )


def draw_line(
    region: str,
    box: Box,
    points: tuple[tuple[int, int], ...],
    update: UpdateClass,
    colour: Colour = Colour.BLACK,
    thickness: int = 2,
) -> DrawItem:
    """A polyline - today's temperature, and nothing else so far.

    The points are absolute screen coordinates rather than offsets inside the
    box, because the curve is computed from a value range against a plot area
    and converting twice is one conversion too many to get wrong.
    """
    return DrawItem(
        region=region,
        primitive=Primitive.LINE,
        box=box,
        colour=colour,
        update=update,
        thickness=thickness,
        points=tuple(points),
    )


def violations(items: tuple[DrawItem, ...] | list[DrawItem]) -> tuple[str, ...]:
    """Everything wrong with one draw list, as readable lines.

    Returns rather than raises, so a test can assert on the whole set at once
    instead of discovering one problem per run.
    """
    found: list[str] = []
    classes: dict[str, UpdateClass] = {}

    for item in items:
        where = f"{item.region} ({item.primitive.value})"

        if item.box.width <= 0 or item.box.height <= 0:
            found.append(f"{where}: empty box {item.box}")

        if item.colour is Colour.RED and item.update is not UpdateClass.FULL:
            found.append(f"{where}: red but not full - there is no partial path to red")

        if item.update is UpdateClass.PARTIAL and not item.box.is_byte_aligned:
            found.append(
                f"{where}: partial box x={item.box.x}..{item.box.right} is not a multiple of 8"
            )

        if item.primitive is Primitive.TEXT and not item.text:
            found.append(f"{where}: text item with nothing to draw")

        if item.primitive is Primitive.LINE:
            if len(item.points) < 2:
                found.append(f"{where}: line with fewer than two points")
            outside = [point for point in item.points if not _inside(item.box, point)]
            if outside:
                found.append(f"{where}: line leaves its box at {outside[0]}")

        seen = classes.setdefault(item.region, item.update)
        if seen is not item.update:
            found.append(
                f"{where}: region mixes {seen.value} and {item.update.value} - "
                "one region is one refresh window"
            )

    return tuple(found)


def _inside(box: Box, point: tuple[int, int]) -> bool:
    """Whether a point falls within a box, right and bottom edges exclusive.

    A line that strays outside its box turns the box into a refresh window that
    does not contain what it refreshes, which is the one thing the region model
    may not allow - a partial refresh would leave the stray pixels behind.
    """
    x, y = point
    return box.x <= x < box.right and box.y <= y < box.bottom


def region_colours(items: tuple[DrawItem, ...] | list[DrawItem]) -> dict[str, set[Colour]]:
    """Which colours each region draws in. Used to count what red actually costs."""
    found: dict[str, set[Colour]] = {}
    for item in items:
        found.setdefault(item.region, set()).add(item.colour)
    return found


def region_classes(items: tuple[DrawItem, ...] | list[DrawItem]) -> dict[str, UpdateClass]:
    """Each region's update class. Assumes `violations()` found no mixed region."""
    return {item.region: item.update for item in items}


def inconsistent_regions(lists: list[tuple[DrawItem, ...]]) -> tuple[str, ...]:
    """Regions whose update class depends on the data. INTENT.md section 4.

    > A region's colour eligibility is a property of the layout, not a guess. If
    > a region *could* render red for some input, it is full-only for all
    > inputs.

    Give this the draw lists a layout function produced from a spread of inputs
    - alerting, not alerting, missing - and it names any region that changed its
    mind. A region that is partial on Monday and full on Tuesday is a region
    whose refresh window has to be recomputed on the wall, which is the one
    thing the draw list exists to avoid.
    """
    found: list[str] = []
    seen: dict[str, UpdateClass] = {}

    for items in lists:
        for region, update in region_classes(items).items():
            first = seen.setdefault(region, update)
            if first is not update:
                found.append(
                    f"{region}: {first.value} for one input and {update.value} for another"
                )

    return tuple(sorted(set(found)))
