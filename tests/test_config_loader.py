"""Tests for the house configuration loader.

A bad config is a developer error and must be fatal and specific. The cases
that matter are the ones that were silently tolerated before: two rooms reading
one sensor, and pixel coordinates living in configuration.
"""

import textwrap

import pytest
import yaml

from config.house import EntityRef
from config.loader import DEFAULT_HOUSE_PATH, ConfigError, load_house, parse_house

MINIMAL = """
weather:
  entity_id: weather.home
sun:
  entity_id: sun.sun
rooms:
  - key: stue
    name: Stue
    climate: climate.living_room
"""


def parse(text):
    return parse_house(yaml.safe_load(textwrap.dedent(text)), source="test.yml")


def problems(text):
    with pytest.raises(ConfigError) as caught:
        parse(text)
    return caught.value.problems


class TestAGoodConfig:
    def test_the_minimal_file_loads(self):
        config = parse(MINIMAL)

        assert config.weather == EntityRef("weather.home")
        assert config.sun == EntityRef("sun.sun")
        assert len(config.rooms) == 1
        assert config.room("stue").climate == EntityRef("climate.living_room")

    def test_order_is_position_in_the_file(self):
        config = parse(
            MINIMAL
            + """
  - key: kokken
    name: Køkken
    climate: climate.kitchen
  - key: gang
    name: Gang
    climate: climate.hall
"""
        )

        assert [(room.key, room.order) for room in config.rooms] == [
            ("stue", 0),
            ("kokken", 1),
            ("gang", 2),
        ]

    def test_an_attribute_reference_reads_part_of_an_entity(self):
        config = parse(
            MINIMAL
            + """
  - key: ude
    name: Ude
    is_outdoor: true
    temperature:
      entity_id: weather.home
      attribute: temperature
"""
        )

        ude = config.room("ude")
        assert ude.is_outdoor is True
        assert ude.temperature == EntityRef("weather.home", "temperature")
        assert str(ude.temperature) == "weather.home[temperature]"

    def test_devices_are_carried_even_though_nothing_draws_them(self):
        config = parse(
            MINIMAL
            + """
    devices:
      - key: lamp
        name: Standerlampe
        kind: light
        entity_id: light.stue_lampe
"""
        )

        (device,) = config.room("stue").devices
        assert (device.key, device.kind) == ("lamp", "light")
        assert device.source == EntityRef("light.stue_lampe")

    def test_entity_ids_are_distinct_and_include_weather_and_sun(self):
        config = parse(
            MINIMAL
            + """
    humidity: sensor.living_room_humidity
"""
        )

        # Room refs first, in field order (temperature, humidity, climate),
        # then the two house-wide entities.
        assert config.entity_ids == (
            "sensor.living_room_humidity",
            "climate.living_room",
            "weather.home",
            "sun.sun",
        )

    def test_indoor_rooms_excludes_the_outdoor_row(self):
        config = parse(
            MINIMAL
            + """
  - key: ude
    name: Ude
    is_outdoor: true
    temperature: sensor.outdoor
"""
        )

        assert [room.key for room in config.indoor_rooms] == ["stue"]

    def test_an_unknown_room_key_raises(self):
        with pytest.raises(KeyError):
            parse(MINIMAL).room("badekar")


class TestComfortBandsAreRetired:
    """Alerts are relative to the house average now, so a file that still
    states a band is stale, and says so rather than being quietly ignored."""

    def test_a_per_room_band_is_rejected(self):
        found = problems(
            MINIMAL
            + """
    comfort:
      max_humidity: 70
"""
        )

        assert any("comfort" in problem and "house average" in problem for problem in found)

    def test_a_defaults_block_is_rejected(self):
        found = problems("""
        weather: {entity_id: weather.home}
        sun: {entity_id: sun.sun}
        defaults:
          comfort: {min_temperature: 19}
        rooms:
          - key: stue
            name: Stue
            climate: climate.living_room
        """)

        assert any("defaults" in problem and "house average" in problem for problem in found)


class TestTheErrorsThatMatter:
    def test_two_rooms_may_not_read_the_same_sensor(self):
        # The bug in rooms.widget.yml: sophie and gang shared _humidity_9, so
        # one of them showed the other's air.
        found = problems(
            MINIMAL
            + """
    humidity: sensor.shared_humidity
  - key: gang
    name: Gang
    climate: climate.hall
    humidity: sensor.shared_humidity
"""
        )

        assert any('sensor.shared_humidity is already read by "stue"' in p for p in found)

    def test_a_room_may_read_one_entity_twice_itself(self):
        # An outdoor row legitimately takes two attributes off one entity.
        config = parse(
            MINIMAL
            + """
  - key: ude
    name: Ude
    temperature: {entity_id: weather.home, attribute: temperature}
    humidity: {entity_id: weather.home, attribute: humidity}
"""
        )

        assert config.room("ude").humidity == EntityRef("weather.home", "humidity")

    def test_pixel_coordinates_are_rejected_by_name(self):
        found = problems(
            MINIMAL
            + """
    position:
      x: 510
      y: 105
"""
        )

        assert any("layout is computed from a box model" in problem for problem in found)

    def test_an_order_key_is_rejected_because_file_order_is_the_order(self):
        found = problems(
            MINIMAL
            + """
    order: 3
"""
        )

        assert any("in the order they appear in this file" in problem for problem in found)

    def test_duplicate_room_keys_are_rejected(self):
        found = problems(
            MINIMAL
            + """
  - key: stue
    name: Stue igen
    climate: climate.other
"""
        )

        assert any('"stue" is already used' in problem for problem in found)

    def test_a_room_with_no_entities_at_all_is_rejected(self):
        found = problems("""
        weather: {entity_id: weather.home}
        sun: {entity_id: sun.sun}
        rooms:
          - key: tom
            name: Tom
        """)

        assert any("needs at least one of temperature, humidity or climate" in p for p in found)

    @pytest.mark.parametrize(
        "value",
        ["climate", "Climate.Living_Room", "climate.", ".living_room", "sensor stue"],
    )
    def test_a_malformed_entity_id_is_rejected(self, value):
        found = problems(f"""
        weather: {{entity_id: weather.home}}
        sun: {{entity_id: sun.sun}}
        rooms:
          - key: stue
            name: Stue
            climate: "{value}"
        """)

        assert any("entity id" in problem for problem in found)

    def test_every_problem_is_reported_at_once(self):
        # A config with four mistakes should cost one round trip, not four.
        found = problems("""
        rooms:
          - key: Stue
            climate: nonsense
        """)

        assert len(found) >= 4
        assert any("weather: required" in p for p in found)
        assert any("sun: required" in p for p in found)
        assert any("rooms[0].name" in p for p in found)
        assert any("rooms[0].key" in p for p in found)

    def test_the_message_names_the_file_and_lists_the_problems(self):
        with pytest.raises(ConfigError) as caught:
            parse("rooms: []")

        message = str(caught.value)
        assert message.startswith("test.yml is not a valid house configuration:")
        assert "\n  - " in message

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", "the file is empty"),
            ("- a\n- b", "the top level must be a mapping"),
        ],
    )
    def test_a_file_that_is_not_a_house_at_all(self, text, expected):
        assert problems(text) == (expected,)

    def test_a_missing_file_is_a_config_error_not_a_traceback(self, tmp_path):
        with pytest.raises(ConfigError) as caught:
            load_house(tmp_path / "nope.yml")

        assert caught.value.problems == ("the file does not exist",)

    def test_broken_yaml_is_a_config_error(self, tmp_path):
        path = tmp_path / "house.yml"
        path.write_text("rooms: [\n  - key: stue\n", encoding="utf-8")

        with pytest.raises(ConfigError) as caught:
            load_house(path)

        assert "not valid YAML" in caught.value.problems[0]


class TestTheShippedFile:
    """house.yml is data, and a broken data file fails exactly like broken code."""

    def test_it_loads(self):
        config = load_house(DEFAULT_HOUSE_PATH)

        assert len(config.rooms) == 11
        assert len(config.indoor_rooms) == 10
        assert config.rooms[-1].key == "ude"

    def test_exactly_one_row_is_outdoors(self):
        outdoor = [room.key for room in load_house(DEFAULT_HOUSE_PATH).rooms if room.is_outdoor]

        assert outdoor == ["ude"]
