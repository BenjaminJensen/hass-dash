"""Tests for the domain dataclasses.

Two properties matter here and both are load-bearing for the layers above:
every field is nullable, and a snapshot cannot be mutated once built.
"""

import dataclasses

import pytest

from domain.models import (
    Climate,
    ComfortBand,
    DailyPoint,
    DeviceState,
    HeatingAction,
    HourlyPoint,
    HouseSummary,
    HumidityAlert,
    PowerState,
    Room,
    RoomAlert,
    Snapshot,
    SunTimes,
    TemperatureAlert,
    Weather,
)

NULLABLE_MODELS = [Climate, ComfortBand, Weather, HourlyPoint, DailyPoint, SunTimes]


class TestNullability:
    @pytest.mark.parametrize("model", NULLABLE_MODELS)
    def test_every_field_defaults_to_none(self, model):
        instance = model()

        for f in dataclasses.fields(instance):
            if f.name == "action":  # an enum with an explicit UNKNOWN member
                continue
            assert getattr(instance, f.name) is None, f"{model.__name__}.{f.name}"

    def test_a_room_needs_only_a_key_and_a_name(self):
        room = Room(key="stue", name="Stue")

        assert room.climate == Climate()
        assert room.comfort == ComfortBand()
        assert room.devices == ()
        assert room.icon is None
        assert room.is_outdoor is False

    def test_climate_action_is_unknown_rather_than_none(self):
        assert Climate().action is HeatingAction.UNKNOWN

    def test_an_empty_snapshot_is_constructible(self):
        snapshot = Snapshot()

        assert snapshot.rooms == ()
        assert snapshot.weather == Weather()
        assert snapshot.sun == SunTimes()
        assert snapshot.source_errors == ()


class TestImmutability:
    @pytest.mark.parametrize(
        ("instance", "field_name", "value"),
        [
            (Climate(), "temperature", 21.0),
            (Room(key="stue", name="Stue"), "name", "Andet"),
            (Snapshot(), "rooms", ()),
            (Weather(), "condition", "sunny"),
        ],
    )
    def test_models_are_frozen(self, instance, field_name, value):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field_name, value)

    def test_rooms_and_devices_are_tuples_so_they_cannot_be_appended_to(self):
        snapshot = Snapshot(rooms=(Room(key="stue", name="Stue"),))

        assert isinstance(snapshot.rooms, tuple)
        assert not hasattr(snapshot.rooms, "append")


class TestValueSemantics:
    def test_equal_contents_compare_equal(self):
        assert Climate(temperature=21.0) == Climate(temperature=21.0)
        assert Room(key="stue", name="Stue") == Room(key="stue", name="Stue")

    def test_device_state_defaults_to_unknown(self):
        device = DeviceState(key="lamp", name="Lampe", kind="light")

        assert device.state is PowerState.UNKNOWN

    def test_room_alert_defaults_to_not_alerting(self):
        alert = RoomAlert()

        assert alert.temperature is TemperatureAlert.UNKNOWN
        assert alert.humidity is HumidityAlert.UNKNOWN
        assert alert.is_alerting is False

    def test_house_summary_counts_default_to_zero_and_stats_to_none(self):
        summary = HouseSummary()

        assert summary.room_count == 0
        assert summary.reporting_count == 0
        assert summary.temperature_mean is None
