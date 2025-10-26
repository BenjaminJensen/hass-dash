from PIL import Image, ImageFont, ImageDraw
from pathlib import Path

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
font = ImageFont.truetype("arial.ttf", 16)

def do_stuff():
    with Image.open("assets/hass-dash-house.bmp") as im:
        draw = ImageDraw.Draw(im)
        draw.text((10, 10), "hello", font=font)
        im.save("out.bmp", "BMP")

def main() -> None:
    print("Pillow version:", Image.__version__)
    
    do_stuff()

if __name__ == "__main__":
    main()