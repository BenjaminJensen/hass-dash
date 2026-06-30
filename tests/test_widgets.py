"""Tests for dashboard widgets."""
import pytest
from pathlib import Path
from unittest.mock import patch

from core.hass_mock import MockHASSClient
from rendering.renderer import PILRenderer
from components.weather_widget import WeatherWidget
from components.weather_forecast_widget import WeatherForecastWidget
from components.sun_widget import SunWidget
from components.rooms_widget import RoomsWidget
from dashboard import Dashboard


@pytest.fixture
def mock_hass():
    """Fixture: Mock HASS client with test data."""
    client = MockHASSClient()

    room_entities = {
        "climate.0x5cc7c1fffede1ef5_5": ("heat", {"current_temperature": 23.5}),
        "sensor.0x5cc7c1fffede1ef5_humidity_5": ("55", {}),
        "climate.0x5cc7c1fffede1ef5_1": ("heat", {"current_temperature": 21.8}),
        "sensor.0x5cc7c1fffede1ef5_humidity_1": ("42", {}),
        "climate.0x5cc7c1fffede1ef5_2": ("heat", {"current_temperature": 22.1}),
        "sensor.0x5cc7c1fffede1ef5_humidity_2": ("44", {}),
        "climate.0x5cc7c1fffede1ef5_6": ("heat", {"current_temperature": 24.0}),
        "sensor.0x5cc7c1fffede1ef5_humidity_6": ("38", {}),
        "climate.0x5cc7c1fffede1ef5_7": ("heat", {"current_temperature": 23.0}),
        "sensor.0x5cc7c1fffede1ef5_humidity_8": ("50", {}),
        "climate.0x5cc7c1fffede1ef5_4": ("heat", {"current_temperature": 21.0}),
        "sensor.0x5cc7c1fffede1ef5_humidity_4": ("41", {}),
        "climate.0x5cc7c1fffede1ef5_8": ("heat", {"current_temperature": 20.5}),
        "sensor.0x5cc7c1fffede1ef5_humidity_9": ("43", {}),
        "climate.0x5cc7c1fffede1ef5_3": ("heat", {"current_temperature": 21.2}),
        "sensor.0x5cc7c1fffede1ef5_humidity_3": ("40", {}),
        "climate.0x5cc7c1fffede1ef5_9": ("heat", {"current_temperature": 19.8}),
        "sensor.0x5cc7c1fffede1ef5_humidity_10": ("52", {}),
        "climate.0x5cc7c1fffede1ef5_10": ("heat", {"current_temperature": 18.0}),
    }

    for entity_id, (state, attributes) in room_entities.items():
        client.set_entity(entity_id, state, attributes)

    return client


@pytest.fixture
def pil_renderer():
    """Fixture: PIL renderer for testing."""
    return PILRenderer(size=(800, 480), output_path="test_output.bmp")


class TestWeatherWidget:
    """Tests for weather widget."""

    def test_fetch_current_weather(self, mock_hass, pil_renderer):
        """Test fetching current weather data."""
        widget = WeatherWidget(mock_hass, pil_renderer)
        widget.update()

        assert widget.current_weather is not None
        assert widget.get_temperature() == 22.5
        assert widget.get_condition() == "cloudy"
        assert widget.current_weather["condition_icon"] == "weather-cloudy"

    def test_weather_caching(self, mock_hass, pil_renderer):
        """Test weather widget caching behavior."""
        widget = WeatherWidget(mock_hass, pil_renderer, cache_ttl=300)

        assert widget.needs_update() is True
        widget.update()
        assert widget.needs_update() is False

    def test_weather_render(self, mock_hass, pil_renderer):
        """Test rendering weather widget (icon draw is mocked)."""
        widget = WeatherWidget(mock_hass, pil_renderer)
        widget.update()

        with patch.object(pil_renderer, "draw_icon") as mock_icon:
            widget.render()
            mock_icon.assert_called_once_with((80, 20), "weather-cloudy", 100)

        # Temperature text drawn at correct position with big style
        image = pil_renderer.get_image()
        assert image is not None

    def test_weather_render_missing_icon_raises(self, mock_hass, pil_renderer):
        """draw_icon raises FileNotFoundError for unknown icon names."""
        widget = WeatherWidget(mock_hass, pil_renderer)
        widget.update()
        # Force a non-existent icon
        widget.current_weather["condition_icon"] = "weather-does-not-exist"

        with pytest.raises(FileNotFoundError):
            widget.render()


class TestWeatherForecastWidget:
    """Tests for weather forecast widget."""

    def test_fetch_and_sample_forecast(self, mock_hass, pil_renderer):
        """Widget should normalize, sample, and always return five entries."""
        mock_hass.set_forecast(
            [
                {"datetime": "2025-11-01T16:00:00+00:00", "temperature": 12.0, "condition": "sunny"},
                {
                    "datetime": "2025-11-01T17:00:00+00:00",
                    "temperature": 11.5,
                    "condition": "partlycloudy",
                },
                {"datetime": "2025-11-01T18:00:00+00:00", "temperature": 11.0, "condition": "rainy"},
                {"datetime": "2025-11-01T19:00:00+00:00", "temperature": 10.5, "condition": "cloudy"},
                {"datetime": "2025-11-01T20:00:00+00:00", "temperature": 10.0, "condition": "snowy"},
                {"datetime": "2025-11-01T21:00:00+00:00", "temperature": 9.5, "condition": "windy"},
            ]
        )

        widget = WeatherForecastWidget(
            mock_hass,
            pil_renderer,
            device_id="test-device",
            step=2,
            is_night=True,
        )
        widget.update()

        sampled = widget.get_items()
        assert len(sampled) == 5
        assert sampled[0].condition == "partlycloudy"
        assert sampled[0].condition_icon == "weather-night-partly-cloudy"
        assert sampled[1].condition == "cloudy"
        assert sampled[2].condition == "windy"
        assert sampled[3].condition is None
        assert sampled[4].condition is None

    def test_render_forecast(self, mock_hass, pil_renderer):
        """Render should draw five forecast icons using legacy spacing."""
        mock_hass.set_forecast(
            [
                {"datetime": "2025-11-01T16:00:00+00:00", "temperature": 12.0, "condition": "sunny"},
                {"datetime": "2025-11-01T17:00:00+00:00", "temperature": 11.5, "condition": "cloudy"},
                {"datetime": "2025-11-01T18:00:00+00:00", "temperature": 11.0, "condition": "rainy"},
                {
                    "datetime": "2025-11-01T19:00:00+00:00",
                    "temperature": 10.5,
                    "condition": "lightning-rainy",
                },
                {"datetime": "2025-11-01T20:00:00+00:00", "temperature": 10.0, "condition": "snowy"},
                {"datetime": "2025-11-01T21:00:00+00:00", "temperature": 9.5, "condition": "windy"},
                {"datetime": "2025-11-01T22:00:00+00:00", "temperature": 9.0, "condition": "fog"},
                {
                    "datetime": "2025-11-01T23:00:00+00:00",
                    "temperature": 8.5,
                    "condition": "windy-variant",
                },
                {"datetime": "2025-11-02T00:00:00+00:00", "temperature": 8.0, "condition": "clear-night"},
                {
                    "datetime": "2025-11-02T01:00:00+00:00",
                    "temperature": 7.5,
                    "condition": "partlycloudy",
                },
            ]
        )

        widget = WeatherForecastWidget(
            mock_hass,
            pil_renderer,
            device_id="test-device",
            step=2,
        )
        widget.update()

        with patch.object(pil_renderer, "draw_icon") as mock_icon:
            widget.render()
            assert mock_icon.call_count == 5
            mock_icon.assert_any_call((50, 157), "weather-cloudy", 50)
            mock_icon.assert_any_call((123, 157), "weather-lightning-rainy", 50)
            mock_icon.assert_any_call((196, 157), "weather-windy", 50)
            mock_icon.assert_any_call((269, 157), "weather-windy-variant", 50)
            mock_icon.assert_any_call((342, 157), "weather-partly-cloudy", 50)


class TestSunWidget:
    """Tests for sun widget."""

    def test_fetch_sun_data(self, mock_hass, pil_renderer):
        """Test fetching sun/sunrise/sunset data."""
        widget = SunWidget(mock_hass, pil_renderer)
        widget.update()

        assert widget.sunrise is not None
        assert widget.sunset is not None
        assert widget.sunrise.hour == 7
        assert widget.sunset.hour == 16

    def test_sun_night_detection(self, mock_hass, pil_renderer):
        """Test night/day detection."""
        widget = SunWidget(mock_hass, pil_renderer)
        widget.update()

        # Mock data: sunrise after sunset = night
        is_night = widget.is_night_time()
        assert isinstance(is_night, bool)

    def test_sun_render(self, mock_hass, pil_renderer):
        """Test rendering sun widget."""
        widget = SunWidget(mock_hass, pil_renderer)
        widget.update()
        widget.render()

        # Should not raise exception
        assert widget.sunrise is not None


class TestDashboard:
    """Tests for dashboard orchestrator."""

    def test_dashboard_add_widgets(self, mock_hass, pil_renderer):
        """Test adding widgets to dashboard."""
        dashboard = Dashboard(pil_renderer)

        dashboard.add_widget(WeatherWidget(mock_hass, pil_renderer))
        dashboard.add_widget(SunWidget(mock_hass, pil_renderer))

        assert len(dashboard.widgets) == 2

    def test_dashboard_update_all(self, mock_hass, pil_renderer):
        """Test updating all widgets."""
        dashboard = Dashboard(pil_renderer)
        dashboard.add_widget(WeatherWidget(mock_hass, pil_renderer))
        dashboard.add_widget(SunWidget(mock_hass, pil_renderer))

        dashboard.update_all()

        # All widgets should have data after update
        for widget in dashboard.widgets:
            assert widget._data is not None or widget.current_weather is not None

    def test_dashboard_full_run(self, mock_hass, pil_renderer):
        """Test full dashboard run: update and render."""
        mock_hass.set_forecast(
            [
                {"datetime": "2025-11-01T16:00:00+00:00", "temperature": 12.0, "condition": "sunny"},
                {"datetime": "2025-11-01T17:00:00+00:00", "temperature": 11.5, "condition": "cloudy"},
                {"datetime": "2025-11-01T18:00:00+00:00", "temperature": 11.0, "condition": "rainy"},
                {
                    "datetime": "2025-11-01T19:00:00+00:00",
                    "temperature": 10.5,
                    "condition": "lightning-rainy",
                },
                {"datetime": "2025-11-01T20:00:00+00:00", "temperature": 10.0, "condition": "snowy"},
                {"datetime": "2025-11-01T21:00:00+00:00", "temperature": 9.5, "condition": "windy"},
                {"datetime": "2025-11-01T22:00:00+00:00", "temperature": 9.0, "condition": "fog"},
                {
                    "datetime": "2025-11-01T23:00:00+00:00",
                    "temperature": 8.5,
                    "condition": "windy-variant",
                },
                {"datetime": "2025-11-02T00:00:00+00:00", "temperature": 8.0, "condition": "clear-night"},
                {
                    "datetime": "2025-11-02T01:00:00+00:00",
                    "temperature": 7.5,
                    "condition": "partlycloudy",
                },
            ]
        )

        dashboard = Dashboard(pil_renderer)
        dashboard.add_widget(WeatherWidget(mock_hass, pil_renderer))
        dashboard.add_widget(WeatherForecastWidget(mock_hass, pil_renderer, device_id="test-device"))
        dashboard.add_widget(SunWidget(mock_hass, pil_renderer))
        dashboard.add_widget(RoomsWidget(mock_hass, pil_renderer))

        with patch.object(pil_renderer, "draw_icon", wraps=pil_renderer.draw_icon) as mock_icon:
            dashboard.run()

            # WeatherWidget renders one 100x100 icon, forecast renders five 50x50 icons.
            forecast_calls = [call for call in mock_icon.call_args_list if call.args[2] == 50]
            assert len(forecast_calls) == 5

        # Should complete without errors
        assert len(dashboard.widgets) == 4


class TestRoomsWidget:
    """Tests for rooms widget."""

    def test_rooms_initialization(self, mock_hass, pil_renderer):
        """Test rooms widget initialization."""
        widget = RoomsWidget(mock_hass, pil_renderer)

        assert widget is not None
        assert len(widget.get_rooms()) == 0  # No config loaded

    def test_rooms_render(self, mock_hass, pil_renderer):
        """Test rendering rooms widget (with no config)."""
        widget = RoomsWidget(mock_hass, pil_renderer)
        widget.update()
        widget.render()
        pil_renderer.render()

        # Should not raise exception
        assert isinstance(widget.rooms, list)
        assert len(widget.rooms) == 10
        assert widget.rooms[0].name == "Stort Bad"
        assert widget.rooms[0].temperature == 23.5
        assert widget.rooms[0].humidity == 55.0
        assert Path("test_output.bmp").exists()


class TestPILRenderer:
    """Tests for PIL renderer behavior."""

    def test_clear_restores_background(self, pil_renderer):
        """Clear should restore the original image baseline."""
        baseline = pil_renderer.get_image().tobytes()

        pil_renderer.draw_text((20, 20), "changed")
        assert pil_renderer.get_image().tobytes() != baseline

        pil_renderer.clear()
        assert pil_renderer.get_image().tobytes() == baseline
