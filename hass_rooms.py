from homeassistant_api import Client
from json import dumps
from typing import List, Dict, Any
import os
import yaml
from dataclasses import dataclass
from typing import Optional
import logging
from typing import Tuple


logger = logging.getLogger('hass_rooms')


@dataclass
class Position:
    x: int
    y: int

@dataclass
class EntityRef:
    entity_id: str
    name: str
    position: Position
    value: Optional[float] = None
'''
@dataclass
class HassRoom:
    """Simple storage class for a room's basic telemetry."""
    name: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    config: Dict[str, Any] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "HassRoom":
        # Accept common key names; be permissive about types
        name = d.get("name") or d.get("room") or d.get("entity_id")
        # Try a few possible keys for temperature/humidity
        temp = d.get("temperature") or d.get("temp") or d.get("temperature_c")
        hum = d.get("humidity") or d.get("hum")

        # Convert to float where possible
        def to_float(v):
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        return HassRoom(name=name, temperature=to_float(temp), humidity=to_float(hum))

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "temperature": self.temperature, "humidity": self.humidity}
'''
class HassRoom:
    def __init__(self, config: Dict[str, Any], client: Client):
        self.client = client
        self.config = config or {}
        self.parse_config()

    @property
    def temperature(self) -> Optional[float]:
        t = self._climate
        if t:
            return t.value
        return None
    
    @property
    def temperature_pos(self) -> Optional[Tuple[int, int]]:
        t = self._climate
        if t:
            return t.position.x, t.position.y
        return None
    
    @property
    def humidity(self) -> Optional[float]:
        h = self._humidity
        if h:
            return h.value
        return None
    
    @property
    def humidity_pos(self) -> Optional[Tuple[int, int]]:
        h = self._humidity
        if h:
            return h.position.x, h.position.y
        return None
    def parse_entity_ref(self, name) -> EntityRef | None:
        if name in self.config:
            entity_cfg = self.config[name]
            pos = Position(
                x=entity_cfg.get('position', {}).get('x', 0), 
                y=entity_cfg.get('position', {}).get('y', 0))
            return EntityRef(entity_cfg['entity_id'], name, pos)
        return None
    
    def parse_config(self):
        if 'name' in self.config:
            self.name = self.config['name']
        else:
            self.name = "Unnamed Room"

        # Parse optional entity references
        self._humidity = self.parse_entity_ref('humidity')
        self._climate = self.parse_entity_ref('climate')

    def update_climate(self):
        with self.client:
            if self._climate:
                e = f'climate.{self._climate.entity_id}'
                climate_entity = self.client.get_entity(entity_id=e)
                if climate_entity:
                    state = climate_entity.get_state()
                    attributes = state.attributes
                    #print(dumps(attributes, indent=4))
                    self._climate.value = attributes.get('current_temperature')

    def update_humidity(self):
        with self.client:
            if self._humidity:
                e = f'sensor.{self._humidity.entity_id}'
                humidity_entity = self.client.get_entity(entity_id=e)
                if humidity_entity:
                    state = humidity_entity.get_state()
                    #print(dumps(attributes, indent=4))
                    try:
                        self._humidity.value = float(state.state)
                    except:
                        logger.warning(f"Could not convert humidity state to float: {state.state} of room {self.name}")
                        self._humidity.value = None

    def update(self):
        logging.info(f"Updating room: {self.name}")
        self.update_climate()
        self.update_humidity()

    def __repr__(self) -> str:
        parts = [f"name={self.name}"]
        # Include temperature/humidity only if present
        if hasattr(self, "temperature") and self.temperature is not None:
            parts.append(f"temperature={self.temperature}")
        if hasattr(self, "humidity") and self.humidity is not None:
            parts.append(f"humidity={self.humidity}")
        return f"HassRoom({', '.join(parts)})"
    
class HassRooms:
    def __init__(self, client: Client):
        self.client = client
        self.rooms: List[HassRoom] = []

    def update_rooms(self):
        for r in self.rooms:
            r.update()

    def read_rooms(self, path: str = "rooms.yml") -> List[HassRoom]:
        """Read and parse a rooms YAML file.

        Args:
            path: Path to the YAML file. Relative paths are resolved against CWD.

        Returns:
            A list of room dictionaries (the value of the top-level `rooms:` key,
            or the top-level list if the file is a plain list).

        Raises:
            RuntimeError: if PyYAML is not installed.
            FileNotFoundError: if the YAML file does not exist.
            ValueError: if the YAML structure does not contain rooms.
        """

        file_path = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"rooms file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        # Accept either a mapping with 'rooms' key, or a top-level list of rooms
        if isinstance(data, dict):
            rooms = data.get("rooms")
            if rooms is None:
                # empty dict or missing key
                raise ValueError("rooms.yml does not contain a 'rooms' key")
            
            for room_cfg in rooms:
                room = HassRoom(config=room_cfg, client=self.client)
                self.rooms.append(room)

            return self.rooms
        
        if isinstance(data, list):
            return data

        raise ValueError("Unexpected YAML structure in rooms.yml")


def main() -> None:
    from hass import Client, get_hass_client
    logging.basicConfig(level=logging.INFO)

    client = get_hass_client()
    hass_rooms = HassRooms(client)
    rooms = hass_rooms.read_rooms()
    hass_rooms.update_rooms()
    for idx, room in enumerate(rooms):
        room_name = room.name
        temperature = f'{room.temperature}°C'
        humidity = f'{room.humidity}%'
        print(f"Room {idx}: {room_name}, Temp: {temperature}, Humidity: {humidity}")

if __name__ == "__main__":
    main()