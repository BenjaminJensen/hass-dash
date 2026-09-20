"""Compose the regions into one draw list for one snapshot.

The walking skeleton of PLAN.md M4: the header and the room table, cut straight
through every layer so that a real BMP exists before the rest of the screen is
designed. The left column is computed (see `boxes.left`) and deliberately empty
- M5 fills it with the weather hero, the six-slot strip, today's curve and the
seven-day strip.

`screen()` is a pure function of a `Snapshot`. It reads the clock from
`snapshot.taken_at` rather than calling one, so a test can render any moment.
"""

from __future__ import annotations

from domain.models import Snapshot
from view.boxes import ScreenBoxes, room_table as room_table_boxes, screen_boxes
from view.drawlist import DrawItem, Edge, UpdateClass, draw_rule
from view.header import header
from view.rooms import room_table


def screen(snapshot: Snapshot, boxes: ScreenBoxes | None = None) -> tuple[DrawItem, ...]:
    """Everything the panel should show, as a list you can assert on."""
    boxes = boxes or screen_boxes()

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
    items.extend(room_table(snapshot.rooms, room_table_boxes(boxes.right, len(snapshot.rooms))))

    return tuple(items)
