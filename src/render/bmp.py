"""Executes a draw list into the two planes the panel actually has.

The panel is not a colour display with a red in its palette. It is two
one-bit planes - `0x10` for black and `0x13` for red - and a pixel is whichever
plane has ink at it, with red winning (HARDWARE.md section 4). This renderer
builds exactly those two planes, which is why the same draw list can later go
to the panel with no change: `EPDRenderer` at M8 hands these images to
`getbuffer()` and this file never learns that GPIO exists.

Plane convention follows the vendored driver's own: a plane is a PIL `"1"`
image where 255 is blank and 0 is ink, so `Image.new("1", size, 255)` is an
empty plane. `getbuffer()` inverts on the way out and `display()` inverts the
black buffer back; that double inversion is respected at M8, never
reimplemented.

**A pixel is one colour.** Drawing black clears red underneath it and drawing
red clears black, rather than leaving both planes inked and relying on the
panel's precedence. The composite is then unambiguous and the BMP on disk says
what the wall will say.

Two files come out of a render, per INTENT.md section 7:

*The composite* is the three-colour BMP, for judging by eye whether red has
been spent where it earns its keep.

*The preview* is the black plane alone - the partial-eligible content, and
nothing else. Anything red is simply absent from it. That is the refresh
contract made visible during development instead of discovered on the wall.

One wrinkle worth writing down, because this preview depends on it and the
vendored driver states it twice in two different ways. In `display()` the
registers split by colour: `0x10` takes the black image and `0x13` takes the
red one. `display_Partial()` also writes `0x13` - but only after `0x91` has put
the controller into partial mode, and the driver's own comment on that write
reads "Write Black and White image to RAM", with `0x10` pre-filled blank across
the window first. So the register number is the same and its role is not, which
is why HARDWARE.md section 4 can truthfully say partial writes `0x13` and that
there is no partial path to red. Nothing in this file depends on the
resolution; confirming it on the bench belongs to M9, before any partial path
is built.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from render.fonts import FontBook
from view.drawlist import (
    Align,
    Box,
    Colour,
    DrawItem,
    Edge,
    Primitive,
    VAlign,
)

ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "weather-icons"

#: A plane holds ink at 0 and nothing at 255, as the vendored driver expects.
INK = 0
BLANK = 255

#: Roughly the panel's own red. Only the composite BMP uses it; the panel has
#: one red and does not take a value for it.
RED_RGB = (196, 32, 32)
BLACK_RGB = (0, 0, 0)
WHITE_RGB = (255, 255, 255)


@dataclass(frozen=True)
class Planes:
    """The two one-bit images one frame consists of."""

    black: Any
    red: Any


class BMPRenderer:
    """Turns a draw list into BMP files on disk."""

    def __init__(
        self,
        size: tuple[int, int] = (800, 480),
        fonts: FontBook | None = None,
        icon_dir: Path | str | None = None,
    ) -> None:
        self.size = size
        self.fonts = fonts or FontBook()
        self.icon_dir = Path(icon_dir) if icon_dir is not None else ICON_DIR

    def planes(self, items: tuple[DrawItem, ...] | list[DrawItem]) -> Planes:
        """Execute the draw list into a black plane and a red plane."""
        from PIL import Image, ImageDraw

        black = Image.new("1", self.size, BLANK)
        red = Image.new("1", self.size, BLANK)
        surfaces = {
            Colour.BLACK: black,
            Colour.RED: red,
        }
        draws = {Colour.BLACK: ImageDraw.Draw(black), Colour.RED: ImageDraw.Draw(red)}

        for item in items:
            for plane, fill in self._targets(item.colour):
                self._draw(item, surfaces[plane], draws[plane], fill)

        return Planes(black=black, red=red)

    def compose(self, planes: Planes) -> Any:
        """The two planes as one three-colour image, red over black."""
        from PIL import Image, ImageChops

        image = Image.new("RGB", self.size, WHITE_RGB)
        image.paste(BLACK_RGB, mask=ImageChops.invert(planes.black.convert("L")))
        image.paste(RED_RGB, mask=ImageChops.invert(planes.red.convert("L")))
        return image

    def render(
        self,
        items: tuple[DrawItem, ...] | list[DrawItem],
        path: str | Path,
        preview_path: str | Path | None = None,
    ) -> Planes:
        """Write the composite, and optionally the black-plane preview."""
        planes = self.planes(items)
        self.compose(planes).save(str(path), "BMP")

        if preview_path is not None:
            planes.black.save(str(preview_path), "BMP")

        return planes

    @staticmethod
    def _targets(colour: Colour) -> tuple[tuple[Colour, int], ...]:
        """Which plane gets ink and which gets cleared, for one colour.

        White is not a colour the panel can draw; it is ink removed from both
        planes, which is how white-on-black text in the header and the outdoor
        row works without a third surface.
        """
        if colour is Colour.BLACK:
            return ((Colour.BLACK, INK), (Colour.RED, BLANK))
        if colour is Colour.RED:
            return ((Colour.RED, INK), (Colour.BLACK, BLANK))
        return ((Colour.BLACK, BLANK), (Colour.RED, BLANK))

    def _draw(self, item: DrawItem, surface: Any, draw: Any, fill: int) -> None:
        if item.primitive is Primitive.FILL:
            draw.rectangle(_corners(item.box), fill=fill)
        elif item.primitive is Primitive.OUTLINE:
            draw.rectangle(_corners(item.box), outline=fill, width=item.thickness)
        elif item.primitive is Primitive.RULE:
            self._draw_rule(item, draw, fill)
        elif item.primitive is Primitive.TEXT:
            self._draw_text(item, draw, fill)
        elif item.primitive is Primitive.ICON:
            self._draw_icon(item, surface, fill)
        elif item.primitive is Primitive.LINE:
            draw.line(list(item.points), fill=fill, width=item.thickness, joint="curve")

    def _draw_rule(self, item: DrawItem, draw: Any, fill: int) -> None:
        """The thin strip along one edge, whole or broken into dashes."""
        strip = _rule_box(item.box, item.edge, item.thickness)
        if not item.dash:
            draw.rectangle(_corners(strip), fill=fill)
            return

        for segment in _dashes(strip, item.dash, item.gap):
            draw.rectangle(_corners(segment), fill=fill)

    def _draw_text(self, item: DrawItem, draw: Any, fill: int) -> None:
        """Place a string inside its box by alignment, from the ascender line.

        Vertical placement uses the font's metrics rather than the string's own
        ink extent, so every value in a row shares a baseline whatever glyphs it
        happens to contain. Centring on ink would drop "23,1" a pixel below
        "Stue" and the table would visibly ripple.
        """
        font = self.fonts.get(item.style)
        inner = item.box.inset(item.padding, 0)
        ascent, descent = font.getmetrics()

        width = int(draw.textlength(item.text, font=font))
        if item.align is Align.RIGHT:
            x = inner.right - width
        elif item.align is Align.CENTER:
            x = inner.x + (inner.width - width) // 2
        else:
            x = inner.x

        if item.valign is VAlign.TOP:
            y = inner.y
        elif item.valign is VAlign.BOTTOM:
            y = inner.bottom - (ascent + descent)
        else:
            y = inner.y + (inner.height - (ascent + descent)) // 2

        draw.text((x, y), item.text, font=font, fill=fill)

    def _draw_icon(self, item: DrawItem, surface: Any, fill: int) -> None:
        """Paste a pre-rendered mono bitmap, using its ink as the mask.

        The assets are black-on-white BMPs, so the mask is their inverse. A
        missing icon raises: unlike a missing sensor, an asset the code names
        and the repository does not contain is a developer error.
        """
        from PIL import Image, ImageChops

        path = self.icon_dir / f"{item.icon}-{item.icon_size}x{item.icon_size}.bmp"
        if not path.is_file():
            raise FileNotFoundError(f"icon not found: {path}")

        with Image.open(path) as opened:
            mask = ImageChops.invert(opened.convert("L"))

        inner = item.box
        if item.align is Align.RIGHT:
            x = inner.right - mask.width
        elif item.align is Align.CENTER:
            x = inner.x + (inner.width - mask.width) // 2
        else:
            x = inner.x

        if item.valign is VAlign.TOP:
            y = inner.y
        elif item.valign is VAlign.BOTTOM:
            y = inner.bottom - mask.height
        else:
            y = inner.y + (inner.height - mask.height) // 2

        surface.paste(fill, (x, y), mask=mask)


def _corners(box: Box) -> tuple[int, int, int, int]:
    """PIL's rectangle takes an inclusive bottom-right corner."""
    return (box.x, box.y, box.right - 1, box.bottom - 1)


def _dashes(strip: Box, dash: int, gap: int) -> list[Box]:
    """A rule strip cut into dashes along whichever way it runs.

    The first dash starts at the strip's own beginning and the last is clipped
    rather than dropped, so a gridline always meets both edges of the plot it
    crosses - a dotted line that stops short reads as a shorter line.
    """
    horizontal = strip.width >= strip.height
    length = strip.width if horizontal else strip.height

    segments = []
    for offset in range(0, length, dash + gap):
        run = min(dash, length - offset)
        segments.append(
            Box(strip.x + offset, strip.y, run, strip.height)
            if horizontal
            else Box(strip.x, strip.y + offset, strip.width, run)
        )

    return segments


def _rule_box(box: Box, edge: Edge, thickness: int) -> Box:
    """The thin strip along one edge of a box.

    The box itself stays whatever the layout allocated - it is the refresh
    window, and a two-pixel-wide window could never be byte-aligned on x.
    """
    if edge is Edge.TOP:
        return Box(box.x, box.y, box.width, thickness)
    if edge is Edge.BOTTOM:
        return Box(box.x, box.bottom - thickness, box.width, thickness)
    if edge is Edge.LEFT:
        return Box(box.x, box.y, thickness, box.height)
    return Box(box.right - thickness, box.y, thickness, box.height)
