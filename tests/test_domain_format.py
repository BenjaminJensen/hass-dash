"""Tests for the Danish formatting rules.

Comma as decimal separator, dot as time separator, Danish weekday and month
names, Europe/Copenhagen throughout - and a placeholder wherever a value is
missing, because every one of these is reachable with None.
"""

from datetime import datetime, timezone

import pytest

from domain import format_da as fmt

UTC = timezone.utc


class TestNumbers:
    def test_temperature_uses_a_comma_and_a_degree_sign(self):
        assert fmt.temperature(23.14) == "23,1°"

    def test_temperature_places_can_be_dropped_for_the_large_reading(self):
        assert fmt.temperature(17.4, places=0) == "17°"

    def test_negative_temperatures_keep_their_sign(self):
        assert fmt.temperature(-3.25) == "-3,2°"

    def test_humidity_is_whole_percent_with_a_space(self):
        assert fmt.humidity(44.4) == "44 %"

    def test_pressure_and_wind_and_precipitation(self):
        assert fmt.pressure(1013.2) == "1013 hPa"
        assert fmt.wind_speed(4.3) == "4,3 m/s"
        assert fmt.precipitation(1.16) == "1,2 mm"

    def test_decimal_places_are_configurable(self):
        assert fmt.decimal(3.14159, places=3) == "3,142"

    def test_rounding_is_pythons_own_and_is_not_worth_correcting(self):
        """A half-way value rounds to even, and binary floats shift some of them.

        1.15 is stored slightly below 1.15, so it formats as 1,1 rather than
        1,2. At three metres this is invisible, and imposing decimal rounding
        would buy nothing but a dependency. Pinned so the behaviour is a
        decision rather than a surprise.
        """
        assert fmt.decimal(1.15) == "1,1"
        assert fmt.decimal(4.25) == "4,2"


class TestTimes:
    def test_clock_uses_a_dot_and_local_time(self):
        # 12:32 UTC is 14.32 in Copenhagen in September.
        assert fmt.clock(datetime(2026, 9, 19, 12, 32, tzinfo=UTC)) == "14.32"

    def test_clock_pads_to_two_digits(self):
        assert fmt.clock(datetime(2026, 1, 1, 6, 5, tzinfo=UTC)) == "07.05"

    def test_winter_and_summer_offsets_both_apply(self):
        summer = fmt.clock(datetime(2026, 7, 1, 10, 0, tzinfo=UTC))
        winter = fmt.clock(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))

        assert (summer, winter) == ("12.00", "11.00")

    def test_date_long_is_danish(self):
        assert fmt.date_long(datetime(2026, 9, 19, 9, 0, tzinfo=UTC)) == "Lørdag 19. september"

    def test_weekday_short_is_uppercase_three_letters(self):
        assert fmt.weekday_short(datetime(2026, 9, 19, 9, 0, tzinfo=UTC)) == "LØR"

    def test_naive_datetimes_are_treated_as_local_wall_time(self):
        assert fmt.clock(datetime(2026, 9, 19, 14, 32)) == "14.32"

    def test_to_local_converts_an_aware_datetime(self):
        local = fmt.to_local(datetime(2026, 9, 19, 12, 0, tzinfo=UTC))

        assert local.hour == 14
        assert local.utcoffset().total_seconds() == 2 * 3600


class TestMissingValues:
    @pytest.mark.parametrize(
        "formatter",
        [
            fmt.decimal,
            fmt.temperature,
            fmt.humidity,
            fmt.pressure,
            fmt.wind_speed,
            fmt.precipitation,
            fmt.clock,
            fmt.date_long,
            fmt.weekday_short,
            fmt.condition,
            fmt.wind_direction,
            fmt.hour,
        ],
    )
    def test_every_formatter_renders_none_as_the_placeholder(self, formatter):
        assert formatter(None) == fmt.PLACEHOLDER

    def test_to_local_passes_none_through(self):
        assert fmt.to_local(None) is None

    def test_the_placeholder_is_an_en_dash_not_a_hyphen(self):
        assert fmt.PLACEHOLDER == "–"
        assert fmt.PLACEHOLDER != "-"


class TestConditions:
    @pytest.mark.parametrize(
        ("key", "danish"),
        [
            ("sunny", "Sol"),
            ("partlycloudy", "Delvist skyet"),
            ("rainy", "Regn"),
            ("pouring", "Kraftig regn"),
            ("snowy-rainy", "Slud"),
            ("clear-night", "Klar nat"),
            ("fog", "Tåge"),
        ],
    )
    def test_it_renders_home_assistant_s_vocabulary_in_danish(self, key, danish):
        assert fmt.condition(key) == danish

    def test_an_unknown_condition_is_a_placeholder_not_its_key(self):
        """ "windy-variant" on a wall reads as a broken dashboard; a dash does not."""
        assert fmt.condition("meteor-shower") == fmt.PLACEHOLDER

    def test_case_and_surrounding_space_do_not_matter(self):
        assert fmt.condition(" PartlyCloudy ") == "Delvist skyet"

    def test_every_condition_the_icons_cover_has_a_danish_word(self):
        """The two tables are separate on purpose; neither may fall behind."""
        from view.icons import CONDITION_ICONS

        assert set(CONDITION_ICONS) <= set(fmt.CONDITIONS)


class TestWindDirection:
    @pytest.mark.parametrize(
        ("bearing", "point"),
        [
            (0.0, "N"),
            (45.0, "NØ"),
            (90.0, "Ø"),
            (180.0, "S"),
            (237.0, "SV"),
            (270.0, "V"),
            (315.0, "NV"),
        ],
    )
    def test_a_bearing_lands_in_its_compass_point(self, bearing, point):
        assert fmt.wind_direction(bearing) == point

    def test_it_rounds_to_the_nearest_point_rather_than_flooring(self):
        """23 degrees is nearer north-east than north, and 22 is not."""
        assert fmt.wind_direction(23.0) == "NØ"
        assert fmt.wind_direction(21.0) == "N"

    def test_it_wraps_past_north_instead_of_falling_off_the_end(self):
        assert fmt.wind_direction(359.0) == "N"
        assert fmt.wind_direction(361.0) == "N"


class TestHour:
    def test_it_is_the_local_hour_with_a_leading_zero(self):
        """07.00 UTC in September is 09.00 in Copenhagen."""
        assert fmt.hour(datetime(2026, 9, 19, 7, 0, tzinfo=timezone.utc)) == "09"

    def test_midnight_is_zero_zero_not_twenty_four(self):
        assert fmt.hour(datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc)) == "00"
