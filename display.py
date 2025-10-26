from PIL import Image, ImageFont, ImageDraw, ImageOps
from pathlib import Path
from datetime import datetime

'''
print("Pillow version:", Image.__version__)
paths = Path("./assets/weather-icons").glob("*.png")
print("Listing BMP images in ./assets/weather-icons:")
for path in paths:
    with Image.open(path) as im:
        infile = path.name
        print(infile, im.format, f"{im.size}x{im.mode}")

#im = Image.open("hopper.ppm")
#im.show()

'''

#font = ImageFont.load("arial.pil")
font = ImageFont.truetype("arialbd.ttf", 18)
font_big = ImageFont.truetype("arialbd.ttf", 54)

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
        icon_name = fc.get('condition_icon', '')
        icon_path = Path(f"./assets/weather-icons/{icon_name}-50x50.bmp")
        
        try:
            with Image.open(icon_path) as icon_im:
                inverted_image = ImageOps.invert(icon_im)
                im.bitmap((50 + idx * 73, 157), inverted_image)
        except FileNotFoundError:
            print(f"Icon file not found: {icon_path}")
        
        # Draw temperature
        temperature = f'{fc.get('temperature', '')}°C'
        im.text((45 + idx * 73, 205), temperature, font=font)

        # Draw time
        time_value = fc.get('time', '')
        try:
            dt = datetime.fromisoformat(time_value)
            time_str = dt.strftime('%H:%M')
        except Exception:
            # Fallback: use the raw value if parsing fails
            time_str = str(time_value)

        im.text((50 + idx * 73, 140), time_str, font=font)

def draw_weather(im: ImageDraw.ImageDraw, weather: dict) -> None:
        # Draw forecast icon
    icon_name = weather.get('condition_icon', '')
    icon_path = Path(f"./assets/weather-icons/{icon_name}-100x100.bmp")
    
    try:
        with Image.open(icon_path) as icon_im:
            inverted_image = ImageOps.invert(icon_im)
            im.bitmap((80, 20), inverted_image)
    except FileNotFoundError:
        print(f"Icon file not found: {icon_path}")

    # Draw temperature
    temperature = f'{weather.get('temperature', '')}°C'
    im.text((200, 40), temperature, font=font_big)

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