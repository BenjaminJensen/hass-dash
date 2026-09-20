"""The walking skeleton, composed - and driven by the recorded house.

The other view tests build rooms by hand, which is what makes them precise. This
one renders the snapshot actually captured from the live instance on
2026-09-19, because a layout that only ever sees hand-built input is a layout
that has never met eleven rooms at once.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.loader import load_house
from sources.fixture import FixtureSource
from view.drawlist import Colour, UpdateClass, inconsistent_regions, violations
from view.screen import screen

FIXTURES = Path(__file__).parent / "fixtures"
HOUSE = Path(__file__).parent.parent / "house.yml"
FROZEN = datetime(2026, 9, 19, 12, 32, tzinfo=timezone.utc)

#: The three regions outside the room table where INTENT.md section 3 permits
#: red. `curve.plot` holds the precipitation bars; its temperature line is
#: black and shares the window, which is why the whole plot is full-only.
RED_ELSEWHERE = frozenset({"weather.condition", "strip.precipitation", "curve.plot"})


def permitted_red(config):
    """Every region INTENT.md section 3 allows red in, by name.

    By name rather than by suffix, because `weather.temperature` is the largest
    number on the screen and may never be red - a suffix rule would wave it
    through and the assertion would stop meaning anything.
    """
    rooms = {
        f"room.{room.key}.{cell}"
        for room in config.rooms
        if not room.is_outdoor
        for cell in ("marker", "temperature", "humidity")
    }
    return rooms | set(RED_ELSEWHERE)


@pytest.fixture
def config():
    return load_house(HOUSE)


def snapshot(config, name=None):
    directory = FIXTURES if name is None else FIXTURES / "sets" / name
    return FixtureSource(config, directory, clock=lambda: FROZEN).fetch()


@pytest.fixture
def items(config):
    return screen(snapshot(config))


class TestTheComposedScreen:
    def test_it_draws_the_header_the_divider_and_every_room(self, items, config):
        regions = {item.region for item in items}

        assert "header.date" in regions
        assert "divider" in regions
        for room in config.rooms:
            assert f"room.{room.key}.name" in regions

    def test_it_draws_the_summary(self, items):
        assert "summary.headline" in {item.region for item in items}

    def test_nothing_is_drawn_outside_the_panel(self, items):
        outside = [
            item.region
            for item in items
            if item.box.x < 0 or item.box.y < 0 or item.box.right > 800 or item.box.bottom > 480
        ]

        assert outside == []

    def test_it_draws_every_region_of_the_weather_column(self, items):
        """INTENT.md section 3's left half, top to bottom."""
        regions = {item.region for item in items}

        assert {"weather.icon", "weather.temperature", "weather.condition"} <= regions
        assert {f"strip.{slot}" for slot in ("sunrise", "sunset", "wind")} <= regions
        assert {"curve.title", "curve.plot", "curve.axis"} <= regions
        assert "day.0" in regions

    def test_the_two_columns_do_not_reach_into_each_other(self, items):
        """The divider is a seam, not a suggestion.

        The header is exempt: it spans the full width *above* the divider,
        which is what makes it read as a frame rather than as a third column.
        """
        divider = next(item for item in items if item.region == "divider").box
        straddling = [
            item.region
            for item in items
            if item.region != "divider"
            and item.box.y >= divider.y
            and item.box.x < divider.right
            and item.box.right > divider.x
        ]

        assert straddling == []


class TestTheRefreshContract:
    def test_the_whole_screen_is_a_legal_draw_list(self, items):
        assert violations(items) == ()

    def test_red_appears_only_where_intent_permits_it(self, items, config):
        red = {item.region for item in items if item.colour is Colour.RED}

        assert red, "the recorded house has alerts; a frame with no red means a broken mapping"
        assert red <= permitted_red(config)

    def test_the_largest_number_on_the_screen_is_never_red(self, items):
        """Red is for "act". An outdoor temperature is not something to act on."""
        colours = {item.colour for item in items if item.region == "weather.temperature"}

        assert Colour.RED not in colours

    def test_no_region_changes_class_between_a_nominal_and_a_hostile_house(self, config):
        """Same layout, opposite extremes of input. The windows must not move."""
        lists = [screen(snapshot(config, name)) for name in ("nominal", "hostile")]
        lists.append(screen(snapshot(config)))

        assert inconsistent_regions(lists) == ()

    def test_a_house_with_every_sensor_dead_is_still_a_legal_frame(self, config):
        """Absence is a state, not a crash. INTENT.md section 2."""
        items = screen(snapshot(config, "hostile"))

        assert violations(items) == ()
        assert Colour.RED not in {item.colour for item in items}

    def test_the_full_only_regions_are_exactly_the_ones_that_could_be_red(self, items, config):
        """The count PLAN.md M9 has to be decided on, pinned so it cannot drift.

        Every full-only region on this screen is one INTENT.md section 3 allows
        red in, and every one of them is full-only because it *could* be red,
        not because it is red today. Nothing else has to wait for the
        26-second cycle.

        If this ever swings far toward partial, partial refresh has become worth
        building. Today it carries the whole weather column bar three regions,
        the room names, the outdoor row, the summary - and the clock, which is
        the only one of them that moves every cycle.
        """
        classes = {item.region: item.update for item in items}
        full = {region for region, update in classes.items() if update is UpdateClass.FULL}
        alerting = {region for region in full if region.endswith(".marker")}

        assert full <= permitted_red(config)

        indoor = 10
        assert len(full) == indoor * 2 + len(alerting) + len(RED_ELSEWHERE)

        header_and_divider = 3 + 1
        seams = 3  # between the left column's four regions
        column_head = 1
        room_names = indoor
        row_rules = indoor  # one under every room but the last
        outdoor_row = 4  # fill, name, temperature, humidity - never judged
        summary = 4  # rule, headline, and one statistics line per axis
        hero = 4  # icon, temperature, apparent, high/low - never red
        strip_slots = 5  # everything but precipitation
        curve = 2  # the title and the hour labels; the plot holds the bars
        days = 6  # this provider returns six, not seven

        assert len(classes) - len(full) == (
            header_and_divider
            + seams
            + column_head
            + room_names
            + row_rules
            + outdoor_row
            + summary
            + hero
            + strip_slots
            + curve
            + days
        )
