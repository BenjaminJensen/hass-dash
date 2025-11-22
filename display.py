from PIL import Image, ImageFont, ImageDraw, ImageOps
from pathlib import Path
from datetime import datetime
import os


if os.name == 'nt':
    font_path = "C:/Windows/Fonts/arialbd.ttf"
else:
    font = 'liberation/LiberationSans-Bold.ttf'
    font_path = f"/usr/share/fonts/truetype/{font}"

font = ImageFont.truetype(font_path, 18)
font_big = ImageFont.truetype(font_path, 54)

forecasts = [
    {
        'time': '2024-06-01T19:00:00+00:00',
        'temperature': 21.5,
        'humidity': 55,
        'condition_icon': 'weather-rainy',
    },
    {
        'time': '2024-06-01T20:00:00+00:00',
        'temperature': 20.0,
        'humidity': 60,
        'condition_icon': 'weather-windy-variant',
    },
    {
        'time': '2024-06-01T21:00:00+00:00',
        'temperature': 18.5,
        'humidity': 65,
        'condition_icon': 'weather-windy',
    },
    {
        'time': '2024-06-01T22:00:00+00:00',
        'temperature': 17.0,
        'humidity': 70,
        'condition_icon': 'weather-sunny',
    },
    {
        'time': '2024-06-01T23:00:00+00:00',
        'temperature': 16.0,
        'humidity': 75,
        'condition_icon': 'weather-snowy',
    }

]

def draw_forecast(im: ImageDraw.ImageDraw, forecast: list) -> None:
    for idx, fc in enumerate(forecast):
        # idx is the iteration index (0-based)
        # Draw forecast icon
        icon_name = fc.condition_icon
        icon_path = Path(f"./assets/weather-icons/{icon_name}-50x50.bmp")
        
        try:
            with Image.open(icon_path) as icon_im:
                inverted_image = ImageOps.invert(icon_im)
                im.bitmap((50 + idx * 73, 157), inverted_image)
        except FileNotFoundError:
            print(f"Icon file not found: {icon_path}")
        
        # Draw temperature
        temperature = f'{fc.temperature}°C'
        im.text((45 + idx * 73, 205), temperature, font=font)

        # Draw time
        time_value = fc.time
        try:
            if isinstance(time_value, datetime):
                dt = time_value
            else:
                raise ValueError("time_value is not a datetime object")
            time_str = dt.strftime('%H:%M')
        except Exception:
            # Fallback: use the raw value if parsing fails
            print(f"Failed to parse time: {time_value}")
            time_str = str(time_value)

        im.text((50 + idx * 73, 140), time_str, font=font)

def draw_weather(im: ImageDraw.ImageDraw, weather: dict) -> None:
        # Draw forecast icon
    icon_name = weather.condition_icon
    icon_path = Path(f"./assets/weather-icons/{icon_name}-100x100.bmp")
    
    try:
        with Image.open(icon_path) as icon_im:
            inverted_image = ImageOps.invert(icon_im)
            im.bitmap((80, 20), inverted_image)
    except FileNotFoundError:
        print(f"Icon file not found: {icon_path}")

    # Draw temperature
    temperature = f'{weather.temperature}°C'
    im.text((200, 40), temperature, font=font_big)

def draw_sun(im: ImageDraw.ImageDraw, sun:dict) -> None:
    # Draw sunrise icon

    # Draw sunrise time
    sunrise_time = sun.rising
    try:
        if isinstance(sunrise_time, datetime):
            dt = sunrise_time
        else:
            raise ValueError("dawn is not a datetime object")
        time_str = dt.strftime('%H:%M')

    except Exception:
        # Fallback: use the raw value if parsing fails
        print(f"Failed to parse sunrise time: {sunrise_time}")
        time_str = str(sunrise_time)

    im.text((105, 405), f'{time_str}', font=font)

    # Draw sunset icon
    icon_path = Path(f"./assets/weather-icons/weather-sunset-down-100x100.bmp")
    

    # Draw sunset time
    sunset_time = sun.setting
    try:
        if isinstance(sunset_time, datetime):
            dt = sunset_time
        else:
            raise ValueError("dusk is not a datetime object")
        time_str = dt.strftime('%H:%M')
    except Exception:
        # Fallback: use the raw value if parsing fails
        print(f"Failed to parse sunset time: {sunset_time}")
        time_str = str(sunset_time)

    im.text((270, 405), f'{time_str}', font=font)

def draw_rooms(im: ImageDraw.ImageDraw, rooms: list) -> None:
    for idx, room in enumerate(rooms):
        temperature = f'{room.temperature}°C'
        pos = room.temperature_pos
        im.text(pos, temperature, font=font)
        humidity = f'{room.humidity}%'
        pos = room.humidity_pos
        im.text(pos, humidity, font=font)
        

def do_stuff():
    with Image.open("assets/hass-dash-house.bmp") as im:
        draw = ImageDraw.Draw(im)
        draw_forecast(draw, forecasts)
        draw_weather(draw, {'temperature': 22.0, 'condition_icon': 'weather-windy-variant'})
        im.save("out.bmp", "BMP")

def main() -> None:
    print("Pillow version:", Image.__version__)
    
    do_stuff()

if __name__ == "__main__":
    main()