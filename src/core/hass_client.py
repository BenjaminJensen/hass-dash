"""Abstract interface for Home Assistant client."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class Entity:
    """Represents a Home Assistant entity."""
    entity_id: str
    state: str
    attributes: Dict[str, Any]


class HASSClient(ABC):
    """Abstract base class for Home Assistant client.
    
    This interface allows for real HASS connections and mock implementations.
    """

    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID.
        
        Args:
            entity_id: The entity ID (e.g., 'sensor.temperature')
            
        Returns:
            Entity object or None if not found
        """
        pass

    @abstractmethod
    def get_forecast(self, device_id: str, forecast_type: str = "hourly") -> list:
        """Get weather forecast data.
        
        Args:
            device_id: The weather device ID
            forecast_type: "hourly" or "daily"
            
        Returns:
            List of forecast dictionaries
        """
        pass


class RealHASSClient(HASSClient):
    """Real implementation using homeassistant_api."""

    def __init__(self, url: str, token: str):
        """Initialize with Home Assistant URL and token."""
        from homeassistant_api import Client as HassApiClient

        self.url = url
        self.token = token
        self._client = HassApiClient(url, token)

    def _extract_forecast_list(self, forecasts: Any) -> list:
        """Normalize different API response shapes into a list of forecast dicts."""
        if isinstance(forecasts, list):
            if forecasts and all(isinstance(item, dict) and "datetime" in item for item in forecasts):
                return forecasts

            for item in forecasts:
                extracted = self._extract_forecast_list(item)
                if extracted:
                    return extracted

        if isinstance(forecasts, tuple):
            for item in forecasts:
                extracted = self._extract_forecast_list(item)
                if extracted:
                    return extracted

        if isinstance(forecasts, dict):
            direct = forecasts.get("forecast")
            if isinstance(direct, list):
                return direct

            for value in forecasts.values():
                if isinstance(value, dict):
                    nested = value.get("forecast")
                    if isinstance(nested, list):
                        return nested

        return []

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity from Home Assistant."""
        try:
            with self._client:
                entity = self._client.get_entity(entity_id=entity_id)
                if entity is None:
                    return None
                state = entity.get_state()
                return Entity(
                    entity_id=entity_id,
                    state=state.state,
                    attributes=state.attributes or {}
                )
        except Exception as e:
            print(f"Error fetching entity {entity_id}: {e}")
            return None

    def get_forecast(self, device_id: str, forecast_type: str = "hourly") -> list:
        """Get forecast from Home Assistant."""
        try:
            with self._client:
                weather = self._client.get_domain("weather")
                if weather is None:
                    return []
                forecasts = weather.get_forecasts(device_id=device_id, type=forecast_type)
                return self._extract_forecast_list(forecasts)
        except Exception as e:
            print(f"Error fetching forecast: {e}")
            return []
