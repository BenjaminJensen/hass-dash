from PIL import Image, ImageDraw

from hass_weather import HassWeather, WeatherItem
from hass_rooms import HassRooms
from hass import Client, get_hass_client
from hass_sun import HassSun
from display import draw_forecast, draw_weather

def main() -> None:
    client = get_hass_client()
    hass_sun = HassSun(client)
    hass_sun.update()

    hass_weather = HassWeather(client, hass_sun.is_night())
    hass_weather.update()
    forecast = hass_weather.get_forecast()

    with Image.open("assets/hass-dash-house.bmp") as im:
        draw = ImageDraw.Draw(im)
        draw_forecast(draw, forecast)
        draw_weather(draw, hass_weather)
        im.save("out2.bmp", "BMP")

if __name__ == "__main__":
    main()