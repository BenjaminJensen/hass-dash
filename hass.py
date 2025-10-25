from dotenv import load_dotenv
import os
from homeassistant_api import Client
from json import dumps
from hass_rooms import HassRooms
from hass_weather import HassWeather

load_dotenv()  # Loads .env file from current directory

HASS_TOKEN = os.getenv("HASS_TOKEN")
if HASS_TOKEN is None:
    raise RuntimeError("HASS_TOKEN environment variable is not set")

HASS_URL = os.getenv("HASS_URL")
if HASS_URL is None:
    raise RuntimeError("HASS_URL environment variable is not set")

client = Client(HASS_URL, HASS_TOKEN)

def get_stuff():
    """Simple demo runner for Home Assistant client actions."""
    print(f'Hass URL: {HASS_URL}')
    print(f'Hass Token: {HASS_TOKEN}')

    with client:
        sun = client.get_entity(entity_id="sun.sun")
        if sun is None:
            raise RuntimeError("Sun entity not found")
        state = sun.get_state()  # Because requests are cached we reduce bandwidth usage :D
        print(dumps(state.attributes, indent=4))

    with client:
        weather = client.get_entity(entity_id="weather.home")
        if weather is None:
            raise RuntimeError("Weather entity not found")
        state = weather.get_state()  # Because requests are cached we reduce bandwidth usage :D
        print(dumps(state.attributes, indent=4))

        w = client.get_domain("weather")
        if w is None:
            raise RuntimeError("Weather domain not found")
        fc = w.get_forecasts(device_id="c8e8bb619ae918a8ed095ab1889f5a07", type="hourly") # type: ignore
        print(dumps(fc, indent=4))

def humi_stuff():
    e_id="0x5cc7c1fffede1ef5_humidity_1"
    h = client.get_entity(entity_id=f"sensor.{e_id}")
    if h is None:
        raise RuntimeError(f"Humidity sensor {e_id} not found")
    state = h.get_state()
    print(dumps(state.attributes, indent=4))
    print(state.state)

def rooms():
    hass_rooms = HassRooms(client)
    rooms = hass_rooms.read_rooms("rooms.yml")
    print("Rooms loaded from rooms.yml:")
    print(rooms)

def weather():
    hass_weather = HassWeather(client)
    hass_weather.update()
    print("Weather data:")
    print(hass_weather)

def main() -> None:
    #rooms()
    weather()
    



if __name__ == "__main__":
    main()