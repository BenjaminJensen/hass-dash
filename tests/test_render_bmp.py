"""The renderer, asserted on pixels - which is the one place pixels belong.

Everywhere else the tests assert on the draw list so they survive a font
change. Here the whole point is that the draw list reaches the glass correctly,
so these read individual pixels out of the two planes.

The plane convention under test: a plane is a PIL `"1"` image where 255 is
blank and 0 is ink, matching what the vendored driver's `getbuffer()` expects
to be handed (HARDWARE.md section 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from render.bmp import BLANK, INK, RED_RGB, BMPRenderer
from render.fonts import STYLES, FontBook
from view.boxes import COLUMN_HEAD_HEIGHT, room_table, screen_boxes
from view.drawlist import (
    Align,
    Box,
    Colour,
    Edge,
    TextStyle,
    UpdateClass,
    draw_fill,
    draw_icon,
    draw_outline,
    draw_rule,
    draw_text,
)

SIZE = (64, 32)
BOX = Box(8, 8, 16, 16)


@pytest.fixture
def renderer():
    return BMPRenderer(size=SIZE)


def ink_pixels(plane) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(plane.height)
        for x in range(plane.width)
        if plane.getpixel((x, y)) == INK
    }


class TestPlanes:
    def test_an_empty_frame_is_two_blank_planes(self, renderer):
        planes = renderer.planes([])

        assert planes.black.size == SIZE
        assert planes.black.mode == "1"
        assert ink_pixels(planes.black) == set()
        assert ink_pixels(planes.red) == set()

    def test_a_black_fill_inks_the_black_plane_only(self, renderer):
        planes = renderer.planes([draw_fill("f", BOX, Colour.BLACK, UpdateClass.FULL)])

        assert planes.black.getpixel((8, 8)) == INK
        assert planes.black.getpixel((23, 23)) == INK
        assert planes.black.getpixel((24, 24)) == BLANK
        assert ink_pixels(planes.red) == set()

    def test_a_red_fill_inks_the_red_plane_only(self, renderer):
        planes = renderer.planes([draw_fill("f", BOX, Colour.RED, UpdateClass.FULL)])

        assert planes.red.getpixel((8, 8)) == INK
        assert ink_pixels(planes.black) == set()

    def test_red_over_black_leaves_the_pixel_in_one_plane(self):
        """A pixel is one colour. Drawing red clears the black underneath it."""
        renderer = BMPRenderer(size=SIZE)
        planes = renderer.planes(
            [
                draw_fill("bg", BOX, Colour.BLACK, UpdateClass.FULL),
                draw_fill("fg", Box(8, 8, 8, 8), Colour.RED, UpdateClass.FULL),
            ]
        )

        assert planes.red.getpixel((8, 8)) == INK
        assert planes.black.getpixel((8, 8)) == BLANK
        assert planes.black.getpixel((20, 20)) == INK

    def test_white_removes_ink_from_both_planes(self):
        """White is not a colour the panel draws. It is how inverted text works."""
        renderer = BMPRenderer(size=SIZE)
        planes = renderer.planes(
            [
                draw_fill("bg", BOX, Colour.BLACK, UpdateClass.FULL),
                draw_fill("hole", Box(8, 8, 8, 8), Colour.WHITE, UpdateClass.PARTIAL),
            ]
        )

        assert planes.black.getpixel((8, 8)) == BLANK
        assert planes.black.getpixel((20, 20)) == INK
        assert ink_pixels(planes.red) == set()


class TestPrimitives:
    def test_an_outline_inks_the_border_and_not_the_middle(self, renderer):
        planes = renderer.planes(
            [draw_outline("o", BOX, Colour.BLACK, UpdateClass.FULL, thickness=2)]
        )

        assert planes.black.getpixel((8, 8)) == INK
        assert planes.black.getpixel((9, 9)) == INK
        assert planes.black.getpixel((12, 12)) == BLANK

    @pytest.mark.parametrize(
        "edge,inked,blank",
        [
            (Edge.TOP, (12, 8), (12, 23)),
            (Edge.BOTTOM, (12, 23), (12, 8)),
            (Edge.LEFT, (8, 12), (23, 12)),
            (Edge.RIGHT, (23, 12), (8, 12)),
        ],
    )
    def test_a_rule_is_drawn_along_the_edge_it_names(self, renderer, edge, inked, blank):
        """The box stays the refresh window; only the thin strip gets ink."""
        planes = renderer.planes([draw_rule("r", BOX, edge, UpdateClass.PARTIAL)])

        assert planes.black.getpixel(inked) == INK
        assert planes.black.getpixel(blank) == BLANK

    def test_text_lands_inside_its_box(self, renderer):
        box = Box(0, 0, 64, 32)
        planes = renderer.planes([draw_text("t", box, "8", TextStyle.ROOM_VALUE, UpdateClass.FULL)])
        inked = ink_pixels(planes.black)

        assert inked
        assert all(0 <= x < 64 and 0 <= y < 32 for x, y in inked)

    def test_right_aligned_text_ends_at_the_padded_right_edge(self, renderer):
        box = Box(0, 0, 64, 32)
        planes = renderer.planes(
            [
                draw_text(
                    "t",
                    box,
                    "88",
                    TextStyle.ROOM_VALUE,
                    UpdateClass.FULL,
                    align=Align.RIGHT,
                    padding=6,
                )
            ]
        )
        rightmost = max(x for x, _ in ink_pixels(planes.black))

        assert 54 <= rightmost <= 58

    def test_left_aligned_text_starts_at_the_padded_left_edge(self, renderer):
        box = Box(0, 0, 64, 32)
        planes = renderer.planes(
            [draw_text("t", box, "88", TextStyle.ROOM_VALUE, UpdateClass.FULL, padding=6)]
        )
        leftmost = min(x for x, _ in ink_pixels(planes.black))

        assert 6 <= leftmost <= 10

    def test_two_different_strings_share_a_baseline(self):
        """Centring on ink extent instead of font metrics makes the table ripple.

        Both strings here sit flat on the baseline - no comma, no descender - so
        their lowest inked row *is* the baseline. Centring on ink would put the
        shorter one lower and every room row would sit at its own height.
        """
        renderer = BMPRenderer(size=(128, 32))
        box = Box(0, 0, 128, 32)
        bottoms = []
        for text in ("231", "Stue"):
            planes = renderer.planes(
                [draw_text("t", box, text, TextStyle.ROOM_VALUE, UpdateClass.FULL)]
            )
            bottoms.append(max(y for _, y in ink_pixels(planes.black)))

        assert bottoms[0] == bottoms[1]

    def test_a_descender_hangs_below_the_baseline_rather_than_moving_it(self):
        """The comma in "23,1" drops; the digits do not move up to compensate."""
        renderer = BMPRenderer(size=(128, 32))
        box = Box(0, 0, 128, 32)
        tops = []
        for text in ("231", "23,1"):
            planes = renderer.planes(
                [draw_text("t", box, text, TextStyle.ROOM_VALUE, UpdateClass.FULL)]
            )
            tops.append(min(y for _, y in ink_pixels(planes.black)))

        assert tops[0] == tops[1]

    def test_an_icon_is_pasted_from_the_asset_tree(self):
        renderer = BMPRenderer(size=(128, 128))
        planes = renderer.planes(
            [draw_icon("i", Box(0, 0, 128, 128), "weather-sunny", UpdateClass.FULL, size=100)]
        )

        assert len(ink_pixels(planes.black)) > 100

    def test_a_missing_icon_is_a_developer_error_not_a_placeholder(self, renderer):
        """Unlike a missing sensor. The repository controls its own assets."""
        with pytest.raises(FileNotFoundError):
            renderer.planes([draw_icon("i", BOX, "weather-nonexistent", UpdateClass.FULL)])


class TestComposite:
    def test_blank_planes_compose_to_white(self, renderer):
        image = renderer.compose(renderer.planes([]))

        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 255, 255)

    def test_black_ink_composes_to_black(self, renderer):
        image = renderer.compose(
            renderer.planes([draw_fill("f", BOX, Colour.BLACK, UpdateClass.FULL)])
        )

        assert image.getpixel((8, 8)) == (0, 0, 0)

    def test_red_ink_composes_to_red(self, renderer):
        image = renderer.compose(
            renderer.planes([draw_fill("f", BOX, Colour.RED, UpdateClass.FULL)])
        )

        assert image.getpixel((8, 8)) == RED_RGB


class TestRenderToDisk:
    def test_it_writes_a_three_colour_composite(self, tmp_path, renderer):
        out = tmp_path / "screen.bmp"
        renderer.render([draw_fill("f", BOX, Colour.RED, UpdateClass.FULL)], out)

        with Image.open(out) as written:
            assert written.size == SIZE
            assert written.convert("RGB").getpixel((8, 8)) == RED_RGB

    def test_the_preview_is_the_black_plane_with_the_red_missing(self, tmp_path, renderer):
        """Exactly what a partial refresh could carry, and no more."""
        out = tmp_path / "screen.bmp"
        preview = tmp_path / "preview.bmp"
        renderer.render(
            [
                draw_fill("black", Box(8, 8, 8, 8), Colour.BLACK, UpdateClass.PARTIAL),
                draw_fill("red", Box(24, 8, 8, 8), Colour.RED, UpdateClass.FULL),
            ],
            out,
            preview,
        )

        with Image.open(preview) as written:
            assert written.mode == "1"
            assert written.getpixel((8, 8)) == INK
            assert written.getpixel((24, 8)) == BLANK

    def test_no_preview_is_written_when_none_is_asked_for(self, tmp_path, renderer):
        renderer.render([], tmp_path / "screen.bmp")

        assert list(tmp_path.iterdir()) == [tmp_path / "screen.bmp"]


class TestFonts:
    def test_every_style_the_view_can_name_has_a_face(self):
        assert set(STYLES) == set(TextStyle)

    def test_faces_are_loaded_once(self):
        book = FontBook()

        assert book.get(TextStyle.ROOM_VALUE) is book.get(TextStyle.ROOM_VALUE)

    def test_a_missing_font_file_says_which_style_wanted_it(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="room_value"):
            FontBook(tmp_path).get(TextStyle.ROOM_VALUE)

    @pytest.mark.parametrize(
        "style,box_height",
        [
            (TextStyle.HEADER_DATE, 36),
            (TextStyle.HEADER_META, 36),
            (TextStyle.COLUMN_LABEL, COLUMN_HEAD_HEIGHT),
        ],
    )
    def test_a_style_fits_the_box_the_layout_gives_it(self, style, box_height):
        assert FontBook().line_height(style) <= box_height

    @pytest.mark.parametrize(
        "style", [TextStyle.ROOM_NAME, TextStyle.ROOM_VALUE, TextStyle.ROOM_MARKER]
    )
    def test_a_room_style_fits_a_room_row(self, style):
        """The binding constraint: eleven rooms cap the row, the row caps the font."""
        row = room_table(screen_boxes().right, 11).rows[0]

        assert FontBook().line_height(style) <= row.height

    def test_the_summary_styles_fit_their_lines(self):
        summary = room_table(screen_boxes().right, 11).summary
        book = FontBook()

        assert book.line_height(TextStyle.SUMMARY_VALUE) <= summary.headline.height
        assert book.line_height(TextStyle.SUMMARY_STAT) <= summary.temperature_stats.height

    def test_the_fit_check_would_notice_a_font_that_is_too_big(self):
        """A row of 30 pixels cannot hold a 60-pixel face."""
        assert FontBook().line_height(TextStyle.ROOM_VALUE) > 20


def test_the_asset_tree_is_where_the_renderer_thinks_it_is():
    """Guards the parents[2] path arithmetic, which is silent when wrong."""
    from render.bmp import ICON_DIR
    from render.fonts import FONT_DIR

    assert (FONT_DIR / "LiberationSans-Bold.ttf").is_file()
    assert (ICON_DIR / "weather-sunny-100x100.bmp").is_file()
    assert Path(__file__).parent.parent / "assets" == FONT_DIR.parent.parent
