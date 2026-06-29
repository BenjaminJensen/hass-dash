"""Rooms widget component."""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from components.widget import Widget
from core.hass_client import HASSClient
from rendering.renderer import Renderer
import yaml
from pathlib import Path


@dataclass
class Room:
    """Represents a room with temperature and humidity."""
    name: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None


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
        self.config_path = config_path or "rooms.yml"
        self.rooms: List[Room] = []
        self._room_config: Dict[str, Any] = {}

    def _load_config(self) -> None:
        """Load room configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                print(f"Config file not found: {self.config_path}")
                return

            with open(config_file, "r") as f:
                self._room_config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading room config: {e}")

    def _fetch_data(self) -> None:
        """Fetch room data from HASS."""
        if not self._room_config:
            self._load_config()

        self.rooms = []

        for room_name, room_config in self._room_config.items():
            room = Room(name=room_name)

            # Get temperature sensor
            if "temperature_entity" in room_config:
                temp_entity = self.hass_client.get_entity(
                    room_config["temperature_entity"]
                )
                if temp_entity:
                    try:
                        room.temperature = float(temp_entity.state)
                    except (ValueError, TypeError):
                        pass

            # Get humidity sensor
            if "humidity_entity" in room_config:
                humid_entity = self.hass_client.get_entity(
                    room_config["humidity_entity"]
                )
                if humid_entity:
                    try:
                        room.humidity = float(humid_entity.state)
                    except (ValueError, TypeError):
                        pass

            self.rooms.append(room)

    def render(self) -> None:
        """Render rooms widget."""
        draw = self.renderer.get_draw()

        from PIL import ImageFont

        try:
            font = ImageFont.load_default()
            y_offset = 110

            for room in self.rooms:
                temp_str = f"{room.temperature:.1f}°C" if room.temperature else "N/A"
                humid_str = f"{room.humidity:.0f}%" if room.humidity else "N/A"

                draw.text((10, y_offset), f"{room.name}: {temp_str} / {humid_str}", font=font, fill=0)
                y_offset += 15
        except Exception as e:
            print(f"Error rendering rooms widget: {e}")

    def get_rooms(self) -> List[Room]:
        """Get list of rooms."""
        return self.rooms
