#!/usr/bin/env python3
"""The README's banner (docs/images/banner.png, 1600x480): a bullet in slow motion over a dusk sky, and the title, in
Crema's layout (the MGR port's make-banner.py).

Original art, drawn here: no game artwork or logo.

    python3 scripts/make-banner.py
"""
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
W, H = 1600, 480
MUTED = (0xB4, 0xA4, 0x94)
AMBER = (0xF5, 0xA6, 0x23)


def font(names, size):
    for name in names:
        for d in ("C:/Windows/Fonts", "/mnt/c/Windows/Fonts", "/usr/share/fonts/truetype/dejavu"):
            path = os.path.join(d, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def background():
    """Near black, a dusk glow low on the left and a cold one high on the right, faint film lines"""
    img = Image.new("RGBA", (W, H), (0x0B, 0x09, 0x08, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((-260, 180, 900, 820), fill=(0x6A, 0x2E, 0x0E, 255))
    d.ellipse((1150, -320, 1900, 260), fill=(0x0E, 0x2A, 0x33, 220))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(160)))
    lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    for y in range(0, H, 6):
        ld.line([(0, y), (W, y)], fill=(0xFF, 0xE0, 0xB0, 7), width=2)
    return Image.alpha_composite(img, lines)


def bullet():
    """A bullet flying right with the air rippling behind it, drawn 2x for smooth edges"""
    K = 2
    cy = 250 * K
    base, length, r = 430 * K, 180 * K, 25 * K
    body_end = base + int(length * 0.5)
    tip = base + length
    shape = Image.new("L", (W * K, H * K), 0)
    sd = ImageDraw.Draw(shape)
    top = []
    for i in range(61):
        t = i / 60
        top.append((body_end + (tip - body_end) * t, cy - r * (1 - t ** 2.2) ** 0.5))
    poly = [(base, cy - r)] + top + [(x, 2 * cy - y) for x, y in reversed(top)] + [(base, cy + r)]
    sd.polygon(poly, fill=255)

    # Copper, lit from above: a vertical gradient through the shape, a hot rim along the top
    metal = Image.new("RGBA", (W * K, H * K), (0, 0, 0, 0))
    md = ImageDraw.Draw(metal)
    for y in range(cy - r, cy + r + 1):
        t = (y - (cy - r)) / (2 * r)
        k = math.exp(-((t - 0.28) / 0.16) ** 2)
        c = (int(0x8A + 0x6C * k + 0x20 * (1 - t)), int(0x46 + 0x80 * k), int(0x1E + 0x6A * k), 255)
        md.line([(base, y), (tip, y)], fill=c)
    layer = Image.new("RGBA", (W * K, H * K), (0, 0, 0, 0))
    layer.paste(metal, (0, 0), shape)
    ImageDraw.Draw(layer).line([(base, cy + r - K), (body_end, cy + r - K)], fill=(0x3A, 0x1C, 0x0C, 255), width=2 * K)
    layer = layer.resize((W, H), Image.LANCZOS)

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # The trail: a streak of hot air thinning out behind it
    trail = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(trail)
    b, rr, c = base // K, r // K, cy // K
    for x in range(40, b):
        t = (x - 40) / (b - 40)
        half = 2 + (rr * 0.75 - 2) * t ** 1.6
        td.line([(x, c - half), (x, c + half)], fill=(0xFF, 0xD8, 0xA0, int(120 * t ** 2.4)))
    out = Image.alpha_composite(out, trail.filter(ImageFilter.GaussianBlur(5)))
    # The ripples it leaves in the air: rings growing and fading behind it
    rings = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rings)
    for i, back in enumerate((46, 120, 210, 315)):
        x = b - back
        hh = rr * (1.7 + 0.55 * i)
        ww = 9 + 5 * i
        rd.ellipse((x - ww, c - hh, x + ww, c + hh), outline=(0xFF, 0xE6, 0xC8, 150 - 30 * i), width=2)
    out = Image.alpha_composite(out, rings.filter(ImageFilter.GaussianBlur(1.2)))
    glow = layer.filter(ImageFilter.GaussianBlur(18))
    tint = Image.new("RGBA", (W, H), (0xFF, 0x9A, 0x3C, 0))
    tint.putalpha(glow.getchannel("A").point(lambda a: a * 0.55))
    out = Image.alpha_composite(out, tint)
    out = Image.alpha_composite(out, layer)

    # Dust hanging in the slowed air
    dust = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dust)
    rnd = random.Random(3)
    for _ in range(90):
        x, y = rnd.uniform(20, 780), rnd.uniform(40, 440)
        s = rnd.uniform(0.8, 2.4)
        dd.ellipse((x - s, y - s, x + s, y + s), fill=(0xFF, 0xD9, 0xA8, int(rnd.uniform(30, 140))))
    return Image.alpha_composite(out, dust.filter(ImageFilter.GaussianBlur(0.7)))


def gradient_text(img, x_right, y, text, f, left, right):
    """Right-aligned text filled with a left-to-right gradient, like Crema's title"""
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    x = x_right - tw
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((x - bbox[0], y - bbox[1]), text, font=f, fill=255)
    grad = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(grad)
    for i in range(tw + 1):
        t = i / max(tw, 1)
        c = tuple(round(left[k] + (right[k] - left[k]) * t) for k in range(3)) + (255,)
        gd.line([(x + i, 0), (x + i, H)], fill=c)
    grad.putalpha(ImageChops.multiply(mask, Image.new("L", (W, H), 255)))
    img.alpha_composite(grad)


def right_text(img, x_right, y, text, f, fill):
    d = ImageDraw.Draw(img)
    d.text((x_right - d.textlength(text, font=f), y), text, font=f, fill=fill)


def main():
    img = background()
    img.alpha_composite(bullet())
    bold = font(("segoeuib.ttf", "DejaVuSans-Bold.ttf"), 128)
    small = font(("segoeuil.ttf", "segoeui.ttf", "DejaVuSans.ttf"), 34)
    gradient_text(img, 1530, 140, "Max Payne 3", bold, (0xF6, 0xF1, 0xEA), AMBER)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((1530 - 330, 318, 1530, 322), radius=2, fill=AMBER + (230,))
    right_text(img, 1530, 342, "XBOX 360 RECOMP  ·  PS4", small, MUTED)
    out = os.path.join(ROOT, "docs", "images")
    os.makedirs(out, exist_ok=True)
    img.convert("RGB").save(os.path.join(out, "banner.png"))
    print("wrote docs/images/banner.png")


if __name__ == "__main__":
    main()
