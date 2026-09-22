"""The draw list, and the three invariants it exists to make checkable.

INTENT.md section 4 states the refresh contract in prose. This file is where
the prose becomes something that fails a build. Each invariant gets both a case
that violates it and a case that does not, and `TestTheCheckItself` proves the
checker can actually fail - a validator that always returns an empty tuple is
worse than no validator, because it reads like protection.
"""

from __future__ import annotations

from view.drawlist import (
    BYTE_ALIGNMENT,
    Align,
    Box,
    Colour,
    Edge,
    Primitive,
    TextStyle,
    UpdateClass,
    draw_fill,
    draw_icon,
    draw_line,
    draw_outline,
    draw_rule,
    draw_text,
    inconsistent_regions,
    region_classes,
    region_colours,
    violations,
)

ALIGNED = Box(8, 0, 16, 10)


def label(region="label", box=ALIGNED, colour=Colour.BLACK, update=UpdateClass.PARTIAL):
    return draw_text(region, box, "x", TextStyle.ROOM_NAME, update, colour=colour)


class TestBox:
    def test_edges(self):
        box = Box(10, 20, 30, 40)

        assert (box.right, box.bottom) == (40, 60)

    def test_inset_shrinks_on_both_sides(self):
        assert Box(0, 0, 100, 50).inset(10, 5) == Box(10, 5, 80, 40)

    def test_inset_takes_one_argument_for_both_axes(self):
        assert Box(0, 0, 100, 50).inset(10) == Box(10, 10, 80, 30)

    def test_top_and_below_tile_the_whole_box(self):
        box = Box(0, 36, 400, 444)
        top = box.top(130)
        rest = box.below(130)

        assert top.y == box.y
        assert top.bottom == rest.y
        assert rest.bottom == box.bottom

    def test_bottom_slice_ends_at_the_bottom(self):
        box = Box(0, 36, 400, 444)

        assert box.bottom_slice(84) == Box(0, 480 - 84, 400, 84)

    def test_columns_tile_left_to_right_without_gaps(self):
        a, b, c = Box(400, 0, 400, 30).columns(24, 184, 96)

        assert a.x == 400
        assert a.right == b.x
        assert b.right == c.x
        assert c.right == 704

    def test_stack_tiles_downward_without_gaps(self):
        rows = Box(400, 62, 400, 90).stack(3, 30)

        assert [row.y for row in rows] == [62, 92, 122]
        assert rows[-1].bottom == 152

    def test_byte_alignment_is_about_both_x_edges(self):
        assert Box(400, 0, 400, 10).is_byte_aligned is True
        assert Box(401, 0, 400, 10).is_byte_aligned is False
        assert Box(400, 0, 399, 10).is_byte_aligned is False

    def test_the_alignment_constant_is_the_panel_s(self):
        """`display_Partial` snaps to whole bytes, and a byte is eight pixels."""
        assert BYTE_ALIGNMENT == 8


class TestFactories:
    def test_fill_covers_its_box(self):
        item = draw_fill("bar", ALIGNED, Colour.BLACK, UpdateClass.PARTIAL)

        assert item.primitive is Primitive.FILL
        assert item.box == ALIGNED

    def test_rule_remembers_which_edge(self):
        item = draw_rule("r", ALIGNED, Edge.LEFT, UpdateClass.PARTIAL, thickness=2)

        assert (item.primitive, item.edge, item.thickness) == (Primitive.RULE, Edge.LEFT, 2)

    def test_outline_defaults_to_two_pixels(self):
        item = draw_outline("badge", ALIGNED, Colour.RED, UpdateClass.FULL)

        assert (item.primitive, item.thickness) == (Primitive.OUTLINE, 2)

    def test_text_carries_its_alignment_and_style(self):
        item = draw_text(
            "t", ALIGNED, "23,1", TextStyle.ROOM_VALUE, UpdateClass.FULL, align=Align.RIGHT
        )

        assert (item.text, item.style, item.align) == ("23,1", TextStyle.ROOM_VALUE, Align.RIGHT)

    def test_icon_carries_its_name_and_size(self):
        item = draw_icon("i", ALIGNED, "weather-sunny", UpdateClass.FULL, size=100)

        assert (item.primitive, item.icon, item.icon_size) == (Primitive.ICON, "weather-sunny", 100)

    def test_line_carries_its_points(self):
        item = draw_line("l", ALIGNED, ((8, 0), (20, 5)), UpdateClass.FULL, thickness=2)

        assert (item.primitive, item.points, item.thickness) == (
            Primitive.LINE,
            ((8, 0), (20, 5)),
            2,
        )

    def test_line_accepts_any_sequence_and_keeps_a_tuple(self):
        """The layout builds points in a list; a DrawItem is frozen and stays so."""
        item = draw_line("l", ALIGNED, [(8, 0), (20, 5)], UpdateClass.FULL)

        assert item.points == ((8, 0), (20, 5))

    def test_an_unconsidered_item_is_full_by_default(self):
        """The safe default. Claiming a partial path you do not have is the bug."""
        from view.drawlist import DrawItem

        assert DrawItem("x", Primitive.FILL, ALIGNED).update is UpdateClass.FULL


class TestViolations:
    def test_a_well_formed_list_has_none(self):
        items = [
            label(),
            draw_text("value", ALIGNED, "1", TextStyle.ROOM_VALUE, UpdateClass.FULL),
        ]

        assert violations(items) == ()

    def test_red_may_not_be_partial(self):
        """There is no partial path to the red plane. HARDWARE.md section 4."""
        found = violations([label(colour=Colour.RED, update=UpdateClass.PARTIAL)])

        assert len(found) == 1
        assert "no partial path to red" in found[0]

    def test_red_is_fine_when_it_is_full(self):
        assert violations([label(colour=Colour.RED, update=UpdateClass.FULL)]) == ()

    def test_a_partial_box_must_be_byte_aligned(self):
        found = violations([label(box=Box(401, 0, 16, 10))])

        assert len(found) == 1
        assert "multiple of 8" in found[0]

    def test_a_full_box_need_not_be_byte_aligned(self):
        """Only the partial window snaps. A full refresh writes the whole frame."""
        assert violations([label(box=Box(401, 0, 15, 10), update=UpdateClass.FULL)]) == ()

    def test_a_region_may_not_mix_update_classes(self):
        items = [label(region="row"), label(region="row", update=UpdateClass.FULL)]
        found = violations(items)

        assert len(found) == 1
        assert "one region is one refresh window" in found[0]

    def test_an_empty_box_is_a_mistake(self):
        found = violations([label(box=Box(8, 0, 0, 10))])

        assert any("empty box" in line for line in found)

    def test_text_with_nothing_to_draw_is_a_mistake(self):
        item = draw_text("t", ALIGNED, "", TextStyle.ROOM_NAME, UpdateClass.PARTIAL)

        assert any("nothing to draw" in line for line in violations([item]))

    def test_a_line_needs_two_points_to_be_a_line(self):
        found = violations([draw_line("l", ALIGNED, ((8, 0),), UpdateClass.FULL)])

        assert any("fewer than two points" in line for line in found)

    def test_a_line_may_not_leave_its_box(self):
        """The box is the refresh window. Ink outside it is ink nothing repaints."""
        found = violations([draw_line("l", ALIGNED, ((8, 0), (40, 5)), UpdateClass.FULL)])

        assert any("leaves its box" in line for line in found)

    def test_a_line_inside_its_box_is_fine(self):
        """The right and bottom edges are exclusive, as a box is everywhere else."""
        points = ((ALIGNED.x, ALIGNED.y), (ALIGNED.right - 1, ALIGNED.bottom - 1))

        assert violations([draw_line("l", ALIGNED, points, UpdateClass.FULL)]) == ()

    def test_a_dash_with_no_gap_is_a_solid_line_pretending(self):
        item = draw_rule("g", ALIGNED, Edge.TOP, UpdateClass.FULL, dash=2)

        assert any("only with a gap" in line for line in violations([item]))

    def test_a_dash_on_anything_but_a_rule_would_be_ink_the_renderer_ignores(self):
        from dataclasses import replace

        line = draw_line("l", ALIGNED, ((8, 0), (8, 5)), UpdateClass.FULL)
        item = replace(line, dash=1, gap=4)

        assert any("only means anything on a rule" in entry for entry in violations([item]))

    def test_a_dashed_rule_with_a_gap_is_fine(self):
        item = draw_rule("g", ALIGNED, Edge.TOP, UpdateClass.FULL, dash=1, gap=4)

        assert violations([item]) == ()

    def test_every_problem_is_reported_not_just_the_first(self):
        items = [
            label(region="a", colour=Colour.RED, update=UpdateClass.PARTIAL),
            label(region="b", box=Box(3, 0, 5, 10)),
        ]

        assert len(violations(items)) == 2


class TestInconsistentRegions:
    """INTENT.md section 4's fourth rule, which needs more than one input to see."""

    def test_a_region_that_keeps_its_class_is_fine(self):
        one = (label(region="temp", update=UpdateClass.FULL),)
        two = (label(region="temp", update=UpdateClass.FULL, colour=Colour.RED),)

        assert inconsistent_regions([one, two]) == ()

    def test_a_region_that_goes_full_only_when_alerting_is_named(self):
        """The exact bug: partial while comfortable, full once it is not."""
        calm = (label(region="room.stue.temperature", update=UpdateClass.PARTIAL),)
        alert = (label(region="room.stue.temperature", update=UpdateClass.FULL, colour=Colour.RED),)

        found = inconsistent_regions([calm, alert])

        assert len(found) == 1
        assert "room.stue.temperature" in found[0]

    def test_a_region_absent_from_one_input_is_not_a_change(self):
        """A marker that only exists while alerting has not changed its mind."""
        calm = (label(region="name"),)
        alert = (label(region="name"), label(region="marker", update=UpdateClass.FULL))

        assert inconsistent_regions([calm, alert]) == ()


class TestSummaries:
    def test_region_colours_gathers_every_colour_a_region_uses(self):
        items = [label(region="r", colour=Colour.RED, update=UpdateClass.FULL), label(region="r2")]

        assert region_colours(items) == {"r": {Colour.RED}, "r2": {Colour.BLACK}}

    def test_region_classes_maps_each_region_to_its_class(self):
        assert region_classes([label(region="r")]) == {"r": UpdateClass.PARTIAL}


class TestTheCheckItself:
    """A validator that cannot fail is worse than no validator."""

    def test_violations_is_capable_of_returning_something(self):
        assert violations([label(colour=Colour.RED, update=UpdateClass.PARTIAL)]) != ()

    def test_inconsistent_regions_is_capable_of_returning_something(self):
        lists = [
            (label(region="r", update=UpdateClass.PARTIAL),),
            (label(region="r", update=UpdateClass.FULL),),
        ]

        assert inconsistent_regions(lists) != ()
