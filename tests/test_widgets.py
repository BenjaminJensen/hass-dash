"""Tests for dashboard widgets."""
import pytest

from core.hass_mock import MockHASSClient
from rendering.renderer import PILRenderer
from components.weather_widget import WeatherWidget
from components.sun_widget import SunWidget
from components.rooms_widget import RoomsWidget
from dashboard import Dashboard


@pytest.fixture
def mock_hass():
    """Fixture: Mock HASS client with test data."""
    return MockHASSClient()


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

    def test_weather_caching(self, mock_hass, pil_renderer):
        """Test weather widget caching behavior."""
        widget = WeatherWidget(mock_hass, pil_renderer, cache_ttl=300)

        assert widget.needs_update() is True
        widget.update()
        assert widget.needs_update() is False

    def test_weather_render(self, mock_hass, pil_renderer):
        """Test rendering weather widget."""
        widget = WeatherWidget(mock_hass, pil_renderer)
        widget.update()
        widget.render()

        # Should not raise exception
        assert widget.current_weather is not None


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
        dashboard = Dashboard(pil_renderer)
        dashboard.add_widget(WeatherWidget(mock_hass, pil_renderer))
        dashboard.add_widget(SunWidget(mock_hass, pil_renderer))

        dashboard.run()

        # Should complete without errors
        assert len(dashboard.widgets) == 2


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

        # Should not raise exception
        assert isinstance(widget.rooms, list)
