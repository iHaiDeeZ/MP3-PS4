#!/usr/bin/env python3
"""The pkg's icon0.png (512x512): original art, no game assets. Usage: make-icon.py <out.png>"""
import sys

from PIL import Image, ImageDraw, ImageFont

W = 512
img = Image.new("RGB", (W, W), (14, 14, 16))
d = ImageDraw.Draw(img)
# Film-grain bands and a red slash.
for y in range(0, W, 4):
    shade = 18 + (y * 7919 % 13)
    d.line([(0, y), (W, y)], fill=(shade, shade, shade + 2))
d.polygon([(0, 330), (W, 250), (W, 290), (0, 370)], fill=(150, 16, 20))


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def centered(text, y, size, fill):
    f = font(size)
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


centered("MP3", 120, 150, (235, 235, 235))
centered("PS4", 395, 70, (200, 30, 34))
img.save(sys.argv[1])
print("wrote", sys.argv[1])
