"""The inverted bar across the top: what day it is, and how stale the screen is.

Inverted because it is the one band that is never data - it frames the screen
rather than reporting it - and because black-on-white everywhere else means the
eye finds the frame without reading it.

Nothing here can be red, so the whole bar is partial-eligible. That matters
more than it looks: the updated-at clock is the only thing on the screen that
changes every cycle, and it is the reason a partial refresh has anything to do
at all (INTENT.md section 4).
"""

from __future__ import annotations

from datetime import datetime

from domain import format_da
from view.boxes import HeaderBoxes
from view.drawlist import (
    Align,
    Colour,
    DrawItem,
    TextStyle,
    UpdateClass,
    draw_fill,
    draw_text,
)

#: Danish for "updated", drawn uppercase as a label rather than a sentence.
UPDATED_LABEL = "OPDATERET"

PADDING = 12


def header(taken_at: datetime | None, boxes: HeaderBoxes) -> tuple[DrawItem, ...]:
    """The date on the left, the time of this snapshot on the right."""
    return (
        draw_fill("header.bar", boxes.box, Colour.BLACK, UpdateClass.PARTIAL),
        draw_text(
            "header.date",
            boxes.date,
            format_da.date_long(taken_at),
            TextStyle.HEADER_DATE,
            UpdateClass.PARTIAL,
            colour=Colour.WHITE,
            align=Align.LEFT,
            padding=PADDING,
        ),
        draw_text(
            "header.meta",
            boxes.meta,
            f"{UPDATED_LABEL} {format_da.clock(taken_at)}",
            TextStyle.HEADER_META,
            UpdateClass.PARTIAL,
            colour=Colour.WHITE,
            align=Align.RIGHT,
            padding=PADDING,
        ),
    )
