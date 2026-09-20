"""The hero and the six-slot strip: content, position, colour, update class.

Never pixels. A font change moves every glyph on the screen and must not move a
single assertion here (INTENT.md section 7), so these tests ask what a box
contains and which refresh can carry it - not where the ink landed.

`TestTheRefreshContract` is the important half. It drives the same layout over
rain, snow, drought and a dead weather entity and asserts that no region ever
changes its update class, which is section 4's "if a region could be red for
some input, it is full-only for all inputs" made mechanical.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.format_da import PLACEHOLDER
from domain.models import SunTimes, Weather
from view.boxes import screen_boxes
from view.drawlist import (
    Colour,
    Primitive,
    UpdateClass,
    inconsistent_regions,
    violations,
)
from view.weather import hero, strip

UTC = timezone.utc
BOXES = screen_boxes().left

#: Both fields are *future* transitions, as the sun entity reports them.
SUN = SunTimes(
    next_rising=datetime(2026, 9, 20, 4, 59, tzinfo=UTC),
    next_setting=datetime(2026, 9, 20, 17, 21, tzinfo=UTC),
)

NOMINAL = Weather(
    condition="cloudy",
    temperature=17.7,
    humidity=92.0,
    pressure=1009.5,
    wind_speed=23 / 3.6,
    wind_bearing=237.0,
    temperature_high=17.7,
    temperature_low=16.7,
    precipitation=0.0,
)


def draw_hero(weather=NOMINAL, sun=SUN):
    return hero(weather, sun, BOXES.hero)


def draw_strip(weather=NOMINAL, sun=SUN):
    return strip(weather, sun, BOXES.strip)


def text_of(items, region):
    """The strings one region draws, in order."""
    return [
        item.text for item in items if item.region == region and item.primitive is Primitive.TEXT
    ]


def region_of(items, region):
    return [item for item in items if item.region == region]


class TestTheHero:
    def test_the_current_temperature_is_whole_degrees(self):
        """A tenth of a degree outdoors has never changed anybody's coat."""
        assert text_of(draw_hero(), "weather.temperature") == ["18°"]

    def test_it_is_the_largest_thing_on_the_screen(self):
        from render.fonts import STYLES

        item = region_of(draw_hero(), "weather.temperature")[0]
        largest = max(spec.size for spec in STYLES.values())

        assert STYLES[item.style].size == largest

    def test_the_condition_is_danish(self):
        assert text_of(draw_hero(), "weather.condition") == ["Skyet"]

    def test_the_icon_is_the_condition_s(self):
        icon = [item for item in draw_hero() if item.primitive is Primitive.ICON]

        assert [item.icon for item in icon] == ["weather-cloudy"]

    def test_the_icon_follows_the_sun_below_the_horizon(self):
        """next_rising before next_setting means the sun is down now."""
        night = SunTimes(
            next_rising=datetime(2026, 9, 20, 4, 59, tzinfo=UTC),
            next_setting=datetime(2026, 9, 20, 17, 21, tzinfo=UTC),
        )
        day = SunTimes(
            next_rising=datetime(2026, 9, 21, 4, 59, tzinfo=UTC),
            next_setting=datetime(2026, 9, 20, 17, 21, tzinfo=UTC),
        )
        clear = Weather(condition="sunny")

        assert draw_hero(clear, night)[0].icon == "weather-night"
        assert draw_hero(clear, day)[0].icon == "weather-sunny"

    def test_an_unknown_condition_draws_no_icon_rather_than_a_guess(self):
        items = draw_hero(Weather(condition="meteor-shower"))

        assert [item for item in items if item.primitive is Primitive.ICON] == []

    def test_the_apparent_temperature_is_labelled_and_computed(self):
        assert text_of(draw_hero(), "weather.apparent") == ["Føles som 15°"]

    def test_the_day_s_high_and_low_sit_together(self):
        assert text_of(draw_hero(), "weather.range") == ["18° / 17°"]

    def test_a_dead_weather_entity_draws_placeholders_and_no_traceback(self):
        items = draw_hero(Weather())

        assert text_of(items, "weather.temperature") == [PLACEHOLDER]
        assert text_of(items, "weather.condition") == [PLACEHOLDER]
        assert text_of(items, "weather.apparent") == [f"Føles som {PLACEHOLDER}"]
        assert text_of(items, "weather.range") == [f"{PLACEHOLDER} / {PLACEHOLDER}"]

    def test_the_icon_and_the_big_number_do_not_overlap(self):
        items = draw_hero()
        icon = region_of(items, "weather.icon")[0]
        number = region_of(items, "weather.temperature")[0]

        assert icon.box.right <= number.box.x

    def test_the_two_rows_are_split_at_the_same_x(self):
        """A hole on one row and not the other is what makes a hero look broken."""
        items = draw_hero()

        assert region_of(items, "weather.range")[0].box.x == (
            region_of(items, "weather.apparent")[0].box.x
        )


class TestTheStrip:
    def test_it_draws_six_slots(self):
        regions = {item.region for item in draw_strip()}

        assert regions == {
            "strip.sunrise",
            "strip.sunset",
            "strip.wind",
            "strip.humidity",
            "strip.pressure",
            "strip.precipitation",
        }

    def test_each_slot_is_a_label_over_a_value(self):
        assert text_of(draw_strip(), "strip.pressure") == ["TRYK", "1010 hPa"]

    def test_the_sun_times_are_the_next_ones_local(self):
        """04.59 UTC is 06.59 in Copenhagen; 17.21 UTC is 19.21."""
        items = draw_strip()

        assert text_of(items, "strip.sunrise") == ["SOL OP", "06.59"]
        assert text_of(items, "strip.sunset") == ["SOL NED", "19.21"]

    def test_the_wind_carries_its_direction(self):
        """23 km/h from 237 degrees, in the metres per second a Dane reads."""
        assert text_of(draw_strip(), "strip.wind") == ["VIND", "6,4 m/s SV"]

    def test_a_wind_with_no_bearing_is_just_a_speed(self):
        calm = Weather(wind_speed=3.0)

        assert text_of(draw_strip(calm), "strip.wind") == ["VIND", "3,0 m/s"]

    def test_a_dead_weather_entity_fills_every_slot_with_a_placeholder(self):
        values = [
            text_of(draw_strip(Weather(), SunTimes()), region)[1]
            for region in ("strip.sunrise", "strip.wind", "strip.humidity", "strip.pressure")
        ]

        assert values == [PLACEHOLDER] * 4


class TestWhereTheRedIs:
    """INTENT.md section 3 permits exactly two places on this half of the column."""

    def test_the_condition_goes_red_when_it_is_raining(self):
        item = region_of(draw_hero(Weather(condition="rainy")), "weather.condition")[0]

        assert item.colour is Colour.RED

    def test_the_condition_stays_black_when_it_is_merely_grey(self):
        item = region_of(draw_hero(Weather(condition="cloudy")), "weather.condition")[0]

        assert item.colour is Colour.BLACK

    def test_the_precipitation_value_goes_red_when_there_is_any(self):
        wet = Weather(precipitation=1.4)
        colours = {item.colour for item in region_of(draw_strip(wet), "strip.precipitation")}

        assert Colour.RED in colours

    def test_a_dry_day_spends_no_red_at_all(self):
        items = draw_hero() + draw_strip()

        assert Colour.RED not in {item.colour for item in items}

    def test_nothing_else_is_ever_red(self):
        wet = Weather(condition="pouring", precipitation=9.9, temperature=4.0)
        red = {
            item.region for item in draw_hero(wet) + draw_strip(wet) if item.colour is Colour.RED
        }

        assert red == {"weather.condition", "strip.precipitation"}


class TestTheRefreshContract:
    #: Every kind of day this layout has to survive, including no day at all.
    INPUTS = (
        NOMINAL,
        Weather(condition="pouring", precipitation=9.9),
        Weather(condition="snowy", temperature=-12.0, precipitation=2.0),
        Weather(condition="sunny", temperature=28.0, humidity=20.0, wind_speed=0.5),
        Weather(),
    )

    @pytest.mark.parametrize("weather", INPUTS)
    def test_every_input_produces_a_legal_draw_list(self, weather):
        assert violations(draw_hero(weather) + draw_strip(weather)) == ()

    def test_no_region_changes_its_update_class_with_the_weather(self):
        lists = [draw_hero(weather) + draw_strip(weather) for weather in self.INPUTS]

        assert inconsistent_regions(lists) == ()

    def test_the_regions_that_could_be_red_are_full_for_every_input(self):
        """Full-only on a dry day too, because the class is a property of layout."""
        classes = {item.region: item.update for item in draw_hero() + draw_strip()}
        full = {region for region, update in classes.items() if update is UpdateClass.FULL}

        assert full == {"weather.condition", "strip.precipitation"}

    def test_everything_else_can_ride_a_partial_refresh(self):
        """Most of the moving content on this half of the screen, and that matters."""
        classes = {item.region: item.update for item in draw_hero() + draw_strip()}
        partial = {region for region, update in classes.items() if update is UpdateClass.PARTIAL}

        assert partial == {
            "weather.icon",
            "weather.temperature",
            "weather.apparent",
            "weather.range",
            "strip.sunrise",
            "strip.sunset",
            "strip.wind",
            "strip.humidity",
            "strip.pressure",
        }
