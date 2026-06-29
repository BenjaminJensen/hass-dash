"""Weather widget component."""
from typing import List, Dict, Any, Optional
from components.widget import Widget
from core.hass_client import HASSClient
from rendering.renderer import Renderer


class WeatherWidget(Widget):
    """Self-contained weather widget that fetches and renders weather data."""

    def __init__(
        self,
        hass_client: HASSClient,
        renderer: Renderer,
        device_id: str = "",
        cache_ttl: int = 300
    ):
        """Initialize weather widget.
        
        Args:
            hass_client: HASS client instance
            renderer: Rendering backend
            device_id: Home Assistant weather device ID
            cache_ttl: Cache time-to-live in seconds (default: 300 = 5 min)
        """
        super().__init__(hass_client, renderer, cache_ttl=cache_ttl)
        self.device_id = device_id
        self.current_weather: Optional[Dict[str, Any]] = None
        self.forecast: List[Dict[str, Any]] = []

    def _fetch_data(self) -> None:
        """Fetch weather data from HASS."""
        # Get current weather
        weather_entity = self.hass_client.get_entity("weather.home")
        if weather_entity:
            self.current_weather = {
                "temperature": weather_entity.attributes.get("temperature"),
                "humidity": weather_entity.attributes.get("humidity"),
                "condition": weather_entity.attributes.get("condition"),
            }

        # Get forecast
        if self.device_id:
            forecast_data = self.hass_client.get_forecast(
                device_id=self.device_id,
                forecast_type="hourly"
            )
            self.forecast = forecast_data or []

    def render(self) -> None:
        """Render weather widget."""
        draw = self.renderer.get_draw()

        if not self.current_weather:
            return

        from PIL import ImageFont

        # Simple rendering for now - can be enhanced
        temp = self.current_weather.get("temperature", "N/A")
        condition = self.current_weather.get("condition", "")
        humidity = self.current_weather.get("humidity", "N/A")

        try:
            font = ImageFont.load_default()
            draw.text((10, 10), f"Weather: {temp}°C", font=font, fill=0)
            draw.text((10, 25), f"Condition: {condition}", font=font, fill=0)
            draw.text((10, 40), f"Humidity: {humidity}%", font=font, fill=0)
        except Exception as e:
            print(f"Error rendering weather widget: {e}")

    def get_temperature(self) -> Optional[float]:
        """Get current temperature."""
        if self.current_weather:
            return self.current_weather.get("temperature")
        return None

    def get_condition(self) -> Optional[str]:
        """Get current weather condition."""
        if self.current_weather:
            return self.current_weather.get("condition")
        return None
