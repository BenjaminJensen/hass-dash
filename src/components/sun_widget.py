"""Sun widget component."""
from typing import Optional
from datetime import datetime
from components.widget import Widget
from core.hass_client import HASSClient
from rendering.renderer import Renderer


class SunWidget(Widget):
    """Self-contained sun widget that fetches and renders sun/sunrise/sunset data."""

    def __init__(self, hass_client: HASSClient, renderer: Renderer, cache_ttl: int = 300):
        """Initialize sun widget.
        
        Args:
            hass_client: HASS client instance
            renderer: Rendering backend
            cache_ttl: Cache time-to-live in seconds (default: 300 = 5 min)
        """
        super().__init__(hass_client, renderer, cache_ttl=cache_ttl)
        self.sunrise: Optional[datetime] = None
        self.sunset: Optional[datetime] = None
        self.is_night: bool = False

    def _fetch_data(self) -> None:
        """Fetch sun data from HASS."""
        sun_entity = self.hass_client.get_entity("sun.sun")
        if not sun_entity:
            return

        attrs = sun_entity.attributes

        # Parse sunrise/sunset times
        from localize import local_dt_from_utc_str

        try:
            rising_str = attrs.get("next_rising")
            setting_str = attrs.get("next_setting")

            if rising_str:
                self.sunrise = local_dt_from_utc_str(rising_str)
            if setting_str:
                self.sunset = local_dt_from_utc_str(setting_str)

            # Simple night detection: if next rising is after next setting, it's night
            if self.sunrise and self.sunset:
                self.is_night = self.sunrise > self.sunset
        except Exception as e:
            print(f"Error parsing sun data: {e}")

    def render(self) -> None:
        """Render sun widget."""
        draw = self.renderer.get_draw()

        from PIL import ImageFont

        try:
            font = ImageFont.load_default()

            sunrise_str = self.sunrise.strftime("%H:%M") if self.sunrise else "N/A"
            sunset_str = self.sunset.strftime("%H:%M") if self.sunset else "N/A"

            draw.text((10, 70), f"Sunrise: {sunrise_str}", font=font, fill=0)
            draw.text((10, 85), f"Sunset: {sunset_str}", font=font, fill=0)
            draw.text((10, 100), f"Night: {'Yes' if self.is_night else 'No'}", font=font, fill=0)
        except Exception as e:
            print(f"Error rendering sun widget: {e}")

    def is_night_time(self) -> bool:
        """Check if it's currently night."""
        return self.is_night
