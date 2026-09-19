"""Tests for the capture tool's pure half.

The tool itself can only be run against the live Home Assistant instance, from
outside the container, by a person. That is exactly why the parts that decide
*what to keep* and *what to report* are pure functions with no network in them:
a crash discovered on the wire costs a round trip to a house, and this suite is
the only thing standing in for that.
"""

import json

import pytest

from capture_snapshot import build_report, is_interesting, read_env, select_states
from config.loader import parse_house

CONFIG = parse_house(
    {
        "weather": {"entity_id": "weather.home"},
        "sun": {"entity_id": "sun.sun"},
        "rooms": [
            {
                "key": "stue",
                "name": "Stue",
                "climate": "climate.stue",
                "humidity": "sensor.stue_humidity",
            },
            {"key": "gang", "name": "Gang", "climate": "climate.gang"},
        ],
    }
)


def state(entity_id, value="21.0", **attributes):
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


STATES = {
    "climate.stue": state("climate.stue", "heat"),
    "climate.gang": state("climate.gang", "heat"),
    "sensor.stue_humidity": state("sensor.stue_humidity", "44", device_class="humidity"),
    "sensor.loose_humidity": state(
        "sensor.loose_humidity", "51", device_class="humidity", friendly_name="Lille bad fugt"
    ),
    "sensor.outdoor_temp": state(
        "sensor.outdoor_temp", "9.2", device_class="temperature", friendly_name="Ude"
    ),
    "sensor.phone_battery": state("sensor.phone_battery", "88", device_class="battery"),
    "weather.home": state("weather.home", "cloudy", temperature=17.0, humidity=71),
    "sun.sun": state("sun.sun", "above_horizon"),
}

HOURLY = [{"datetime": "2026-09-19T15:00:00+00:00", "temperature": 17.2, "precipitation": 0.4}]
DAILY = [{"datetime": "2026-09-19T00:00:00+00:00", "temperature": 18.0, "templow": 9.0}]


class TestWhatGetsRecorded:
    def test_climate_entities_are_kept(self):
        assert is_interesting("climate.stue", STATES["climate.stue"])
        assert is_interesting("weather.home", STATES["weather.home"])
        assert is_interesting("sun.sun", STATES["sun.sun"])

    @pytest.mark.parametrize(
        "entity_id", ["sensor.stue_humidity", "sensor.loose_humidity", "sensor.outdoor_temp"]
    )
    def test_climate_sensors_are_kept_even_when_unconfigured(self, entity_id):
        # An unconfigured humidity sensor is the answer to the duplicate-sensor
        # question, so it has to survive the filter.
        assert is_interesting(entity_id, STATES[entity_id])

    def test_the_rest_of_the_household_is_not_recorded(self):
        # These fixtures get committed. A climate dashboard has no business
        # keeping a copy of everyone's phone.
        assert not is_interesting("sensor.phone_battery", STATES["sensor.phone_battery"])

        kept = select_states(STATES, set(CONFIG.entity_ids))

        assert "sensor.phone_battery" not in kept
        assert "sensor.loose_humidity" in kept

    def test_a_configured_entity_is_kept_whatever_it_is(self):
        states = {"light.stue": state("light.stue", "on")}
        config = parse_house(
            {
                "weather": {"entity_id": "weather.home"},
                "sun": {"entity_id": "sun.sun"},
                "rooms": [
                    {
                        "key": "stue",
                        "name": "Stue",
                        "climate": "climate.stue",
                        "devices": [
                            {
                                "key": "lamp",
                                "name": "Lampe",
                                "kind": "light",
                                "entity_id": "light.stue",
                            }
                        ],
                    }
                ],
            }
        )

        assert "light.stue" in select_states(states, set(config.entity_ids))

    def test_selection_is_sorted_so_the_fixture_diffs_cleanly(self):
        assert list(select_states(STATES, set(CONFIG.entity_ids))) == sorted(
            select_states(STATES, set(CONFIG.entity_ids))
        )


class TestTheReport:
    def report(self, states=None, hourly=None, daily=None):
        return build_report(
            CONFIG,
            STATES if states is None else states,
            HOURLY if hourly is None else hourly,
            DAILY if daily is None else daily,
            "2026-09-19T12:00:00+00:00",
        )

    def test_a_missing_configured_entity_is_called_out(self):
        states = {k: v for k, v in STATES.items() if k != "climate.gang"}

        report = self.report(states=states)

        assert "**MISSING**" in report
        assert "1 of 5 configured entities are missing" in report

    def test_nothing_missing_says_so_plainly(self):
        assert "0 of 5 configured entities are missing" in self.report()

    def test_every_humidity_sensor_is_listed_for_the_duplicate_question(self):
        report = self.report()

        assert "sensor.loose_humidity" in report
        assert "Lille bad fugt" in report

    def test_unused_temperature_sensors_are_offered_for_the_outdoor_row(self):
        report = self.report()
        section = report.split("## Temperature sensors the configuration does not use")[1]

        assert "sensor.outdoor_temp" in section
        assert "sensor.stue_humidity" not in section

    def test_absent_weather_attributes_are_marked_no(self):
        report = self.report()
        section = report.split("## Weather depth")[1]

        assert "| `temperature` | yes | 17.0 |" in section
        assert "| `apparent_temperature` | **no** |" in section
        assert "| `pressure` | **no** |" in section

    def test_forecast_keys_and_the_first_entry_are_recorded(self):
        report = self.report()

        assert "`templow`" in report
        assert json.dumps(HOURLY[0], indent=2, ensure_ascii=False) in report

    def test_an_empty_forecast_is_reported_rather_than_skipped(self):
        report = self.report(daily=[])

        assert "Returned nothing" in report

    def test_a_missing_weather_entity_does_not_crash_the_report(self):
        states = {k: v for k, v in STATES.items() if k != "weather.home"}

        assert "The configured weather entity does not exist." in self.report(states=states)


class TestEnvFile:
    def test_reads_keys_and_ignores_comments_and_quotes(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text(
            "# a comment\n\nHASS_URL='http://hass.local:8123'\nHASS_TOKEN=abc123\nrubbish\n",
            encoding="utf-8",
        )

        assert read_env(path) == {"HASS_URL": "http://hass.local:8123", "HASS_TOKEN": "abc123"}

    def test_a_missing_env_file_is_empty_not_an_error(self, tmp_path):
        assert read_env(tmp_path / "nope") == {}


class TestTheEntityTable:
    """The table is the thing a person acts on, so it names the room, not just the id."""

    def test_each_row_names_its_room_and_role(self):
        report = TestTheReport().report()

        assert "| Stue | humidity | `sensor.stue_humidity` | 44 |" in report
        assert "| - | weather | `weather.home` | cloudy |" in report

    def test_a_missing_entity_is_reported_by_room(self):
        states = {k: v for k, v in STATES.items() if k != "climate.gang"}

        report = build_report(CONFIG, states, HOURLY, DAILY, "2026-09-19T12:00:00+00:00")

        assert "- Gang / climate: `climate.gang`" in report

    def test_an_attribute_reference_shows_the_attribute_not_the_state(self):
        config = parse_house(
            {
                "weather": {"entity_id": "weather.home"},
                "sun": {"entity_id": "sun.sun"},
                "rooms": [
                    {
                        "key": "ude",
                        "name": "Ude",
                        "is_outdoor": True,
                        "temperature": {"entity_id": "weather.home", "attribute": "temperature"},
                    }
                ],
            }
        )

        report = build_report(config, STATES, HOURLY, DAILY, "2026-09-19T12:00:00+00:00")

        # weather.home's state is "cloudy"; its temperature attribute is 17.0.
        assert "| Ude | temperature | `weather.home[temperature]` | 17.0 |" in report

    def test_one_forecast_entry_is_not_reported_as_one_entries(self):
        assert "1 entry." in TestTheReport().report()
        assert "1 entries" not in TestTheReport().report()
