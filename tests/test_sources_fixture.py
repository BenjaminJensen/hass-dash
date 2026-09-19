"""The fixture source, and the promise that hostile input cannot break a render.

The central test here is `TestHostileSet`: the whole unpleasant recording must
produce a `Snapshot` with every reading `None` and zero tracebacks. That is the
M3 exit condition, and it is the difference between a dashboard that degrades
and one that goes dark at 03:00 when a Zigbee stick reboots.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.loader import load_house
from domain.derive import house_summary, is_night, room_alert
from domain.models import HeatingAction, Snapshot
from sources.fixture import FixtureSource
from sources.port import SnapshotSource, SourceUnavailable

FIXTURES = Path(__file__).parent / "fixtures"
SETS = FIXTURES / "sets"
HOUSE = Path(__file__).parent.parent / "house.yml"

FROZEN = datetime(2026, 9, 19, 12, 30, tzinfo=timezone.utc)


@pytest.fixture
def config():
    return load_house(HOUSE)


def source(config, directory: Path) -> FixtureSource:
    return FixtureSource(config, directory, clock=lambda: FROZEN)


class TestPortConformance:
    def test_a_fixture_source_is_a_snapshot_source(self, config):
        assert isinstance(source(config, SETS / "nominal"), SnapshotSource)

    def test_it_names_itself_for_the_log(self, config):
        assert source(config, SETS / "nominal").name == "fixture:nominal"

    def test_it_stamps_the_snapshot_from_its_clock(self, config):
        assert source(config, SETS / "nominal").fetch().taken_at == FROZEN


class TestNominalSet:
    """The synthetic recording. Shapes are documented; values are invented."""

    @pytest.fixture
    def snapshot(self, config) -> Snapshot:
        return source(config, SETS / "nominal").fetch()

    def test_every_configured_room_is_present_and_in_order(self, snapshot, config):
        assert tuple(r.key for r in snapshot.rooms) == tuple(r.key for r in config.rooms)

    def test_every_room_reports_a_temperature(self, snapshot):
        missing = [r.key for r in snapshot.rooms if r.climate.temperature is None]
        assert missing == []

    def test_every_room_reports_a_humidity(self, snapshot):
        missing = [r.key for r in snapshot.rooms if r.climate.humidity is None]
        assert missing == []

    def test_nothing_is_reported_as_broken(self, snapshot):
        """A clean recording against its own house.yml must produce no errors."""
        assert snapshot.source_errors == ()

    def test_the_outdoor_row_reads_the_weather_provider(self, snapshot):
        ude = snapshot.rooms[-1]
        assert ude.is_outdoor is True
        assert ude.climate.temperature == snapshot.weather.temperature

    def test_it_carries_weather_with_the_depth_section_3_asks_for(self, snapshot):
        weather = snapshot.weather
        assert weather.condition == "rainy"
        assert weather.temperature == 17.0
        assert weather.apparent_temperature == 15.0
        assert weather.temperature_high == 18.0
        assert weather.temperature_low == 9.0
        assert weather.pressure == 1006.4
        assert weather.wind_speed == 6.7

    def test_it_carries_a_full_days_curve_and_a_weeks_strip(self, snapshot):
        assert len(snapshot.hourly) == 24
        assert len(snapshot.daily) == 7

    def test_the_sun_is_readable_and_it_is_daytime(self, snapshot):
        """The recording is a Saturday lunchtime, so the sun sets before it rises."""
        assert snapshot.sun.next_rising is not None
        assert snapshot.sun.next_setting is not None
        assert is_night(snapshot.sun) is False

    def test_the_domain_derivations_run_on_it(self, snapshot):
        """The point of a source is that the layers above it work unchanged."""
        summary = house_summary(snapshot.rooms)
        assert summary.room_count == 10
        assert summary.reporting_count == 10
        assert summary.temperature_mean is not None

    def test_it_produces_the_alerts_the_bands_imply(self, snapshot):
        """Marius at 16.2 is below its 17.0 floor; the summary is not a guess."""
        alerts = {r.key: room_alert(r) for r in snapshot.rooms}
        assert alerts["marius"].is_alerting is True
        assert alerts["stue"].is_alerting is False

    def test_heating_action_survives_the_trip(self, snapshot):
        by_key = {r.key: r.climate.action for r in snapshot.rooms}
        assert by_key["stue"] is HeatingAction.HEATING
        assert by_key["kokken"] is HeatingAction.IDLE
        assert by_key["garage"] is HeatingAction.OFF


class TestHostileSet:
    """M3's exit condition: nothing but `None`s, and zero tracebacks."""

    @pytest.fixture
    def snapshot(self, config) -> Snapshot:
        return source(config, SETS / "hostile").fetch()

    def test_it_returns_a_snapshot_at_all(self, snapshot):
        assert isinstance(snapshot, Snapshot)

    def test_every_room_is_still_on_the_screen(self, snapshot, config):
        """A broken sensor loses a number, never a row."""
        assert tuple(r.key for r in snapshot.rooms) == tuple(r.key for r in config.rooms)

    def test_junk_in_one_room_does_not_poison_a_good_one(self, snapshot):
        """The two readable temperatures in the set must survive intact.

        `stue` arrives as the string `"21.5"` and `sophie` as a plain float.
        Nine other entities are broken around them in nine different ways, and
        a partial outage is far more likely than a total one - so this is the
        case that matters, not a set where everything is dark.
        """
        readings = {r.key: r.climate.temperature for r in snapshot.rooms}

        assert readings["stue"] == 21.5
        assert readings["sophie"] == 21.3

    def test_no_other_room_invents_a_temperature(self, snapshot):
        """Every remaining temperature is junk, in a different way each time."""
        readable = {"stue", "sophie"}
        readings = {r.key: r.climate.temperature for r in snapshot.rooms}
        assert [k for k, v in readings.items() if k not in readable and v is not None] == []

    def test_no_room_reports_a_humidity_it_cannot_justify(self, snapshot):
        """`"44,0"` is a decimal comma and a real reading; the rest is junk."""
        readings = {r.key: r.climate.humidity for r in snapshot.rooms}
        assert readings["stue"] == 44.0
        assert [key for key, value in readings.items() if key != "stue" and value is not None] == []

    def test_the_weather_is_empty_rather_than_wrong(self, snapshot):
        weather = snapshot.weather
        assert weather.condition is None
        assert weather.temperature is None
        assert weather.humidity is None

    def test_an_empty_hourly_forecast_is_an_empty_curve(self, snapshot):
        assert snapshot.hourly == ()

    def test_a_daily_forecast_of_junk_keeps_only_what_parses(self, snapshot):
        """Two of the three entries are mappings; neither has a usable value."""
        assert len(snapshot.daily) == 2
        assert all(point.temperature_high is None for point in snapshot.daily)

    def test_unreadable_sun_timestamps_leave_night_undecided(self, snapshot):
        """None is the honest answer, and is why is_night returns three values."""
        assert is_night(snapshot.sun) is None

    def test_it_says_what_went_wrong(self, snapshot):
        assert len(snapshot.source_errors) > 0

    def test_it_names_the_absent_entity(self, snapshot):
        """lille_bad's climate entity is not in the recording at all."""
        assert any("_7 does not exist" in error for error in snapshot.source_errors)

    def test_it_reports_the_shape_changes_but_not_the_quiet_sensors(self, snapshot):
        """`"kold"` is worth a line. `unavailable` is an ordinary Tuesday."""
        errors = "\n".join(snapshot.source_errors)
        assert "'kold'" in errors
        assert "unavailable" not in errors

    def test_the_domain_derivations_still_run_on_it(self, snapshot):
        """The whole house dark must not crash the summary the header shows."""
        summary = house_summary(snapshot.rooms)
        assert summary.room_count == 10
        assert summary.reporting_count == 2
        assert summary.temperature_mean == 21.4

    def test_a_room_with_no_reading_is_never_drawn_in_red(self, snapshot):
        """Silence must not be drawn in red. Red means act (INTENT.md section 2).

        The two rooms that *do* report are both inside their bands, so nothing
        in this set alerts - a screen of placeholders, not a screen of alarm.
        """
        assert [r.key for r in snapshot.rooms if room_alert(r).is_alerting] == []


class TestRecordedCapture:
    """The real recording from the live instance, once it exists.

    PLAN.md slice 2.2 has not been run yet, so this skips rather than fails.
    The moment someone runs `tools/capture_snapshot.py`, these start covering
    the actual house, and a `house.yml` that does not match it starts failing
    here instead of on the wall.
    """

    @pytest.fixture
    def snapshot(self, config) -> Snapshot:
        if not (FIXTURES / "states.json").exists():
            pytest.skip("no live capture yet - run tools/capture_snapshot.py")
        return source(config, FIXTURES).fetch()

    def test_it_replays(self, snapshot):
        assert isinstance(snapshot, Snapshot)

    def test_every_configured_entity_exists_on_the_instance(self, snapshot):
        """The UNCONFIRMED entity ids in house.yml get settled right here."""
        missing = [error for error in snapshot.source_errors if "does not exist" in error]
        assert missing == []


class TestWholeSourceFailure:
    """Distinct from a dead sensor, and the reason `SourceUnavailable` exists."""

    def test_a_missing_directory_raises(self, config, tmp_path):
        with pytest.raises(SourceUnavailable):
            source(config, tmp_path / "nowhere").fetch()

    def test_a_missing_states_file_raises(self, config, tmp_path):
        """A set with no states is a launch mistake, not a quiet instance."""
        with pytest.raises(SourceUnavailable):
            source(config, tmp_path).fetch()

    def test_the_message_says_where_it_looked(self, config, tmp_path):
        with pytest.raises(SourceUnavailable, match=str(tmp_path.name)):
            source(config, tmp_path / "nowhere").fetch()


class TestPartialSet:
    """A recording that is missing a forecast is a recording, not a failure."""

    @pytest.fixture
    def directory(self, tmp_path):
        (tmp_path / "states.json").write_text("{}", encoding="utf-8")
        return tmp_path

    def test_a_missing_forecast_file_is_reported_not_raised(self, config, directory):
        snapshot = source(config, directory).fetch()

        assert snapshot.hourly == ()
        assert any("forecast_hourly.json" in error for error in snapshot.source_errors)

    def test_invalid_json_is_reported_not_raised(self, config, directory):
        """A hand-edited set should look like a dead instance, not a crash."""
        (directory / "forecast_daily.json").write_text("{not json", encoding="utf-8")

        snapshot = source(config, directory).fetch()

        assert snapshot.daily == ()
        assert any("forecast_daily.json" in error for error in snapshot.source_errors)


class TestStatesShapes:
    """Both shapes a recording can have, because /api/states returns a list."""

    def test_it_reads_a_mapping_keyed_by_entity_id(self, config, tmp_path):
        payload = {
            "weather.home": {"entity_id": "weather.home", "state": "sunny", "attributes": {}}
        }
        (tmp_path / "states.json").write_text(json.dumps(payload), encoding="utf-8")

        assert source(config, tmp_path).fetch().weather.condition == "sunny"

    def test_it_reads_a_bare_list_as_api_states_returns_it(self, config, tmp_path):
        payload = [{"entity_id": "weather.home", "state": "sunny", "attributes": {}}]
        (tmp_path / "states.json").write_text(json.dumps(payload), encoding="utf-8")

        assert source(config, tmp_path).fetch().weather.condition == "sunny"

    def test_it_survives_a_states_file_that_is_neither(self, config, tmp_path):
        (tmp_path / "states.json").write_text('"a string"', encoding="utf-8")

        snapshot = source(config, tmp_path).fetch()
        assert snapshot.rooms and all(r.climate.temperature is None for r in snapshot.rooms)
