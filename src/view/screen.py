"""Compose the regions into one draw list for one snapshot.

Every region of INTENT.md section 3, in one pure function of a `Snapshot`: the
inverted header, the weather column on the left, and the room table on the
right. Each region is a function of its own in its own module, tested on its
own; this file only says where they go and in what order.

`screen()` reads the clock from `snapshot.taken_at` rather than calling one, so
a test can render any moment - and so a frame is reproducible, which is what
makes `tools/render_fixture.py` a development loop rather than a screenshot.

Order matters in exactly one way: later items draw over earlier ones, and a
pixel is one colour (see `render/bmp.py`). The divider is drawn before the two
columns so that nothing in them has to know it exists.

The rules between the left column's four regions are drawn here rather than by
the regions themselves, for the same reason: a separator belongs to the seam
and not to either side of it, and a region that drew its own bottom edge would
put the seam inside its refresh window.
"""

from __future__ import annotations

from domain.models import Snapshot
from view.boxes import (
    LeftBoxes,
    ScreenBoxes,
    room_table as room_table_boxes,
    screen_boxes,
)
from view.drawlist import Box, DrawItem, Edge, UpdateClass, draw_rule
from view.forecast import curve, days
from view.header import header
from view.rooms import room_table
from view.weather import hero, strip

#: The hairline between two regions of the left column. One pixel: this is a
#: seam, not a border, and the right column's row rules are the same weight.
SEAM_THICKNESS = 1


def screen(snapshot: Snapshot, boxes: ScreenBoxes | None = None) -> tuple[DrawItem, ...]:
    """Everything the panel should show, as a list you can assert on."""
    boxes = boxes or screen_boxes()
    left = boxes.left

    items: list[DrawItem] = []
    items.extend(header(snapshot.taken_at, boxes.header))
    items.append(
        draw_rule(
            "divider",
            boxes.divider,
            Edge.LEFT,
            UpdateClass.PARTIAL,
            thickness=2,
        )
    )
    items.extend(seams(left))
    items.extend(hero(snapshot.weather, snapshot.sun, left.hero))
    items.extend(strip(snapshot.weather, snapshot.sun, left.strip))
    items.extend(curve(snapshot.hourly, left.curve))
    items.extend(days(snapshot.daily, left.days))
    items.extend(room_table(snapshot.rooms, room_table_boxes(boxes.right, len(snapshot.rooms))))

    return tuple(items)


def seams(left: LeftBoxes) -> tuple[DrawItem, ...]:
    """A hairline between each of the left column's four regions.

    One region each, because one rule is one refresh window: three rules spread
    down the column sharing a region would make that window the whole column.
    Nothing here can be red, so all three are partial-eligible.
    """
    return tuple(
        draw_rule(
            f"left.seam.{name}",
            Box(left.box.x, box.y - SEAM_THICKNESS, left.box.width, SEAM_THICKNESS),
            Edge.TOP,
            UpdateClass.PARTIAL,
            thickness=SEAM_THICKNESS,
        )
        for name, box in (("strip", left.strip), ("curve", left.curve), ("days", left.days))
    )
