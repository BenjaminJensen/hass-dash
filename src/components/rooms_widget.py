"""Rooms widget component."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from components.widget import Widget
from core.hass_client import HASSClient
from rendering.renderer import Renderer
import yaml


@dataclass
class EntityConfig:
    """Entity reference and optional draw position."""

    entity_id: str
    position: Optional[Tuple[int, int]] = None


@dataclass
class Room:
    """Represents a room with temperature and humidity."""

    key: str
    name: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    climate_position: Optional[Tuple[int, int]] = None
    humidity_position: Optional[Tuple[int, int]] = None


class RoomsWidget(Widget):
    """Self-contained rooms widget that fetches and renders room data."""

    def __init__(
        self,
        hass_client: HASSClient,
        renderer: Renderer,
        config_path: Optional[str] = None,
        cache_ttl: int = 60
    ):
        """Initialize rooms widget.
        
        Args:
            hass_client: HASS client instance
            renderer: Rendering backend
            config_path: Path to rooms.yml configuration file
            cache_ttl: Cache time-to-live in seconds (default: 60 = 1 min)
        """
        super().__init__(hass_client, renderer, cache_ttl=cache_ttl)
        self.config_path = config_path or "rooms.widget.yml"
        self.rooms: List[Room] = []
        self._room_config: Dict[str, Any] = {}

    def _resolve_config_path(self) -> Path:
        """Resolve the rooms config path from CWD or the repository root."""
        config_file = Path(self.config_path)
        if config_file.is_absolute() or config_file.exists():
            return config_file

        return Path(__file__).resolve().parents[2] / config_file

    def _parse_position(self, value: Any) -> Optional[Tuple[int, int]]:
        """Parse a coordinate mapping into a tuple."""
        if not isinstance(value, dict):
            return None

        x = value.get("x")
        y = value.get("y")
        if x is None or y is None:
            return None

        try:
            return int(x), int(y)
        except (TypeError, ValueError):
            return None

    def _parse_entity_config(self, value: Any) -> Optional[EntityConfig]:
        """Parse an entity reference from the rooms config."""
        if not isinstance(value, dict):
            return None

        entity_id = value.get("entity_id")
        if not entity_id:
            return None

        return EntityConfig(
            entity_id=str(entity_id),
            position=self._parse_position(value.get("position")),
        )

    def _extract_float(self, entity: Any, attribute_name: Optional[str] = None) -> Optional[float]:
        """Convert an entity state or attribute into a float when possible."""
        if entity is None:
            return None

        candidates: List[Any] = []
        if attribute_name:
            candidates.append(entity.attributes.get(attribute_name))
        candidates.append(entity.state)

        for candidate in candidates:
            try:
                return float(candidate)
            except (TypeError, ValueError):
                continue

        return None

    def _load_config(self) -> None:
        """Load room configuration from YAML file."""
        try:
            config_file = self._resolve_config_path()
            if not config_file.exists():
                print(f"Config file not found: {self.config_path}")
                return

            with open(config_file, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}

            if not isinstance(raw_config, dict):
                print(f"Invalid room config format in: {config_file}")
                return

            rooms_config = raw_config.get("rooms")
            if not isinstance(rooms_config, dict):
                print(f"Config file missing a rooms mapping: {config_file}")
                return

            self._room_config = rooms_config
        except Exception as e:
            print(f"Error loading room config: {e}")

    def _fetch_data(self) -> None:
        """Fetch room data from HASS."""
        if not self._room_config:
            self._load_config()

        self.rooms = []

        for room_key, room_config in self._room_config.items():
            if not isinstance(room_config, dict):
                continue

            room = Room(
                key=str(room_key),
                name=str(room_config.get("name", room_key)),
            )

            climate_config = self._parse_entity_config(room_config.get("climate"))
            humidity_config = self._parse_entity_config(room_config.get("humidity"))

            if climate_config:
                room.climate_position = climate_config.position
                temp_entity = self.hass_client.get_entity(climate_config.entity_id)
                room.temperature = self._extract_float(temp_entity, "current_temperature")

            if humidity_config:
                room.humidity_position = humidity_config.position
                humid_entity = self.hass_client.get_entity(humidity_config.entity_id)
                room.humidity = self._extract_float(humid_entity)

            self.rooms.append(room)

    def render(self) -> None:
        """Render rooms widget."""
        try:
            y_offset = 110

            for room in self.rooms:
                temp_str = f"{room.temperature:.1f}°C" if room.temperature is not None else "N/A"
                humid_str = f"{room.humidity:.0f}%" if room.humidity is not None else "N/A"

                temp_position = room.climate_position or (10, y_offset)
                humid_position = room.humidity_position or (140, y_offset)

                self.renderer.draw_text(
                    temp_position,
                    f"{temp_str}",
                    style="normal",
                    fill=0,
                )
                self.renderer.draw_text(humid_position, humid_str, style="normal", fill=0)

                if room.climate_position is None and room.humidity_position is None:
                    y_offset += 15
        except Exception as e:
            print(f"Error rendering rooms widget: {e}")

    def get_rooms(self) -> List[Room]:
        """Get list of rooms."""
        return self.rooms
