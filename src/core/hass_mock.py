"""Mock Home Assistant client for testing."""
from typing import Any, Dict, Optional
from core.hass_client import HASSClient, Entity


class MockHASSClient(HASSClient):
    """Mock Home Assistant client for testing without a real HASS instance."""

    def __init__(self):
        """Initialize with default mock data."""
        self.entities: Dict[str, Entity] = {}
        self.forecast_data: list = []
        self._setup_defaults()

    def _setup_defaults(self) -> None:
        """Set up default mock entities."""
        # Sun entity
        self.entities["sun.sun"] = Entity(
            entity_id="sun.sun",
            state="above_horizon",
            attributes={
                "next_dawn": "2025-11-01T05:43:17.360104+00:00",
                "next_dusk": "2025-11-01T16:17:40.833431+00:00",
                "next_midnight": "2025-10-31T23:00:55+00:00",
                "next_noon": "2025-11-01T11:00:55+00:00",
                "next_rising": "2025-11-01T06:23:08.606893+00:00",
                "next_setting": "2025-11-01T15:37:53.683560+00:00",
                "elevation": -26.44,
                "azimuth": 283.52,
                "rising": False,
                "friendly_name": "Sun",
            }
        )

        # Weather entity
        self.entities["weather.home"] = Entity(
            entity_id="weather.home",
            state="cloudy",
            attributes={
                "temperature": 22.5,
                "humidity": 60,
                "condition": "cloudy",
                "friendly_name": "Home",
            }
        )

    def set_entity(self, entity_id: str, state: str, attributes: Dict[str, Any]) -> None:
        """Set mock entity data."""
        self.entities[entity_id] = Entity(
            entity_id=entity_id,
            state=state,
            attributes=attributes
        )

    def set_forecast(self, forecast_data: list) -> None:
        """Set mock forecast data."""
        self.forecast_data = forecast_data

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get mock entity."""
        return self.entities.get(entity_id)

    def get_forecast(self, device_id: str, forecast_type: str = "hourly") -> list:
        """Get mock forecast."""
        return self.forecast_data
