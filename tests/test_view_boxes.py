"""The box model: does it tile, does it fit, and is it legal to refresh.

Two properties matter more than any individual coordinate, because both are
silent when broken. Boxes that do not tile leave one-pixel seams that look like
a rendering bug for weeks. Boxes that are not byte-aligned on x are legal until
the first partial refresh grows its window and repaints a neighbour white.

The room count is a parameter throughout: the table is cut for however many
rooms `house.yml` names, and a family adding a room should change the row
height and nothing else.
"""

from __future__ import annotations

import pytest

from view.boxes import (
    COLUMN_HEAD_HEIGHT,
    HEADER_HEIGHT,
    HUMIDITY_WIDTH,
    MARKER_WIDTH,
    NAME_WIDTH,
    RIGHT_MARGIN,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SUMMARY_HEIGHT,
    TEMPERATURE_WIDTH,
    room_table,
    row_cells,
    screen_boxes,
)

ROOMS = 11


def every_box() -> list:
    """Every Box reachable from the screen model, for the blanket assertions."""
    boxes = screen_boxes()
    table = room_table(boxes.right, ROOMS)
    found = [
        boxes.screen,
        boxes.header.box,
        boxes.header.date,
        boxes.header.meta,
        boxes.divider,
        boxes.left.box,
        boxes.left.hero,
        boxes.left.strip,
        boxes.left.curve,
        boxes.left.days,
        boxes.right,
        table.box,
        table.head,
        table.summary.box,
        table.summary.headline,
        table.summary.temperature_stats,
        table.summary.humidity_stats,
    ]
    found.extend(table.rows)
    for row in (table.head, *table.rows, table.summary.headline):
        cells = row_cells(row)
        found.extend([cells.box, cells.marker, cells.name, cells.temperature, cells.humidity])
        found.append(cells.title)
    return found


class TestTheScreen:
    def test_it_is_the_panel(self):
        boxes = screen_boxes()

        assert (boxes.screen.width, boxes.screen.height) == (SCREEN_WIDTH, SCREEN_HEIGHT)

    def test_header_and_body_tile_the_height(self):
        boxes = screen_boxes()

        assert boxes.header.box.bottom == boxes.left.box.y == HEADER_HEIGHT
        assert boxes.left.box.bottom == SCREEN_HEIGHT

    def test_the_two_header_halves_tile_the_width(self):
        boxes = screen_boxes()

        assert boxes.header.date.right == boxes.header.meta.x
        assert boxes.header.meta.right == SCREEN_WIDTH

    def test_left_divider_and_right_tile_the_width(self):
        boxes = screen_boxes()

        assert boxes.left.box.right == boxes.divider.x
        assert boxes.divider.right == boxes.right.x
        assert boxes.right.right == SCREEN_WIDTH

    def test_the_divider_is_wide_enough_to_be_a_legal_partial_window(self):
        """A two-pixel rule lives in an eight-pixel box. That is the whole trick."""
        boxes = screen_boxes()

        assert boxes.divider.width == 8
        assert boxes.divider.is_byte_aligned

    def test_the_left_column_s_four_regions_tile_it_exactly(self):
        left = screen_boxes().left

        assert left.hero.y == left.box.y
        assert left.hero.bottom == left.strip.y
        assert left.strip.bottom == left.curve.y
        assert left.curve.bottom == left.days.y
        assert left.days.bottom == left.box.bottom

    def test_the_left_column_is_empty_but_measured(self):
        """M5 fills it. The box model is not revisited when it does."""
        left = screen_boxes().left

        assert left.hero.height > 0 and left.days.height > 0


class TestTheRoomTable:
    def test_head_rows_and_summary_do_not_overlap(self):
        table = room_table(screen_boxes().right, ROOMS)

        assert table.head.bottom == table.rows[0].y
        assert table.rows[-1].bottom <= table.summary.box.y
        assert table.summary.box.bottom == SCREEN_HEIGHT

    def test_the_rows_tile_each_other(self):
        rows = room_table(screen_boxes().right, ROOMS).rows

        for above, below in zip(rows, rows[1:]):
            assert above.bottom == below.y

    def test_every_room_gets_a_row(self):
        assert len(room_table(screen_boxes().right, ROOMS).rows) == ROOMS

    def test_all_rows_are_the_same_height(self):
        """Nearly-equal rows read as a mistake; the remainder goes above the summary."""
        heights = {row.height for row in room_table(screen_boxes().right, ROOMS).rows}

        assert len(heights) == 1

    @pytest.mark.parametrize("count", [1, 6, 8, 11, 14])
    def test_the_table_fits_whatever_the_configuration_names(self, count):
        right = screen_boxes().right
        table = room_table(right, count)

        assert len(table.rows) == count
        assert table.rows[0].y >= right.y
        assert table.rows[-1].bottom <= table.summary.box.y

    def test_no_rooms_is_not_a_crash(self):
        """An empty house is a configuration mistake, not a traceback here."""
        table = room_table(screen_boxes().right, 0)

        assert table.rows == ()

    def test_the_row_height_is_what_is_left_over(self):
        right = screen_boxes().right
        available = right.height - COLUMN_HEAD_HEIGHT - SUMMARY_HEIGHT

        assert room_table(right, ROOMS).rows[0].height == available // ROOMS

    def test_the_summary_has_a_headline_and_two_statistics_lines(self):
        summary = room_table(screen_boxes().right, ROOMS).summary

        assert summary.headline.bottom == summary.temperature_stats.y
        assert summary.temperature_stats.bottom == summary.humidity_stats.y
        assert summary.humidity_stats.bottom == summary.box.bottom


class TestRowCells:
    def test_the_cells_tile_left_to_right(self):
        row = room_table(screen_boxes().right, ROOMS).rows[0]
        cells = row_cells(row)

        assert cells.marker.x == row.x
        assert cells.marker.right == cells.name.x
        assert cells.name.right == cells.temperature.x
        assert cells.temperature.right == cells.humidity.x

    def test_the_cells_leave_a_right_margin(self):
        row = room_table(screen_boxes().right, ROOMS).rows[0]

        assert row_cells(row).humidity.right == row.right - RIGHT_MARGIN

    def test_the_widths_sum_to_the_column(self):
        total = MARKER_WIDTH + NAME_WIDTH + TEMPERATURE_WIDTH + HUMIDITY_WIDTH + RIGHT_MARGIN

        assert total == screen_boxes().right.width

    def test_title_spans_the_marker_and_the_name(self):
        """For a line that has no marker to show, like the summary headline."""
        cells = row_cells(room_table(screen_boxes().right, ROOMS).rows[0])

        assert cells.title.x == cells.marker.x
        assert cells.title.right == cells.name.right


class TestByteAlignment:
    """Every box is a legal partial window, so any union of them is one too."""

    def test_every_box_in_the_model_is_byte_aligned_on_x(self):
        unaligned = [box for box in every_box() if not box.is_byte_aligned]

        assert unaligned == []

    def test_the_check_would_notice(self):
        from view.drawlist import Box

        assert not Box(401, 0, 100, 10).is_byte_aligned
