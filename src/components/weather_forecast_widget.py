"""Weather forecast widget component."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from components.weather_icons import get_icon_for_condition
from components.widget import Widget
from core.hass_client import HASSClient
from localize import local_dt_from_utc_str
from rendering.renderer import Renderer


@dataclass
class WeatherForecastItem:
    """Normalized forecast item used for rendering."""

    time: Optional[datetime]
    temperature: Optional[float]
    condition: Optional[str]
    condition_icon: Optional[str]


class WeatherForecastWidget(Widget):
    """Self-contained widget for rendering a compact hourly forecast strip."""

    def __init__(
        self,
        hass_client: HASSClient,
        renderer: Renderer,
        device_id: str,
        forecast_type: str = "hourly",
        max_items: int = 5,
        step: int = 2,
        cache_ttl: int = 300,
        is_night: bool = False,
    ):
        super().__init__(hass_client, renderer, cache_ttl=cache_ttl)
        self.device_id = device_id
        self.forecast_type = forecast_type
        self.max_items = max_items
        self.step = step
        self.is_night = is_night
        self.items: List[WeatherForecastItem] = []

    def _empty_item(self) -> WeatherForecastItem:
        """Create an empty placeholder item for fixed-size forecast output."""
        return WeatherForecastItem(
            time=None,
            temperature=None,
            condition=None,
            condition_icon=None,
        )

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if not isinstance(value, str):
            return None

        try:
            return local_dt_from_utc_str(value)
        except Exception:
            return None

    def _normalize_item(self, raw: Any) -> Optional[WeatherForecastItem]:
        if not isinstance(raw, dict):
            return None

        condition = raw.get("condition") or raw.get("state")
        condition_str = str(condition) if condition is not None else None

        item = WeatherForecastItem(
            time=self._parse_time(raw.get("datetime") or raw.get("time") or raw.get("dt")),
            temperature=self._to_float(
                raw.get("temperature") or raw.get("temp") or raw.get("current_temperature")
            ),
            condition=condition_str,
            condition_icon=get_icon_for_condition(condition_str, is_night=self.is_night),
        )
        return item

    def _fetch_data(self) -> None:
        forecast_data = self.hass_client.get_forecast(
            device_id=self.device_id,
            forecast_type=self.forecast_type,
        )

        normalized: List[WeatherForecastItem] = []
        for raw in forecast_data or []:
            item = self._normalize_item(raw)
            if item is not None:
                normalized.append(item)

        self.items = normalized

    def get_items(self) -> List[WeatherForecastItem]:
        """Get sampled forecast items for display.

        The dashboard expects a stable 5-slot forecast strip, so we pad with
        empty placeholder items when fewer entries are available.
        """
        target_count = max(5, self.max_items)

        if self.step <= 0:
            sampled = self.items
        else:
            sampled = self.items[self.step - 1 :: self.step]

        result = sampled[:target_count]
        while len(result) < target_count:
            result.append(self._empty_item())

        return result

    def render(self) -> None:
        """Render forecast strip using legacy layout coordinates."""
        for idx, item in enumerate(self.get_items()):
            if item.condition_icon:
                self.renderer.draw_icon((50 + idx * 73, 157), item.condition_icon, 50)

            if item.temperature is None:
                temperature = "N/A"
            else:
                temperature = f"{item.temperature:.1f}°C"
            self.renderer.draw_text((45 + idx * 73, 205), temperature, style="normal", fill=0)

            time_str = item.time.strftime("%H:%M") if item.time else "n/a"
            self.renderer.draw_text((50 + idx * 73, 140), time_str, style="normal", fill=0)
