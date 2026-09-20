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

#: Where INTENT.md section 3 permits red, as region suffixes.
RED_SUFFIXES = (".marker", ".temperature", ".humidity")


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

    def test_the_left_column_is_still_empty(self):
        """M5 fills it. Delete this test then - it is a note, not a requirement."""
        config = load_house(HOUSE)
        left = [item for item in screen(snapshot(config)) if item.box.right <= 392]

        assert left == []


class TestTheRefreshContract:
    def test_the_whole_screen_is_a_legal_draw_list(self, items):
        assert violations(items) == ()

    def test_red_appears_only_where_intent_permits_it(self, items):
        red = {item.region for item in items if item.colour is Colour.RED}

        assert red, "the recorded house has alerts; a frame with no red means a broken mapping"
        assert all(region.endswith(RED_SUFFIXES) for region in red)

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

    def test_the_full_only_regions_are_exactly_the_room_values(self, items):
        """The count PLAN.md M9 has to be decided on, pinned so it cannot drift.

        Every full-only region on this screen is a room value cell or an alert
        marker, and every one of them is full-only because it *could* be red,
        not because it is red today. Nothing else on the screen has to wait for
        the 26-second cycle.

        If this ever swings far toward partial, partial refresh has become worth
        building. Today it carries names, labels, rules, the outdoor row and the
        summary - and the clock, which is the only one of them that moves.
        """
        classes = {item.region: item.update for item in items}
        full = {region for region, update in classes.items() if update is UpdateClass.FULL}
        alerting = {region for region in full if region.endswith(".marker")}

        indoor = 10
        assert len(full) == indoor * 2 + len(alerting)
        assert all(region.endswith(RED_SUFFIXES) for region in full)

        header_and_divider = 3 + 1
        column_head = 1
        room_names = indoor
        row_rules = indoor  # one under every room but the last
        outdoor_row = 4  # fill, name, temperature, humidity - never judged
        summary = 4  # rule, headline, and one statistics line per axis

        assert len(classes) - len(full) == (
            header_and_divider + column_head + room_names + row_rules + outdoor_row + summary
        )
