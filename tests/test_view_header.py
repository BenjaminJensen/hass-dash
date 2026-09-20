"""The inverted bar, and the one thing on screen that changes every cycle.

The updated-at clock is the reason a partial refresh has anything to do at all,
so the assertions about its update class matter more than the assertions about
its text.
"""

from __future__ import annotations

from datetime import datetime, timezone

from domain.format_da import PLACEHOLDER
from view.boxes import screen_boxes
from view.drawlist import Colour, Primitive, UpdateClass, violations
from view.header import header

WINTER = datetime(2026, 1, 3, 13, 32, tzinfo=timezone.utc)
SUMMER = datetime(2026, 9, 19, 12, 32, tzinfo=timezone.utc)


def draw(taken_at):
    return header(taken_at, screen_boxes().header)


def texts(items):
    return [item.text for item in items if item.primitive is Primitive.TEXT]


class TestContent:
    def test_it_writes_the_danish_date_and_the_local_time(self):
        """13.32 UTC in January is 14.32 in Copenhagen."""
        assert texts(draw(WINTER)) == ["Lørdag 3. januar", "OPDATERET 14.32"]

    def test_it_follows_the_clock_into_summer_time(self):
        """12.32 UTC in September is 14.32 in Copenhagen."""
        assert texts(draw(SUMMER)) == ["Lørdag 19. september", "OPDATERET 14.32"]

    def test_a_frame_with_no_timestamp_draws_placeholders(self):
        assert texts(draw(None)) == [PLACEHOLDER, f"OPDATERET {PLACEHOLDER}"]


class TestAppearance:
    def test_the_bar_is_filled_black_and_written_in_white(self):
        items = draw(SUMMER)

        assert items[0].primitive is Primitive.FILL
        assert items[0].colour is Colour.BLACK
        assert {item.colour for item in items[1:]} == {Colour.WHITE}

    def test_the_date_is_on_the_left_and_the_clock_on_the_right(self):
        _, date, meta = draw(SUMMER)

        assert date.box.right == meta.box.x


class TestTheRefreshContract:
    def test_the_whole_bar_is_partial_eligible(self):
        """Nothing here can be red, and the clock has to move between full cycles."""
        assert {item.update for item in draw(SUMMER)} == {UpdateClass.PARTIAL}

    def test_it_produces_a_legal_draw_list(self):
        assert violations(draw(SUMMER)) == ()

    def test_it_produces_a_legal_draw_list_with_no_timestamp(self):
        assert violations(draw(None)) == ()
