from PIL import Image, ImageDraw

from hass_weather import HassWeather, WeatherItem
from hass_rooms import HassRooms
from hass import Client, get_hass_client
from hass_sun import HassSun
from display import draw_forecast, draw_weather, draw_sun, draw_rooms, draw_update_time

import logging
logger = logging.getLogger(__name__)


def weather_display(draw: ImageDraw.ImageDraw, client: Client, hass_sun: HassSun) -> None:
    hass_weather = HassWeather(client, hass_sun.is_night())
    hass_weather.update()
    forecast = hass_weather.get_forecast()
    draw_weather(draw, hass_weather)
    draw_forecast(draw, forecast)

def sun_display(draw: ImageDraw.ImageDraw, client: Client) -> None:
    hass_sun = HassSun(client)
    hass_sun.update()
    draw_sun(draw, hass_sun)

    return hass_sun

def room_display(draw: ImageDraw.ImageDraw, client: Client) -> None:
    hass_rooms = HassRooms(client)
    rooms = hass_rooms.read_rooms()
    hass_rooms.update_rooms()
    draw_rooms(draw, rooms)
    '''
    for idx, room in enumerate(rooms):
        room_name = room.name
        temperature = f'{room.temperature}°C'
        humidity = f'{room.humidity}%'

        print(f"Room {idx}: {room_name}, Temp: {temperature}, Humidity: {humidity}")
    ''' 


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    client = get_hass_client()


    with Image.open("assets/hass-dash-house.bmp") as im:
        draw = ImageDraw.Draw(im)
        
        hass_sun = sun_display(draw, client)

        weather_display(draw, client, hass_sun)
        
        room_display(draw, client)

        draw_update_time(draw)

        im.save("out2.bmp", "BMP") 

if __name__ == "__main__":
    main()