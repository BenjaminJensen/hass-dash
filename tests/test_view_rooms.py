"""The room table, and the promise that red is spent where INTENT.md says.

Three groups of assertion, in rising order of how much they are worth:

*Content.* The right string in the right cell, placeholders where a sensor is
quiet. These would catch a typo.

*Colour.* Red appears on an alerting room's marker, temperature and humidity,
and in no other region for any input. This is the one that keeps red meaning
"act" (INTENT.md section 2).

*Update class.* A temperature cell is full-only whether or not it is alerting
today, because a region's colour eligibility is a property of the layout rather
than of the data (INTENT.md section 4). `TestTheRefreshContract` drives the
layout over a matrix of every alert state and asserts no region changed its
mind - which is the assertion a hand-written test would never think to make.
"""

from __future__ import annotations

import pytest

from domain.derive import house_summary
from domain.format_da import PLACEHOLDER
from domain.models import Climate, ComfortBand, HouseSummary, Room
from view.boxes import room_table as table_boxes, screen_boxes
from view.drawlist import (
    Colour,
    Primitive,
    UpdateClass,
    inconsistent_regions,
    violations,
)
from view.rooms import (
    MARKER_TOO_COLD,
    MARKER_TOO_HOT,
    room_table,
    summary_block,
)

BAND = ComfortBand(min_temperature=19.0, max_temperature=24.0, max_humidity=60.0)


def make_room(key="stue", temperature=21.0, humidity=45.0, comfort=BAND, **kwargs):
    return Room(
        key=key,
        name=kwargs.pop("name", key.title()),
        climate=Climate(temperature=temperature, humidity=humidity),
        comfort=comfort,
        **kwargs,
    )


def draw(rooms):
    boxes = screen_boxes()
    return room_table(tuple(rooms), table_boxes(boxes.right, len(rooms)))


def region(items, name):
    return [item for item in items if item.region == name]


def texts(items):
    return [item.text for item in items if item.primitive is Primitive.TEXT]


class TestContent:
    def test_a_room_draws_its_name_temperature_and_humidity(self):
        items = draw([make_room(temperature=23.14, humidity=44.0)])

        assert texts(region(items, "room.stue.name")) == ["Stue"]
        assert texts(region(items, "room.stue.temperature")) == ["23,1°"]
        assert texts(region(items, "room.stue.humidity")) == ["44 %"]

    def test_a_quiet_sensor_draws_a_placeholder_not_a_zero(self):
        items = draw([make_room(temperature=None, humidity=None)])

        assert texts(region(items, "room.stue.temperature")) == [PLACEHOLDER]
        assert texts(region(items, "room.stue.humidity")) == [PLACEHOLDER]

    def test_the_column_head_labels_the_three_columns(self):
        assert set(texts(region(draw([make_room()]), "rooms.head"))) == {"RUM", "TEMP", "RF"}

    def test_rooms_are_drawn_in_configuration_order(self):
        rooms = [make_room("b", order=1, name="B"), make_room("a", order=0, name="A")]
        items = draw(rooms)

        first = region(items, "room.a.name")[0]
        second = region(items, "room.b.name")[0]

        assert first.box.y < second.box.y

    def test_the_outdoor_row_is_drawn_last_whatever_its_order(self):
        rooms = [
            make_room("ude", order=0, is_outdoor=True, comfort=ComfortBand()),
            make_room("stue", order=5),
        ]
        items = draw(rooms)

        assert region(items, "room.ude.name")[0].box.y > region(items, "room.stue.name")[0].box.y

    def test_a_room_with_no_box_left_is_dropped_not_drawn_off_the_panel(self):
        boxes = screen_boxes()
        rooms = tuple(make_room(f"r{i}", name=f"R{i}", order=i) for i in range(12))
        items = room_table(rooms, table_boxes(boxes.right, 8))

        assert region(items, "room.r7.name") != []
        assert region(items, "room.r8.name") == []


class TestColour:
    def test_a_comfortable_room_is_entirely_black(self):
        items = draw([make_room(temperature=21.0, humidity=45.0)])

        assert {item.colour for item in items} == {Colour.BLACK}

    def test_too_hot_draws_an_upward_marker_and_a_red_temperature(self):
        items = draw([make_room(temperature=26.0)])

        assert texts(region(items, "room.stue.marker")) == [MARKER_TOO_HOT]
        assert region(items, "room.stue.marker")[0].colour is Colour.RED
        assert region(items, "room.stue.temperature")[0].colour is Colour.RED

    def test_too_cold_draws_a_downward_marker(self):
        items = draw([make_room(temperature=14.0)])

        assert texts(region(items, "room.stue.marker")) == [MARKER_TOO_COLD]

    def test_a_comfortable_room_has_no_marker_at_all(self):
        """An arrow that is always there is decoration, and decoration spends red."""
        assert region(draw([make_room()]), "room.stue.marker") == []

    def test_too_humid_draws_a_red_badge_around_a_red_value(self):
        items = region(draw([make_room(humidity=72.0)]), "room.stue.humidity")

        assert {item.colour for item in items} == {Colour.RED}
        assert Primitive.OUTLINE in {item.primitive for item in items}

    def test_a_room_with_no_comfort_band_is_never_red(self):
        """Unjudged is not the same as fine, and neither of them is red."""
        items = draw([make_room(temperature=40.0, humidity=99.0, comfort=ComfortBand())])

        assert {item.colour for item in items} == {Colour.BLACK}

    def test_red_appears_only_where_intent_permits_it(self):
        """Marker, temperature, humidity. Nowhere else, for any input."""
        rooms = [
            make_room("hot", temperature=30.0, humidity=80.0),
            make_room("cold", temperature=5.0, humidity=10.0),
            make_room("gone", temperature=None, humidity=None),
        ]
        red = {item.region for item in draw(rooms) if item.colour is Colour.RED}

        assert red == {
            "room.hot.marker",
            "room.hot.temperature",
            "room.hot.humidity",
            "room.cold.marker",
            "room.cold.temperature",
        }


class TestTheOutdoorRow:
    """Inverted, and therefore reported rather than judged."""

    def test_it_is_filled_black_and_written_in_white(self):
        items = draw([make_room("ude", is_outdoor=True, comfort=ComfortBand())])
        fill = region(items, "room.ude.row")

        row = [item for item in items if item.region.startswith("room.ude.")]

        assert fill[0].primitive is Primitive.FILL
        assert fill[0].colour is Colour.BLACK
        assert {item.colour for item in row if item.primitive is Primitive.TEXT} == {Colour.WHITE}

    def test_it_stays_white_even_when_its_readings_would_alert(self):
        """Red on black is invisible, so this row does not try. See rooms.py."""
        items = draw([make_room("ude", temperature=40.0, humidity=99.0, is_outdoor=True)])
        row = [item for item in items if item.region.startswith("room.ude.")]

        assert Colour.RED not in {item.colour for item in row}

    def test_it_is_therefore_partial_eligible(self):
        """The one row whose values a partial refresh can carry."""
        items = draw([make_room("ude", temperature=40.0, is_outdoor=True)])
        classes = {item.update for item in region(items, "room.ude.temperature")}

        assert classes == {UpdateClass.PARTIAL}


class TestTheSummary:
    def test_it_reports_the_house_mean_of_the_indoor_rooms(self):
        rooms = [
            make_room("a", temperature=20.0, humidity=40.0),
            make_room("b", temperature=22.0, humidity=50.0),
            make_room("ude", temperature=5.0, humidity=90.0, is_outdoor=True),
        ]
        headline = texts(region(draw(rooms), "summary.headline"))

        assert headline == ["HUSET · 2 RUM", "21,0°", "45 %"]

    def test_it_says_so_when_a_sensor_is_missing(self):
        """A mean over eight rooms presented as a mean over ten is a small lie."""
        rooms = [make_room("a", temperature=20.0), make_room("b", temperature=None)]

        assert texts(region(draw(rooms), "summary.headline"))[0] == "HUSET · 1/2 RUM"

    def test_it_reports_the_spread_that_the_mean_hides(self):
        rooms = [make_room("a", temperature=19.0), make_room("b", temperature=23.0)]
        line = texts(region(draw(rooms), "summary.temperature"))[0]

        assert "SPREDN. 4,0°" in line
        assert "MIN 19,0°" in line and "MAKS 23,0°" in line

    def test_a_house_with_nothing_to_report_draws_placeholders_not_zeros(self):
        boxes = table_boxes(screen_boxes().right, 1).summary
        items = summary_block(HouseSummary(room_count=3), boxes)

        assert texts(region(items, "summary.headline")) == [
            "HUSET · 0/3 RUM",
            PLACEHOLDER,
            PLACEHOLDER,
        ]

    def test_the_summary_is_never_red(self):
        """An average is not something a person acts on."""
        rooms = [make_room("a", temperature=40.0, humidity=99.0) for _ in range(1)]
        summary = house_summary(tuple(rooms))
        items = summary_block(summary, table_boxes(screen_boxes().right, 1).summary)

        assert {item.colour for item in items} == {Colour.BLACK}

    def test_the_whole_summary_is_partial_eligible(self):
        """The one block of real data a partial refresh can carry in full."""
        items = summary_block(HouseSummary(), table_boxes(screen_boxes().right, 1).summary)

        assert {item.update for item in items} == {UpdateClass.PARTIAL}


class TestTheRefreshContract:
    """INTENT.md section 4, checked over inputs rather than asserted once."""

    MATRIX = (
        ("comfortable", 21.0, 45.0),
        ("too hot", 30.0, 45.0),
        ("too cold", 5.0, 45.0),
        ("too humid", 21.0, 80.0),
        ("both", 30.0, 80.0),
        ("missing", None, None),
    )

    def lists(self):
        return [
            draw(
                [
                    make_room("stue", temperature=t, humidity=h),
                    make_room("ude", temperature=t, humidity=h, is_outdoor=True),
                ]
            )
            for _, t, h in self.MATRIX
        ]

    def test_no_region_changes_its_update_class_with_the_data(self):
        assert inconsistent_regions(self.lists()) == ()

    @pytest.mark.parametrize("name,temperature,humidity", MATRIX)
    def test_every_input_produces_a_legal_draw_list(self, name, temperature, humidity):
        rooms = [make_room("stue", temperature=temperature, humidity=humidity)]

        assert violations(draw(rooms)) == ()

    @pytest.mark.parametrize("cell", ["temperature", "humidity"])
    def test_a_value_cell_is_full_only_even_while_comfortable(self, cell):
        """The whole point: today's reading does not decide tomorrow's window."""
        items = region(draw([make_room(temperature=21.0, humidity=45.0)]), f"room.stue.{cell}")

        assert {item.update for item in items} == {UpdateClass.FULL}

    def test_names_and_labels_stay_partial_eligible(self):
        items = draw([make_room()])
        partial = {item.region for item in items if item.update is UpdateClass.PARTIAL}

        assert "room.stue.name" in partial
        assert "rooms.head" in partial
        assert "summary.headline" in partial

    def test_the_matrix_actually_exercises_red(self):
        """Guards against a matrix of inputs that all happen to be comfortable."""
        reds = {
            item.region for items in self.lists() for item in items if item.colour is Colour.RED
        }

        assert reds == {"room.stue.marker", "room.stue.temperature", "room.stue.humidity"}
