"""The REST adapter, driven through a fake opener.

Nothing here opens a socket. The adapter takes its opener by injection for
exactly this reason: the failure modes worth testing - a 500, a timeout, a
proxy returning HTML, a forecast API that moved again - are precisely the ones
you cannot arrange against a live instance on demand.
"""

from __future__ import annotations

import json
import socket
import urllib.error
from datetime import datetime, timezone

import pytest

from config.house import EntityRef, HouseConfig, RoomConfig
from sources.homeassistant import HomeAssistantSource, _forecast_list
from sources.port import SnapshotSource, SourceUnavailable

WEATHER = EntityRef(entity_id="weather.home")
SUN = EntityRef(entity_id="sun.sun")

CONFIG = HouseConfig(
    weather=WEATHER,
    sun=SUN,
    rooms=(RoomConfig(key="stue", name="Stue", climate=EntityRef(entity_id="climate.stue")),),
)

STATES = [
    {
        "entity_id": "climate.stue",
        "state": "heat",
        "attributes": {"current_temperature": 23.1, "current_humidity": 44.0},
    },
    {
        "entity_id": "weather.home",
        "state": "rainy",
        "attributes": {"temperature": 17.0, "humidity": 81},
    },
    {
        "entity_id": "sun.sun",
        "state": "above_horizon",
        "attributes": {
            "next_rising": "2026-09-20T05:20:31+00:00",
            "next_setting": "2026-09-19T17:11:09+00:00",
        },
    },
]

HOURLY = [{"datetime": "2026-09-19T11:00:00+00:00", "temperature": 17.0, "precipitation": 0.8}]
DAILY = [{"datetime": "2026-09-19T00:00:00+00:00", "temperature": 18.0, "templow": 9.0}]


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Answers by path, and records what it was asked for."""

    def __init__(self, states=None, hourly=None, daily=None, fail=None):
        self.states = STATES if states is None else states
        self.hourly = HOURLY if hourly is None else hourly
        self.daily = DAILY if daily is None else daily
        self.fail = fail or {}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, request, timeout=None):
        path = request.full_url.split("8123", 1)[-1]
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.calls.append((request.method, path, body))

        key = "states" if "/api/states" in path else (body or {}).get("type", "forecast")
        if key in self.fail:
            raise self.fail[key]

        if key == "states":
            return FakeResponse(json.dumps(self.states).encode("utf-8"))

        forecast = self.hourly if key == "hourly" else self.daily
        payload = {"service_response": {"weather.home": {"forecast": forecast}}}
        return FakeResponse(json.dumps(payload).encode("utf-8"))


def source(**kwargs) -> tuple[HomeAssistantSource, FakeOpener]:
    opener = FakeOpener(**kwargs)
    return (
        HomeAssistantSource(CONFIG, "http://homeassistant.local:8123", "token", opener=opener),
        opener,
    )


class TestPortConformance:
    def test_it_is_a_snapshot_source(self):
        adapter, _ = source()
        assert isinstance(adapter, SnapshotSource)

    def test_it_names_itself_for_the_log(self):
        adapter, _ = source()
        assert adapter.name == "hass:http://homeassistant.local:8123"

    def test_it_strips_a_trailing_slash_from_the_base_url(self):
        adapter = HomeAssistantSource(CONFIG, "http://ha.local:8123/", "token")
        assert adapter.base_url == "http://ha.local:8123"


class TestHappyPath:
    def test_it_builds_a_snapshot(self):
        adapter, _ = source()
        snapshot = adapter.fetch()

        assert snapshot.rooms[0].climate.temperature == 23.1
        assert snapshot.weather.condition == "rainy"
        assert snapshot.hourly[0].temperature == 17.0
        assert snapshot.daily[0].temperature_high == 18.0
        assert snapshot.sun.next_rising is not None
        assert snapshot.source_errors == ()

    def test_it_stamps_the_snapshot(self):
        adapter, _ = source()
        before = datetime.now(timezone.utc)
        assert adapter.fetch().taken_at >= before

    def test_it_makes_exactly_three_calls(self):
        """One states call, two forecasts. Eleven rooms are not two dozen trips."""
        adapter, opener = source()
        adapter.fetch()
        assert len(opener.calls) == 3

    def test_it_reads_every_state_in_one_call(self):
        """One snapshot means one instant, not readings smeared across a minute."""
        adapter, opener = source()
        adapter.fetch()

        methods_and_paths = [(method, path) for method, path, _ in opener.calls]
        assert ("GET", "/api/states") in methods_and_paths

    def test_it_asks_the_forecast_service_for_both_kinds(self):
        adapter, opener = source()
        adapter.fetch()

        kinds = [body["type"] for method, _, body in opener.calls if body]
        assert sorted(kinds) == ["daily", "hourly"]

    def test_it_asks_about_the_configured_weather_entity(self):
        adapter, opener = source()
        adapter.fetch()

        entities = {body["entity_id"] for _, _, body in opener.calls if body}
        assert entities == {"weather.home"}

    def test_it_sends_the_token_as_a_bearer_header(self):
        captured = []

        class CapturingOpener(FakeOpener):
            def __call__(self, request, timeout=None):
                captured.append(dict(request.headers))
                return super().__call__(request, timeout=timeout)

        adapter = HomeAssistantSource(
            CONFIG, "http://ha.local:8123", "s3cret", opener=CapturingOpener()
        )
        adapter.fetch()

        # urllib title-cases the header names it is handed.
        assert all(headers["Authorization"] == "Bearer s3cret" for headers in captured)
        assert len(captured) == 3

    def test_it_passes_its_timeout_to_the_opener(self):
        """A hung request must not stall the refresh loop forever."""
        seen = []

        class TimingOpener(FakeOpener):
            def __call__(self, request, timeout=None):
                seen.append(timeout)
                return super().__call__(request, timeout=timeout)

        adapter = HomeAssistantSource(
            CONFIG, "http://ha.local:8123", "t", timeout=5.0, opener=TimingOpener()
        )
        adapter.fetch()

        assert seen == [5.0, 5.0, 5.0]

    def test_it_indexes_states_by_entity_id(self):
        """/api/states returns a list; the mapping layer wants it keyed."""
        adapter, _ = source()
        assert adapter._states()["weather.home"]["state"] == "rainy"


class TestWholeSourceFailure:
    """If nothing can be read, the caller keeps the last good frame."""

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.URLError("connection refused"),
            socket.timeout("timed out"),
            OSError("network unreachable"),
        ],
    )
    def test_an_unreachable_instance_raises(self, error):
        adapter, _ = source(fail={"states": error})
        with pytest.raises(SourceUnavailable):
            adapter.fetch()

    def test_an_expired_token_raises(self):
        error = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        adapter, _ = source(fail={"states": error})

        with pytest.raises(SourceUnavailable, match="401"):
            adapter.fetch()

    def test_a_states_response_that_is_not_a_list_raises(self):
        adapter, _ = source(states={"not": "a list"})
        with pytest.raises(SourceUnavailable, match="list of entities"):
            adapter.fetch()

    def test_a_response_that_is_not_json_raises(self):
        """A captive portal or a proxy returning an HTML error page."""

        class HtmlOpener(FakeOpener):
            def __call__(self, request, timeout=None):
                return FakeResponse(b"<html>504 Gateway Timeout</html>")

        adapter = HomeAssistantSource(CONFIG, "http://ha.local:8123", "t", opener=HtmlOpener())
        with pytest.raises(SourceUnavailable, match="did not return JSON"):
            adapter.fetch()

    def test_it_never_raises_a_bare_urlerror_upward(self):
        """The caller handles one exception type, not urllib's whole vocabulary."""
        adapter, _ = source(fail={"states": urllib.error.URLError("boom")})

        with pytest.raises(SourceUnavailable):
            adapter.fetch()


class TestForecastFailureIsNotSourceFailure:
    """The rooms are still worth showing when the weather strip is not."""

    def test_a_failed_hourly_forecast_is_reported_not_raised(self):
        error = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
        adapter, _ = source(fail={"hourly": error})

        snapshot = adapter.fetch()

        assert snapshot.hourly == ()
        assert snapshot.rooms[0].climate.temperature == 23.1
        assert any("hourly forecast" in error for error in snapshot.source_errors)

    def test_both_forecasts_failing_still_renders_the_house(self):
        error = urllib.error.URLError("no route")
        adapter, _ = source(fail={"hourly": error, "daily": error})

        snapshot = adapter.fetch()

        assert (snapshot.hourly, snapshot.daily) == ((), ())
        assert snapshot.weather.condition == "rainy"
        assert len(snapshot.source_errors) == 2

    def test_an_unrecognised_forecast_shape_is_reported(self):
        class OddOpener(FakeOpener):
            def __call__(self, request, timeout=None):
                if request.data:
                    return FakeResponse(b'{"unexpected": true}')
                return FakeResponse(json.dumps(STATES).encode("utf-8"))

        adapter = HomeAssistantSource(CONFIG, "http://ha.local:8123", "t", opener=OddOpener())
        snapshot = adapter.fetch()

        assert snapshot.hourly == ()
        assert any("unrecognised" in error for error in snapshot.source_errors)

    def test_an_empty_forecast_is_not_an_error(self):
        """A provider with nothing to forecast is answering, not failing."""
        adapter, _ = source(hourly=[], daily=[])
        snapshot = adapter.fetch()

        assert snapshot.hourly == ()
        assert snapshot.source_errors == ()


class TestForecastShapes:
    """The forecast API has already moved once, so the shape is dug for."""

    def test_the_current_nested_shape(self):
        payload = {"service_response": {"weather.home": {"forecast": DAILY}}}
        assert _forecast_list(payload, "weather.home") == DAILY

    def test_the_shape_without_the_service_response_wrapper(self):
        assert _forecast_list({"weather.home": {"forecast": DAILY}}, "weather.home") == DAILY

    def test_the_older_single_entity_shape(self):
        assert _forecast_list({"forecast": DAILY}, "weather.home") == DAILY

    def test_a_bare_list(self):
        assert _forecast_list(DAILY, "weather.home") == DAILY

    def test_an_empty_forecast_is_a_list_not_a_failure(self):
        """Distinct from None: the provider answered, and the answer was nothing."""
        assert (
            _forecast_list({"service_response": {"weather.home": {"forecast": []}}}, "weather.home")
            == []
        )

    @pytest.mark.parametrize(
        "payload",
        [None, "nothing", 7, {}, {"service_response": {}}, {"forecast": "soon"}],
    )
    def test_nothing_list_shaped_is_none(self, payload):
        assert _forecast_list(payload, "weather.home") is None

    def test_it_does_not_confuse_another_entitys_forecast(self):
        payload = {"service_response": {"weather.elsewhere": {"forecast": DAILY}}}
        assert _forecast_list(payload, "weather.home") is None


class TestPerEntityFailure:
    """A dead sensor yields None, never an exception (PLAN.md 3.3)."""

    def test_a_missing_entity_leaves_a_placeholder_and_a_note(self):
        adapter, _ = source(states=[STATES[1], STATES[2]])
        snapshot = adapter.fetch()

        assert snapshot.rooms[0].climate.temperature is None
        assert any("climate.stue" in error for error in snapshot.source_errors)

    def test_an_unavailable_entity_leaves_a_placeholder(self):
        states = [{"entity_id": "climate.stue", "state": "unavailable", "attributes": {}}]
        adapter, _ = source(states=states)

        assert adapter.fetch().rooms[0].climate.temperature is None

    def test_entries_that_are_not_entities_are_skipped(self):
        adapter, _ = source(states=["a string", {"no": "entity_id"}, STATES[0]])
        assert adapter.fetch().rooms[0].climate.temperature == 23.1
