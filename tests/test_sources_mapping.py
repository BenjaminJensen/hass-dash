"""The coercion layer, tested against everything a generous API can hand it.

These are the tests that decide whether a dead sensor blanks the screen. Each
one asserts the *value*, not merely that nothing raised - `as_float("21.5")`
returning None would pass a "no exception" test and show a placeholder on a
working thermostat.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config.house import DeviceConfig, EntityRef, HouseConfig, RoomConfig
from domain.models import ComfortBand, HeatingAction, PowerState
from sources.mapping import (
    Problems,
    as_datetime,
    as_float,
    as_text,
    build_snapshot,
    is_absent,
)

WEATHER = EntityRef(entity_id="weather.home")
SUN = EntityRef(entity_id="sun.sun")


def house(*rooms: RoomConfig) -> HouseConfig:
    return HouseConfig(weather=WEATHER, sun=SUN, rooms=rooms)


def room(key: str = "stue", **kwargs) -> RoomConfig:
    kwargs.setdefault("name", key.title())
    kwargs.setdefault("climate", EntityRef(entity_id=f"climate.{key}"))
    return RoomConfig(key=key, **kwargs)


def state(entity_id: str, value: object = "on", **attributes) -> dict:
    return {"entity_id": entity_id, "state": value, "attributes": dict(attributes)}


class TestAsFloat:
    """A float, or None, and never an exception."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (21.5, 21.5),
            (21, 21.0),
            ("21.5", 21.5),
            ("  21.5  ", 21.5),
            ("-3.25", -3.25),
            ("1e2", 100.0),
        ],
    )
    def test_reads_numbers(self, value, expected):
        assert as_float(value) == expected

    def test_reads_a_decimal_comma(self):
        # Danish integrations do emit these, and "44,0" is a reading, not junk.
        assert as_float("44,0") == 44.0

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "   ",
            "unavailable",
            "Unavailable",
            "unknown",
            "none",
            "kold",
            "72 %",
            {"value": 22.4},
            [21.5],
            object(),
        ],
    )
    def test_refuses_everything_else(self, value):
        assert as_float(value) is None

    @pytest.mark.parametrize("value", [True, False])
    def test_refuses_booleans(self, value):
        """bool is an int in Python, so `true` would otherwise be 1.0 degrees."""
        assert as_float(value) is None


class TestAsDatetime:
    def test_reads_an_offset_timestamp(self):
        parsed = as_datetime("2026-09-20T05:20:31.000000+00:00")
        assert parsed == datetime(2026, 9, 20, 5, 20, 31, tzinfo=timezone.utc)

    def test_reads_a_z_suffix(self):
        """HA emits +00:00 today, and has emitted Z. Both are timestamps."""
        assert as_datetime("2026-09-20T05:20:31Z") == datetime(
            2026, 9, 20, 5, 20, 31, tzinfo=timezone.utc
        )

    def test_passes_a_datetime_through(self):
        moment = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        assert as_datetime(moment) is moment

    @pytest.mark.parametrize(
        "value", [None, "", "not a timestamp", "yesterday", "2026-13-45", 1758283200, []]
    )
    def test_refuses_everything_else(self, value):
        assert as_datetime(value) is None


class TestAsText:
    @pytest.mark.parametrize("value,expected", [("rainy", "rainy"), ("  rainy  ", "rainy")])
    def test_reads_strings(self, value, expected):
        assert as_text(value) == expected

    @pytest.mark.parametrize("value", [None, "", "   ", "unavailable", "unknown", 7, 21.5])
    def test_refuses_everything_else(self, value):
        assert as_text(value) is None


class TestIsAbsent:
    @pytest.mark.parametrize("value", [None, "", "unavailable", "UNKNOWN", "none", "null", "nan"])
    def test_absent(self, value):
        assert is_absent(value) is True

    @pytest.mark.parametrize("value", [0, 0.0, False, "rainy", "21.5"])
    def test_present(self, value):
        """Zero is a reading. Only the words mean absence."""
        assert is_absent(value) is False


class TestProblems:
    def test_deduplicates(self):
        """One missing climate entity is one problem, not three."""
        problems = Problems()
        ref = EntityRef(entity_id="climate.stue")
        problems.missing("stue/temperature", ref)
        problems.missing("stue/temperature", ref)
        assert len(problems.as_tuple()) == 1

    def test_keeps_order(self):
        problems = Problems()
        problems.add("first")
        problems.add("second")
        assert problems.as_tuple() == ("first", "second")

    def test_names_the_entity_and_the_role(self):
        problems = Problems()
        problems.missing("stue/humidity", EntityRef(entity_id="sensor.gone"))
        message = problems.as_tuple()[0]
        assert "stue/humidity" in message and "sensor.gone" in message


class TestRoomReadings:
    def test_reads_a_thermostat_when_no_sensor_is_configured(self):
        """Most rooms name only a climate entity; it carries temperature and setpoint."""
        config = house(room("stue"))
        states = {
            "climate.stue": state(
                "climate.stue",
                "heat",
                current_temperature=23.1,
                temperature=22.0,
                hvac_action="heating",
            )
        }

        snapshot = build_snapshot(config, states)
        climate = snapshot.rooms[0].climate

        assert climate.temperature == 23.1
        assert climate.setpoint == 22.0
        assert climate.action is HeatingAction.HEATING
        assert not [error for error in snapshot.source_errors if "climate.stue" in error]

    def test_a_dedicated_sensor_wins_over_the_thermostat(self):
        config = house(room("stue", humidity=EntityRef(entity_id="sensor.stue_rf")))
        states = {
            "climate.stue": state("climate.stue", "heat", current_humidity=99.0),
            "sensor.stue_rf": state("sensor.stue_rf", "44.0"),
        }

        assert build_snapshot(config, states).rooms[0].climate.humidity == 44.0

    def test_temperature_falls_back_to_the_thermostat_when_the_sensor_is_dead(self):
        """A quiet sensor must not hide a reading the thermostat still has."""
        config = house(room("stue", temperature=EntityRef(entity_id="sensor.stue_t")))
        states = {
            "climate.stue": state("climate.stue", "heat", current_temperature=23.1),
            "sensor.stue_t": state("sensor.stue_t", "unavailable"),
        }

        assert build_snapshot(config, states).rooms[0].climate.temperature == 23.1

    def test_humidity_never_falls_back_to_the_thermostat(self):
        """The captured instance broadcasts one house-wide humidity everywhere.

        All ten climate entities report `current_humidity: 72.0` while the
        per-room sensors read 64 to 75. A fallback would put the house average
        in a room's row and call it that room's air - the same class of bug as
        `sophie` and `gang` sharing a sensor (INTENT.md section 11). A
        placeholder is the honest answer.
        """
        config = house(room("stue", humidity=EntityRef(entity_id="sensor.stue_rf")))
        states = {
            "climate.stue": state("climate.stue", "heat", current_humidity=72.0),
            "sensor.stue_rf": state("sensor.stue_rf", "unavailable"),
        }

        assert build_snapshot(config, states).rooms[0].climate.humidity is None

    def test_a_room_naming_no_humidity_sensor_reports_none(self):
        """Not even when the thermostat is sitting there with a number."""
        config = house(room("stue"))
        states = {"climate.stue": state("climate.stue", "heat", current_humidity=72.0)}

        assert build_snapshot(config, states).rooms[0].climate.humidity is None

    def test_reads_an_attribute_reference(self):
        """The outdoor row is backed by an attribute of the weather entity."""
        config = house(
            RoomConfig(
                key="ude",
                name="Ude",
                is_outdoor=True,
                temperature=EntityRef(entity_id="weather.home", attribute="temperature"),
                comfort=ComfortBand(),
            )
        )
        states = {"weather.home": state("weather.home", "rainy", temperature=17.0)}

        assert build_snapshot(config, states).rooms[0].climate.temperature == 17.0

    def test_carries_identity_from_the_configuration(self):
        config = house(room("garage", name="Garage", icon="garage", order=9))
        built = build_snapshot(config, {}).rooms[0]

        assert (built.key, built.name, built.icon, built.order) == ("garage", "Garage", "garage", 9)

    def test_carries_the_comfort_band_from_the_configuration(self):
        """The band decides the red, so it must survive the trip through a source."""
        band = ComfortBand(min_temperature=17.0, max_temperature=22.0, max_humidity=60.0)
        config = house(room("sune", comfort=band))

        assert build_snapshot(config, {}).rooms[0].comfort == band

    def test_keeps_rooms_in_configuration_order(self):
        config = house(room("stue"), room("kokken"), room("gang"))
        keys = tuple(r.key for r in build_snapshot(config, {}).rooms)
        assert keys == ("stue", "kokken", "gang")


class TestHeatingAction:
    @pytest.mark.parametrize(
        "action,expected",
        [
            ("heating", HeatingAction.HEATING),
            ("idle", HeatingAction.IDLE),
            ("off", HeatingAction.OFF),
            ("HEATING", HeatingAction.HEATING),
        ],
    )
    def test_maps_known_actions(self, action, expected):
        config = house(room("stue"))
        states = {"climate.stue": state("climate.stue", "heat", hvac_action=action)}
        assert build_snapshot(config, states).rooms[0].climate.action is expected

    @pytest.mark.parametrize("action", ["preheating", "defrosting", 7, None])
    def test_an_unknown_action_is_unknown_not_a_guess(self, action):
        config = house(room("stue"))
        states = {"climate.stue": state("climate.stue", "heat", hvac_action=action)}
        assert build_snapshot(config, states).rooms[0].climate.action is HeatingAction.UNKNOWN

    def test_a_thermostat_that_is_off_says_so_without_hvac_action(self):
        """Many climate entities never send hvac_action. `off` is still a fact."""
        config = house(room("stue"))
        states = {"climate.stue": state("climate.stue", "off")}
        assert build_snapshot(config, states).rooms[0].climate.action is HeatingAction.OFF

    def test_an_on_thermostat_without_hvac_action_is_unknown(self):
        config = house(room("stue"))
        states = {"climate.stue": state("climate.stue", "heat")}
        assert build_snapshot(config, states).rooms[0].climate.action is HeatingAction.UNKNOWN

    def test_a_room_with_no_climate_entity_is_unknown(self):
        config = house(
            RoomConfig(key="ude", name="Ude", temperature=EntityRef(entity_id="sensor.ude"))
        )
        assert build_snapshot(config, {}).rooms[0].climate.action is HeatingAction.UNKNOWN


class TestDevices:
    """Modelled from day one, rendered by nobody yet (INTENT.md section 5)."""

    def setup_method(self):
        self.config = house(
            room(
                "stue",
                devices=(
                    DeviceConfig(
                        key="lampe",
                        name="Lampe",
                        kind="light",
                        source=EntityRef(entity_id="light.stue"),
                    ),
                ),
            )
        )

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("on", PowerState.ON),
            ("off", PowerState.OFF),
            ("ON", PowerState.ON),
            ("unavailable", PowerState.UNKNOWN),
            (None, PowerState.UNKNOWN),
            (7, PowerState.UNKNOWN),
        ],
    )
    def test_maps_power_state(self, value, expected):
        states = {"light.stue": state("light.stue", value)}
        device = build_snapshot(self.config, states).rooms[0].devices[0]
        assert device.state is expected

    def test_carries_identity(self):
        device = build_snapshot(self.config, {}).rooms[0].devices[0]
        assert (device.key, device.name, device.kind) == ("lampe", "Lampe", "light")

    def test_a_missing_device_is_reported_but_still_modelled(self):
        snapshot = build_snapshot(self.config, {})
        assert snapshot.rooms[0].devices[0].state is PowerState.UNKNOWN
        assert any("device/lampe" in error for error in snapshot.source_errors)


class TestWeather:
    def test_reads_current_conditions(self):
        config = house()
        states = {
            "weather.home": state(
                "weather.home",
                "rainy",
                temperature=17.0,
                apparent_temperature=15.0,
                humidity=81,
                pressure=1006.4,
                wind_speed=6.7,
                wind_bearing=247.0,
            )
        }

        weather = build_snapshot(config, states).weather

        assert weather.condition == "rainy"
        assert weather.temperature == 17.0
        assert weather.apparent_temperature == 15.0
        assert weather.humidity == 81.0
        assert weather.pressure == 1006.4
        assert weather.wind_speed == 6.7
        assert weather.wind_bearing == 247.0

    def test_borrows_high_and_low_from_todays_forecast(self):
        """A weather entity reports now; the day's arc is only in the forecast."""
        daily = [{"datetime": "2026-09-19T00:00:00+00:00", "temperature": 18.0, "templow": 9.0}]
        weather = build_snapshot(house(), {}, daily=daily).weather

        assert weather.temperature_high == 18.0
        assert weather.temperature_low == 9.0

    def test_high_and_low_are_none_without_a_forecast(self):
        weather = build_snapshot(house(), {}, daily=[]).weather
        assert weather.temperature_high is None and weather.temperature_low is None

    def test_a_missing_weather_entity_is_reported(self):
        snapshot = build_snapshot(house(), {})
        assert snapshot.weather.condition is None
        assert any("weather" in error for error in snapshot.source_errors)


class TestForecasts:
    def test_maps_hourly_points(self):
        hourly = [
            {
                "datetime": "2026-09-19T11:00:00+00:00",
                "temperature": 17.0,
                "precipitation": 0.8,
                "condition": "rainy",
            }
        ]
        point = build_snapshot(house(), {}, hourly=hourly).hourly[0]

        assert point.time == datetime(2026, 9, 19, 11, 0, tzinfo=timezone.utc)
        assert point.temperature == 17.0
        assert point.precipitation == 0.8
        assert point.condition == "rainy"

    def test_maps_daily_points(self):
        daily = [
            {
                "datetime": "2026-09-19T00:00:00+00:00",
                "condition": "rainy",
                "temperature": 18.0,
                "templow": 9.0,
                "precipitation": 2.4,
            }
        ]
        point = build_snapshot(house(), {}, daily=daily).daily[0]

        assert point.date == datetime(2026, 9, 19, tzinfo=timezone.utc)
        assert point.condition == "rainy"
        assert point.temperature_high == 18.0
        assert point.temperature_low == 9.0
        assert point.precipitation == 2.4

    def test_keeps_forecast_order(self):
        hourly = [{"datetime": f"2026-09-19T{hour:02d}:00:00+00:00"} for hour in range(6)]
        times = [point.time.hour for point in build_snapshot(house(), {}, hourly=hourly).hourly]
        assert times == [0, 1, 2, 3, 4, 5]

    @pytest.mark.parametrize("forecast", [None, [], "nothing", {"forecast": []}, 7])
    def test_survives_a_forecast_that_is_not_a_list(self, forecast):
        snapshot = build_snapshot(house(), {}, hourly=forecast, daily=forecast)
        assert snapshot.hourly == () and snapshot.daily == ()

    def test_drops_entries_that_are_not_mappings(self):
        daily = ["a string", {"datetime": "2026-09-19T00:00:00+00:00"}, None]
        assert len(build_snapshot(house(), {}, daily=daily).daily) == 1

    def test_an_entry_of_junk_becomes_an_entry_of_nones(self):
        daily = [{"datetime": "yesterday", "temperature": "unavailable", "templow": None}]
        point = build_snapshot(house(), {}, daily=daily).daily[0]
        assert (point.date, point.temperature_high, point.temperature_low) == (None, None, None)


class TestSun:
    def test_reads_both_transitions(self):
        states = {
            "sun.sun": state(
                "sun.sun",
                "above_horizon",
                next_rising="2026-09-20T05:20:31+00:00",
                next_setting="2026-09-19T17:11:09+00:00",
            )
        }
        sun = build_snapshot(house(), states).sun

        assert sun.next_rising == datetime(2026, 9, 20, 5, 20, 31, tzinfo=timezone.utc)
        assert sun.next_setting == datetime(2026, 9, 19, 17, 11, 9, tzinfo=timezone.utc)

    def test_junk_timestamps_become_none(self):
        states = {
            "sun.sun": state("sun.sun", "above_horizon", next_rising="soon", next_setting=None)
        }
        sun = build_snapshot(house(), states).sun
        assert sun.next_rising is None and sun.next_setting is None

    def test_a_missing_sun_entity_is_reported(self):
        snapshot = build_snapshot(house(), {})
        assert snapshot.sun.next_rising is None
        assert any("sun" in error for error in snapshot.source_errors)


class TestReportingPolicy:
    """Which failures are worth a line, and which are an ordinary Tuesday."""

    def test_a_missing_entity_is_reported(self):
        """A rename or a typo shows a placeholder forever. Say so."""
        config = house(room("stue"))
        snapshot = build_snapshot(config, {})

        assert snapshot.rooms[0].climate.temperature is None
        assert any("climate.stue" in error for error in snapshot.source_errors)

    @pytest.mark.parametrize("value", ["unavailable", "unknown", None, ""])
    def test_a_quiet_sensor_is_not_reported(self, value):
        """A Zigbee sensor that has not checked in is doing something normal."""
        config = house(room("stue", humidity=EntityRef(entity_id="sensor.stue_rf")))
        states = {
            "climate.stue": state("climate.stue", "heat"),
            "sensor.stue_rf": state("sensor.stue_rf", value),
        }

        snapshot = build_snapshot(config, states)
        assert snapshot.rooms[0].climate.humidity is None
        assert not [e for e in snapshot.source_errors if "sensor.stue_rf" in e]

    @pytest.mark.parametrize("value", ["kold", "72 %", {"value": 1}, True])
    def test_an_unparseable_value_is_reported(self, value):
        """A value that is present but not a number is a shape change."""
        config = house(room("stue", humidity=EntityRef(entity_id="sensor.stue_rf")))
        states = {
            "climate.stue": state("climate.stue", "heat"),
            "sensor.stue_rf": state("sensor.stue_rf", value),
        }

        snapshot = build_snapshot(config, states)
        assert snapshot.rooms[0].climate.humidity is None
        assert any("sensor.stue_rf" in error for error in snapshot.source_errors)

    def test_extra_errors_are_carried_through(self):
        """A source reports its own failures - a forecast call that would not load."""
        snapshot = build_snapshot(house(), {}, extra_errors=("hourly forecast: HTTP 500",))
        assert "hourly forecast: HTTP 500" in snapshot.source_errors


class TestHostileStatesPayload:
    """The whole payload being wrong, rather than one entity in it."""

    @pytest.mark.parametrize("states", [None, [], "nothing", 7])
    def test_a_states_payload_that_is_not_a_mapping_still_builds(self, states):
        config = house(room("stue"), room("kokken"))
        snapshot = build_snapshot(config, states)

        assert len(snapshot.rooms) == 2
        assert all(r.climate.temperature is None for r in snapshot.rooms)

    def test_a_state_that_is_not_a_mapping_is_treated_as_missing(self):
        config = house(room("stue"))
        snapshot = build_snapshot(config, {"climate.stue": "this used to be an entity"})

        assert snapshot.rooms[0].climate.temperature is None
        assert any("climate.stue" in error for error in snapshot.source_errors)

    def test_attributes_that_are_null_are_treated_as_empty(self):
        config = house(room("stue"))
        states = {
            "climate.stue": {"entity_id": "climate.stue", "state": "heat", "attributes": None}
        }

        snapshot = build_snapshot(config, states)
        assert snapshot.rooms[0].climate.temperature is None

    def test_taken_at_is_carried_through(self):
        moment = datetime(2026, 9, 19, 14, 32, tzinfo=timezone.utc)
        assert build_snapshot(house(), {}, taken_at=moment).taken_at == moment


class TestWindUnits:
    """The wire reports km/h; `format_da.wind_speed()` renders m/s.

    Normalising is the source layer's job - above it, a number is already in
    the domain's unit. 23 is a stiff breeze in km/h and a storm in m/s, and the
    difference decides whether someone takes a coat.
    """

    def weather(self, speed, unit):
        states = {
            "weather.home": state("weather.home", "cloudy", wind_speed=speed, wind_speed_unit=unit)
        }
        return build_snapshot(house(), states).weather

    def test_km_per_hour_becomes_metres_per_second(self):
        """The captured instance's unit: 23 km/h is 6.4 m/s, not a gale."""
        assert self.weather(23.0, "km/h").wind_speed == pytest.approx(6.389, abs=0.001)

    def test_metres_per_second_are_left_alone(self):
        assert self.weather(6.7, "m/s").wind_speed == 6.7

    @pytest.mark.parametrize(
        "speed,unit,expected",
        [(10.0, "mph", 4.4704), (10.0, "kn", 5.14444), (10.0, "ft/s", 3.048)],
    )
    def test_the_other_units_convert(self, speed, unit, expected):
        assert self.weather(speed, unit).wind_speed == pytest.approx(expected, abs=0.0001)

    def test_a_missing_unit_is_assumed_to_be_metres_per_second(self):
        """The domain's own unit is the only safe assumption when none is given."""
        assert self.weather(6.7, None).wind_speed == 6.7

    def test_an_unrecognised_unit_yields_none_rather_than_a_wrong_number(self):
        """A placeholder beats a number that might be a factor of 3.6 out."""
        assert self.weather(23.0, "furlongs/fortnight").wind_speed is None

    def test_no_wind_reading_stays_none(self):
        assert self.weather(None, "km/h").wind_speed is None
