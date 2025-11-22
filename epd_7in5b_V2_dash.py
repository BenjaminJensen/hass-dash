import logging
import epd7in5b_V2
import time
from PIL import Image,ImageDraw

# New imports
from hass_weather import HassWeather
from hass_rooms import HassRooms
from hass import get_hass_client
from hass_sun import HassSun
from display import (
    draw_forecast, 
    draw_weather, 
    draw_sun, 
    draw_rooms,
    draw_update_time)


# Setup logging
logging.basicConfig(level=logging.INFO)

def create_image_for_display() -> Image.Image:
    client = get_hass_client()

    im = Image.open("assets/hass-dash-house.bmp")
    draw = ImageDraw.Draw(im)
    
    hass_sun = HassSun(client)
    hass_sun.update()
    draw_sun(draw, hass_sun)

    hass_weather = HassWeather(client, hass_sun.is_night())
    hass_weather.update()
    forecast = hass_weather.get_forecast()
    draw_weather(draw, hass_weather)
    draw_forecast(draw, forecast)

    hass_rooms = HassRooms(client)
    rooms = hass_rooms.read_rooms()
    hass_rooms.update_rooms()
    draw_rooms(draw, rooms)

    draw_update_time(draw)

    return im

def main() -> None:
    try:
        logging.info("Hass-Dash e-Paper Display")

        epd = epd7in5b_V2.EPD()
        logging.info("init and Clear")
        
        # Init the display
        epd.init()

        # Clear the display
        start_clear = time.time()
        epd.Clear()
        elapsed_clear = (time.time() - start_clear)
        logging.info(f"epd.Clear() took {elapsed_clear:.2f} seconds")

        start_clear = time.time()
        Other = Image.new('1', (epd.width, epd.height), 255)  # 255: clear the frame  
        elapsed_clear = (time.time() - start_clear)
        logging.info(f"Drawing in buffer took {elapsed_clear:.2f} seconds")
        
        # Write buffer to display
        start_clear = time.time()
        
        im_black = create_image_for_display()

        epd.display(epd.getbuffer(im_black), epd.getbuffer(Other))
        
        elapsed_clear = (time.time() - start_clear)
        logging.info(f"Display buffer took {elapsed_clear:.2f} seconds")

        time.sleep(2)

        logging.info("Goto Sleep...")
        epd.sleep()
        
    except IOError as e:
        logging.info(e)
        
    except KeyboardInterrupt:    
        logging.info("ctrl + c:")
        epd7in5b_V2.epdconfig.module_exit(cleanup=True)
        exit()

if __name__ == '__main__':
    main()