"""Which font a named text style actually is.

The view says `TextStyle.ROOM_VALUE`; this file says that means Liberation Sans
Bold at 25 px. Keeping the decision here is what lets the layout tests assert
on content, position, colour and update class and survive a font change
(INTENT.md section 7) - a size changed here moves no assertion.

The sizes are not free choices. The right column has to fit eleven rooms, a
column header and a summary into 444 px, which caps a room row at 30 px, which
caps the value font at whatever has an ascent plus descent of 30 or less. See
`view/boxes.py` for the arithmetic and PLAN.md M4 for what that means at three
metres.

`HERO_TEMPERATURE` is the one size chosen for effect rather than by division:
INTENT.md section 3 asks for the current temperature at the largest size on the
screen, and 72 px is the largest that leaves the condition text and the
apparent temperature a line each inside a 140 px hero.

Faces are cached per `FontBook`, because the loop on the Pi renders a frame
every few minutes for months and re-reading nine TrueType files off an SD card
each time is pure waste.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from view.drawlist import TextStyle

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Liberation"
BOLD = "LiberationSans-Bold.ttf"
REGULAR = "LiberationSans-Regular.ttf"


@dataclass(frozen=True)
class FontSpec:
    """A file and a size, which is all a face is."""

    filename: str
    size: int


#: Every style the view can name. A missing entry is a bug, not a default.
STYLES: dict[TextStyle, FontSpec] = {
    TextStyle.HEADER_DATE: FontSpec(BOLD, 24),
    TextStyle.HEADER_META: FontSpec(BOLD, 18),
    TextStyle.COLUMN_LABEL: FontSpec(BOLD, 15),
    TextStyle.ROOM_NAME: FontSpec(REGULAR, 24),
    TextStyle.ROOM_VALUE: FontSpec(BOLD, 25),
    TextStyle.ROOM_MARKER: FontSpec(BOLD, 20),
    TextStyle.SUMMARY_TITLE: FontSpec(BOLD, 21),
    TextStyle.SUMMARY_VALUE: FontSpec(BOLD, 25),
    TextStyle.SUMMARY_STAT: FontSpec(REGULAR, 16),
    TextStyle.HERO_TEMPERATURE: FontSpec(BOLD, 72),
    TextStyle.HERO_CONDITION: FontSpec(BOLD, 20),
    TextStyle.HERO_DETAIL: FontSpec(REGULAR, 16),
    TextStyle.SLOT_LABEL: FontSpec(BOLD, 13),
    TextStyle.SLOT_VALUE: FontSpec(BOLD, 20),
    TextStyle.CURVE_TITLE: FontSpec(BOLD, 15),
    TextStyle.CURVE_AXIS: FontSpec(REGULAR, 12),
    TextStyle.DAY_NAME: FontSpec(BOLD, 14),
    TextStyle.DAY_VALUE: FontSpec(REGULAR, 15),
}


class FontBook:
    """Loads and caches the faces the styles name."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else FONT_DIR
        self._cache: dict[TextStyle, Any] = {}

    def get(self, style: TextStyle) -> Any:
        """The face for one style, loaded once."""
        cached = self._cache.get(style)
        if cached is not None:
            return cached

        from PIL import ImageFont

        spec = STYLES[style]
        path = self.directory / spec.filename
        if not path.is_file():
            raise FileNotFoundError(f"font for {style.value} not found at {path}")

        font = ImageFont.truetype(str(path), spec.size)
        self._cache[style] = font
        return font

    def line_height(self, style: TextStyle) -> int:
        """Ascent plus descent - the vertical space one line of this style needs.

        Text is placed from the ascender line rather than from its own ink
        extent, so that "23,1" and "Stue" share a baseline. A row whose height
        is below this number will clip, which is what
        `tests/test_render_fonts.py` checks against the box model.
        """
        ascent, descent = self.get(style).getmetrics()
        return ascent + descent
