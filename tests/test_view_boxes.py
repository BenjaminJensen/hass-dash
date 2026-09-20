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
    CURVE_AXIS_EVERY,
    CURVE_POINT_STEP,
    CURVE_POINTS,
    DAY_COUNT,
    DAY_WIDTH,
    HEADER_HEIGHT,
    HUMIDITY_WIDTH,
    LEFT_GUTTER,
    LEFT_MARGIN,
    MARKER_WIDTH,
    NAME_WIDTH,
    RIGHT_MARGIN,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SUMMARY_HEIGHT,
    TEMPERATURE_WIDTH,
    curve_boxes,
    day_boxes,
    hero_boxes,
    room_table,
    row_cells,
    screen_boxes,
    strip_boxes,
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

    hero = hero_boxes(boxes.left.hero)
    found.extend([hero.icon, hero.temperature, hero.condition, hero.apparent, hero.range])

    for slot in strip_boxes(boxes.left.strip):
        found.extend([slot.box, slot.label, slot.value])

    curve = curve_boxes(boxes.left.curve)
    found.extend([curve.title, curve.plot, curve.bars, curve.line, curve.axis])

    for day in day_boxes(boxes.left.days):
        found.extend([day.box, day.name, day.icon, day.values])

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

    def test_the_column_s_content_sits_inside_its_margins(self):
        left = screen_boxes().left

        assert left.content.x == left.box.x + LEFT_MARGIN
        assert left.content.right == left.box.right - LEFT_GUTTER

    def test_the_gutter_keeps_content_off_the_column_rule(self):
        """The divider's rule is drawn on its left edge, which is the column's right."""
        boxes = screen_boxes()

        assert boxes.left.content.right < boxes.divider.x


class TestTheLeftColumn:
    """The regions INTENT.md section 3 puts on the weather half."""

    def test_the_hero_splits_two_rows_at_the_same_x(self):
        hero = hero_boxes(screen_boxes().left.hero)

        assert hero.temperature.right == hero.range.x
        assert hero.condition.right == hero.apparent.x
        assert hero.temperature.x == hero.condition.x

    def test_the_icon_sits_left_of_everything_else(self):
        hero = hero_boxes(screen_boxes().left.hero)

        assert hero.icon.right == hero.temperature.x

    def test_the_hero_leaves_its_slack_at_the_bottom_as_a_gap(self):
        """Not as padding inside a box - the gap is what separates hero from strip."""
        hero = hero_boxes(screen_boxes().left.hero)

        assert hero.apparent.bottom < hero.box.bottom

    def test_the_strip_is_six_slots_in_two_rows_of_three(self):
        slots = strip_boxes(screen_boxes().left.strip)

        assert len(slots) == 6
        assert slots[0].box.y == slots[1].box.y == slots[2].box.y
        assert slots[3].box.y == slots[0].box.bottom

    def test_each_slot_stacks_a_label_over_a_value(self):
        slot = strip_boxes(screen_boxes().left.strip)[0]

        assert slot.label.bottom == slot.value.y
        assert slot.value.bottom == slot.box.bottom

    def test_a_slot_row_leaves_slack_under_its_value(self):
        """The only thing separating one row's value from the next row's label."""
        from render.fonts import FontBook
        from view.drawlist import TextStyle

        slot = strip_boxes(screen_boxes().left.strip)[0]

        assert slot.value.height > FontBook().line_height(TextStyle.SLOT_VALUE)

    def test_the_curve_tiles_title_plot_and_axis(self):
        curve = curve_boxes(screen_boxes().left.curve)

        assert curve.title.y == curve.box.y
        assert curve.title.bottom <= curve.plot.y
        assert curve.plot.bottom <= curve.axis.y
        assert curve.axis.bottom == curve.box.bottom

    def test_the_bar_band_is_the_bottom_of_the_plot_and_the_line_the_rest(self):
        curve = curve_boxes(screen_boxes().left.curve)

        assert curve.line.y == curve.plot.y
        assert curve.line.bottom == curve.bars.y
        assert curve.bars.bottom == curve.plot.bottom

    def test_every_plotted_hour_lands_on_a_byte_boundary(self):
        """Which is what lets the axis labels hanging off them be partial windows."""
        curve = curve_boxes(screen_boxes().left.curve)
        labelled = range(0, CURVE_POINTS, CURVE_AXIS_EVERY)

        assert all((curve.plot.x + index * CURVE_POINT_STEP) % 8 == 0 for index in labelled)

    def test_the_last_plotted_hour_stays_inside_the_plot(self):
        curve = curve_boxes(screen_boxes().left.curve)
        last = curve.plot.x + (CURVE_POINTS - 1) * CURVE_POINT_STEP

        assert last < curve.plot.right

    def test_the_day_strip_is_six_equal_columns(self):
        columns = day_boxes(screen_boxes().left.days)

        assert len(columns) == DAY_COUNT
        assert {column.box.width for column in columns} == {DAY_WIDTH}

    def test_the_day_columns_tile_each_other(self):
        columns = day_boxes(screen_boxes().left.days)

        for left, right in zip(columns, columns[1:]):
            assert left.box.right == right.box.x

    def test_the_day_strip_leaves_the_same_gutter_as_everything_above_it(self):
        boxes = screen_boxes()
        columns = day_boxes(boxes.left.days)

        assert columns[-1].box.right == boxes.left.box.right - LEFT_GUTTER

    def test_a_day_column_stacks_a_weekday_an_icon_and_its_values(self):
        day = day_boxes(screen_boxes().left.days)[0]

        assert day.name.bottom == day.icon.y
        assert day.icon.bottom == day.values.y
        assert day.values.bottom == day.box.bottom

    def test_the_icon_cell_fits_the_icon_the_layout_draws_in_it(self):
        from view.boxes import DAY_ICON_SIZE

        day = day_boxes(screen_boxes().left.days)[0]

        assert day.icon.height >= DAY_ICON_SIZE
        assert day.icon.width >= DAY_ICON_SIZE


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
