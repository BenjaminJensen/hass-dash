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

from PIL import Image, ImageDraw

from hass_weather import HassWeather, WeatherItem
from hass_rooms import HassRooms
from hass import Client, get_hass_client
from hass_sun import HassSun
from display import draw_forecast, draw_weather


logging.basicConfig(level=logging.DEBUG)

try:
    logging.info("epd7in5b_V2 Demo")

    epd = epd7in5b_V2.EPD()
    logging.info("init and Clear")
    
    epd.init()

    start_clear = time.time()
    epd.Clear()
    elapsed_clear = (time.time() - start_clear) * 1000
    logging.info(f"epd.Clear() took {elapsed_clear:.2f} ms")

    #font24 = ImageFont.truetype('Font.ttc', 24)
    #font18 = ImageFont.truetype('Font.ttc', 18)

    # # Drawing on the Horizontal image
    start_clear = time.time()
    logging.info("1.Drawing on the Horizontal image...")
    # Himage = Image.new('1', (epd.width, epd.height), 255)  # 255: clear the frame
    # Other = Image.new('1', (epd.width, epd.height), 255)  # 255: clear the frame
    # draw_Himage = ImageDraw.Draw(Himage)
    # draw_other = ImageDraw.Draw(Other)
    # draw_Himage.text((10, 0), 'hello world', font = font24, fill = 0)
    # draw_Himage.text((10, 20), '7.5inch e-Paper B', font = font24, fill = 0)
    # draw_Himage.text((150, 0), 'Benjamin er klog...', font = font24, fill = 0)    
    # draw_other.line((20, 50, 70, 100), fill = 0)
    # draw_other.line((70, 50, 20, 100), fill = 0)
    # draw_other.rectangle((20, 50, 70, 100), outline = 0)
    # draw_other.line((165, 50, 165, 100), fill = 0)
    # draw_Himage.line((140, 75, 190, 75), fill = 0)
    # draw_Himage.arc((140, 50, 190, 100), 0, 360, fill = 0)
    # draw_Himage.rectangle((80, 50, 130, 100), fill = 0)
    # draw_Himage.chord((200, 50, 250, 100), 0, 360, fill = 0)
        
    elapsed_clear = (time.time() - start_clear) * 1000
    logging.info(f"Drawing in buffer took {elapsed_clear:.2f} ms")
    
    # Write buffer to display
    start_clear = time.time()

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
        #im.save("out2.bmp", "BMP")

        epd.display(epd.getbuffer(im),None)

    elapsed_clear = (time.time() - start_clear) * 1000
    logging.info(f"Display buffer took {elapsed_clear:.2f} ms")

    time.sleep(2)

    logging.info("Goto Sleep...")
    epd.sleep()
    
except IOError as e:
    logging.info(e)
    
except KeyboardInterrupt:    
    logging.info("ctrl + c:")
    epd7in5b_V2.epdconfig.module_exit(cleanup=True)
    exit()
