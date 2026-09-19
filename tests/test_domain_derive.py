"""Tests for the pure derivations.

The night-detection cases are the point of this file. The retired SunWidget got
day and night exactly backwards and its test still passed, because the test
asserted only that the result was a bool. Every assertion here would fail if
the logic were inverted.
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.derive import (
    house_summary,
    humidity_alert,
    indoor_rooms,
    is_night,
    ordered_rooms,
    room_alert,
    temperature_alert,
)
from domain.models import (
    Climate,
    ComfortBand,
    HumidityAlert,
    Room,
    SunTimes,
    TemperatureAlert,
)

UTC = timezone.utc


def room(key="stue", temperature=None, humidity=None, comfort=None, **kwargs):
    """Build a room with just the fields a test cares about."""
    return Room(
        key=key,
        name=kwargs.pop("name", key.title()),
        climate=Climate(temperature=temperature, humidity=humidity),
        comfort=comfort or ComfortBand(),
        **kwargs,
    )


class TestIsNight:
    """Day/night from two future timestamps - the trap documented in SunTimes."""

    def test_night_when_the_sun_will_rise_before_it_sets(self):
        # Real payload shape: at 04:00 both events are ahead, rising first.
        sun = SunTimes(
            next_rising=datetime(2025, 11, 1, 6, 23, tzinfo=UTC),
            next_setting=datetime(2025, 11, 1, 15, 37, tzinfo=UTC),
        )

        assert is_night(sun) is True

    def test_day_when_the_sun_will_set_before_it_rises(self):
        # At 14:00 the sun sets today and rises again tomorrow morning.
        sun = SunTimes(
            next_rising=datetime(2025, 11, 2, 6, 24, tzinfo=UTC),
            next_setting=datetime(2025, 11, 1, 15, 37, tzinfo=UTC),
        )

        assert is_night(sun) is False

    def test_the_retired_widget_expression_gets_both_cases_wrong(self):
        """Pin the bug itself, so a "simplification" cannot reintroduce it."""
        night = SunTimes(
            next_rising=datetime(2025, 11, 1, 6, 23, tzinfo=UTC),
            next_setting=datetime(2025, 11, 1, 15, 37, tzinfo=UTC),
        )
        day = SunTimes(
            next_rising=datetime(2025, 11, 2, 6, 24, tzinfo=UTC),
            next_setting=datetime(2025, 11, 1, 15, 37, tzinfo=UTC),
        )

        for sun in (night, day):
            old_expression = sun.next_rising > sun.next_setting
            assert is_night(sun) is not old_expression

    def test_compares_instants_not_wall_clock_across_a_dst_change(self):
        # Danish clocks go back on 2026-10-25. The setting carries the summer
        # offset and the next rising the winter one; naive comparison of the
        # wall-clock fields would still be right here, so the assertion that
        # matters is that mixed offsets are handled at all.
        sun = SunTimes(
            next_setting=datetime(2026, 10, 25, 18, 0, tzinfo=timezone(timedelta(hours=2))),
            next_rising=datetime(2026, 10, 26, 7, 0, tzinfo=timezone(timedelta(hours=1))),
        )

        assert is_night(sun) is False

    @pytest.mark.parametrize(
        "sun",
        [
            SunTimes(),
            SunTimes(next_rising=datetime(2025, 11, 1, 6, 23, tzinfo=UTC)),
            SunTimes(next_setting=datetime(2025, 11, 1, 15, 37, tzinfo=UTC)),
        ],
    )
    def test_none_when_either_timestamp_is_missing(self, sun):
        assert is_night(sun) is None


class TestTemperatureAlert:
    """Red means act, so an unjudged room must never be classified OK."""

    def test_below_the_band_is_too_cold(self):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0)
        assert temperature_alert(room(temperature=17.5, comfort=band)) is TemperatureAlert.TOO_COLD

    def test_above_the_band_is_too_hot(self):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0)
        assert temperature_alert(room(temperature=25.1, comfort=band)) is TemperatureAlert.TOO_HOT

    def test_inside_the_band_is_ok(self):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0)
        assert temperature_alert(room(temperature=21.0, comfort=band)) is TemperatureAlert.OK

    @pytest.mark.parametrize("value", [19.0, 24.0])
    def test_exactly_on_a_bound_is_ok(self, value):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0)
        assert temperature_alert(room(temperature=value, comfort=band)) is TemperatureAlert.OK

    def test_a_single_bound_only_checks_that_end(self):
        cold_only = ComfortBand(min_temperature=19.0)
        assert temperature_alert(room(temperature=30.0, comfort=cold_only)) is TemperatureAlert.OK
        assert (
            temperature_alert(room(temperature=5.0, comfort=cold_only)) is TemperatureAlert.TOO_COLD
        )

    def test_missing_reading_is_unknown(self):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0)
        assert temperature_alert(room(temperature=None, comfort=band)) is TemperatureAlert.UNKNOWN

    def test_missing_band_is_unknown_not_ok(self):
        assert temperature_alert(room(temperature=35.0)) is TemperatureAlert.UNKNOWN


class TestHumidityAlert:
    def test_above_the_ceiling_is_too_humid(self):
        band = ComfortBand(max_humidity=65.0)
        assert humidity_alert(room(humidity=68.0, comfort=band)) is HumidityAlert.TOO_HUMID

    def test_exactly_at_the_ceiling_is_ok(self):
        band = ComfortBand(max_humidity=65.0)
        assert humidity_alert(room(humidity=65.0, comfort=band)) is HumidityAlert.OK

    def test_missing_ceiling_is_unknown(self):
        assert humidity_alert(room(humidity=90.0)) is HumidityAlert.UNKNOWN

    def test_missing_reading_is_unknown(self):
        band = ComfortBand(max_humidity=65.0)
        assert humidity_alert(room(humidity=None, comfort=band)) is HumidityAlert.UNKNOWN


class TestRoomAlert:
    def test_reports_both_axes(self):
        band = ComfortBand(min_temperature=19.0, max_temperature=24.0, max_humidity=60.0)
        alert = room_alert(room(temperature=26.0, humidity=70.0, comfort=band))

        assert alert.temperature is TemperatureAlert.TOO_HOT
        assert alert.humidity is HumidityAlert.TOO_HUMID
        assert alert.is_alerting is True

    def test_unknown_does_not_count_as_alerting(self):
        alert = room_alert(room(temperature=None, humidity=None))

        assert alert.is_alerting is False

    def test_either_axis_alone_is_enough_to_alert(self):
        humid = ComfortBand(max_humidity=60.0)
        alert = room_alert(room(temperature=None, humidity=70.0, comfort=humid))

        assert alert.temperature is TemperatureAlert.UNKNOWN
        assert alert.is_alerting is True


class TestRoomOrdering:
    def test_outdoor_sorts_last_regardless_of_its_order_value(self):
        rooms = (
            room(key="ude", order=0, is_outdoor=True),
            room(key="stue", order=5),
            room(key="garage", order=9),
        )

        assert [r.key for r in ordered_rooms(rooms)] == ["stue", "garage", "ude"]

    def test_indoor_rooms_excludes_the_outdoors(self):
        rooms = (room(key="stue"), room(key="ude", is_outdoor=True))

        assert [r.key for r in indoor_rooms(rooms)] == ["stue"]


class TestHouseSummary:
    def test_counts_and_averages_indoor_rooms_only(self):
        rooms = (
            room(key="stue", temperature=22.0, humidity=44.0),
            room(key="koekken", temperature=20.0, humidity=48.0),
            room(key="ude", temperature=4.0, humidity=90.0, is_outdoor=True),
        )

        summary = house_summary(rooms)

        assert summary.room_count == 2
        assert summary.reporting_count == 2
        assert summary.temperature_mean == 21.0
        assert summary.temperature_min == 20.0
        assert summary.temperature_max == 22.0
        assert summary.temperature_spread == 2.0
        assert summary.humidity_mean == 46.0

    def test_a_dead_sensor_lowers_reporting_count_but_not_room_count(self):
        rooms = (
            room(key="stue", temperature=22.0),
            room(key="garage", temperature=None),
        )

        summary = house_summary(rooms)

        assert summary.room_count == 2
        assert summary.reporting_count == 1
        assert summary.temperature_mean == 22.0

    def test_a_fully_dead_house_summarises_as_none_not_zero(self):
        rooms = (room(key="stue"), room(key="garage"))

        summary = house_summary(rooms)

        assert summary.room_count == 2
        assert summary.reporting_count == 0
        assert summary.temperature_mean is None
        assert summary.temperature_spread is None
        assert summary.humidity_median is None

    def test_no_rooms_at_all_is_harmless(self):
        summary = house_summary(())

        assert summary.room_count == 0
        assert summary.temperature_mean is None

    def test_humidity_median_is_the_middle_reading(self):
        rooms = (
            room(key="a", humidity=40.0),
            room(key="b", humidity=44.0),
            room(key="c", humidity=90.0),
        )

        assert house_summary(rooms).humidity_median == 44.0
