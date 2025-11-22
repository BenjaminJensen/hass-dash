#!/usr/bin/python
# -*- coding:utf-8 -*-
# import sys
# import os
# picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
# libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
# if os.path.exists(libdir):
#     sys.path.append(libdir)

import logging
import epd7in5b_V2
import time
from PIL import Image,ImageDraw,ImageFont
import traceback

# New imports
from hass_weather import HassWeather, WeatherItem
from hass_rooms import HassRooms
from hass import Client, get_hass_client
from hass_sun import HassSun
from display import draw_forecast, draw_weather, draw_sun, draw_rooms


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

    return im
    
# Do hass-dash stuff
#im = Image.open("assets/hass-dash-house.bmp")
#im = Image.open("out2.bmp")

try:
    logging.info("epd7in5b_V2 Demo")

    epd = epd7in5b_V2.EPD()
    logging.info("init and Clear")
    
    # Init the display
    epd.init()

    # Clear the display
    start_clear = time.time()
    epd.Clear()
    elapsed_clear = (time.time() - start_clear) * 1000
    logging.info(f"epd.Clear() took {elapsed_clear:.2f} ms")


    '''
    # FOnt setup
    font = 'liberation/LiberationSans-Bold.ttf'
    font_path = f"/usr/share/fonts/truetype/{font}"

    font24 = ImageFont.truetype(font_path, 24)
    font18 = ImageFont.truetype(font_path, 18)

    # # Drawing on the Horizontal image
    start_clear = time.time()
    logging.info("1.Drawing on the Horizontal image...")
    
    
    # Draw black image
    Himage = Image.new('1', (epd.width, epd.height), 255)  # 255: clear the frame
    draw_Himage = ImageDraw.Draw(Himage)
    draw_Himage.text((10, 0), 'hello world', font = font24, fill = 0)
    draw_Himage.text((10, 20), '7.5inch e-Paper B', font = font24, fill = 0)
    draw_Himage.text((150, 0), 'Benjamin er klog...', font = font24, fill = 0)    
    draw_Himage.line((140, 75, 190, 75), fill = 0)
    draw_Himage.arc((140, 50, 190, 100), 0, 360, fill = 0)
    draw_Himage.rectangle((80, 50, 130, 100), fill = 0)
    draw_Himage.chord((200, 50, 250, 100), 0, 360, fill = 0)
    
    # Draw red image
      
    draw_other = ImageDraw.Draw(Other)
    draw_other.line((20, 50, 70, 100), fill = 0)
    draw_other.line((70, 50, 20, 100), fill = 0)
    draw_other.rectangle((20, 50, 70, 100), outline = 0)
    draw_other.line((165, 50, 165, 100), fill = 0)
    
    elapsed_clear = (time.time() - start_clear) * 1000

    '''

    Other = Image.new('1', (epd.width, epd.height), 255)  # 255: clear the frame  
    logging.info(f"Drawing in buffer took {elapsed_clear:.2f} ms")
    
    # Write buffer to display
    start_clear = time.time()
    
    im_black = create_image_for_display()

    epd.display(epd.getbuffer(im_black), epd.getbuffer(Other))
    
    elapsed_clear = (time.time() - start_clear) * 1000
    logging.info(f"Display buffer took {elapsed_clear:.2f} ms")

    time.sleep(2)

    
    # Drawing on the Vertical image
    #logging.info("2.Drawing on the Vertical image...")
    #Limage = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
    #Limage_Other = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
    #draw_Himage = ImageDraw.Draw(Limage)
    #draw_Himage_Other = ImageDraw.Draw(Limage_Other)
    #draw_Himage.text((2, 0), 'hello world', font = font18, fill = 0)
    #draw_Himage.text((2, 20), '7.5inch epd', font = font18, fill = 0)
    #draw_Himage_Other.text((20, 50), u'微雪电子', font = font18, fill = 0)
    #draw_Himage_Other.line((10, 90, 60, 140), fill = 0)
    #draw_Himage_Other.line((60, 90, 10, 140), fill = 0)
    #draw_Himage_Other.rectangle((10, 90, 60, 140), outline = 0)
    #draw_Himage_Other.line((95, 90, 95, 140), fill = 0)
    #draw_Himage.line((70, 115, 120, 115), fill = 0)
    #draw_Himage.arc((70, 90, 120, 140), 0, 360, fill = 0)
    #draw_Himage.rectangle((10, 150, 60, 200), fill = 0)
    #draw_Himage.chord((70, 150, 120, 200), 0, 360, fill = 0)
    #epd.display(epd.getbuffer(Limage), epd.getbuffer(Limage_Other))
    #time.sleep(2)

    #logging.info("3.read bmp file")
    #epd.init_Fast()
    #Himage = Image.open(os.path.join(picdir, '7in5_V2_b.bmp'))
    #Himage_Other = Image.open(os.path.join(picdir, '7in5_V2_r.bmp'))
    #epd.display(epd.getbuffer(Himage),epd.getbuffer(Himage_Other))
    #time.sleep(2)

    # # partial update
    # logging.info("4.show time")
    # epd.init()
    # epd.display_Base_color(0xFF)
    # epd.init_part()
    # Himage = Image.new('1', (epd.width, epd.height), 0)
    # draw_Himage = ImageDraw.Draw(Himage)
    # num = 0
    # while (True):
    #     draw_Himage.rectangle((10, 120, 130, 170), fill = 0)
    #     draw_Himage.text((10, 120), time.strftime('%H:%M:%S'), font = font24, fill = 255)
    #     epd.display_Partial(epd.getbuffer(Himage),0, 0, epd.width, epd.height)
    #     num = num + 1
    #     if(num == 10):
    #         break


    #logging.info("Clear...")
    #epd.init()
    #epd.Clear()

    logging.info("Goto Sleep...")
    epd.sleep()
    
except IOError as e:
    logging.info(e)
    
except KeyboardInterrupt:    
    logging.info("ctrl + c:")
    epd7in5b_V2.epdconfig.module_exit(cleanup=True)
    exit()
