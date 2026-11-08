#!/usr/bin/env python3
"""PlayStation button icons for Max Payne 3 (the user, 2026-11-06: "swap the controller buttons within the game with the
ps4 controller buttons", "make high quality 3d buttons").

Renders each icon 8x larger (shaded button body, bevelled rim, gloss, drop shadow, embossed symbol), scales it down
with premultiplied alpha to the size of the game's Xbox icon it replaces, encodes it as the game stores that icon
(DXT5, Xenos-tiled, 8-in-16 byte order: tools/icons.py), and writes the table the game uses to find the Xbox icon by
the hash of its blocks (mp3/ps4/mp3_ps4_icons.inc).

  py tools/ps_icons.py <dir with the Xbox icon dumps> <out mp3_ps4_icons.inc> <preview dir>

The dumps are the live console's `memdump` of the 64 KB blocks holding the icons (mem_18A00000_10000.bin,
mem_09000000_10000.bin); only hashes of the game's icons go into the table, not their pixels.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icons  # noqa: E402

SS = 8
FONT = "C:/Windows/Fonts/arialbd.ttf"
CONDENSED = "C:/Windows/Fonts/bahnschrift.ttf"  # its "Bold Condensed" instance, for OPTIONS

# The Xbox icons: (dump file, offset in it, width, height, name of the PlayStation icon replacing it).
XBOX = [
    ("mem_18A00000_10000.bin", 0x0000, 32, 32, "circle"),    # B
    ("mem_18A00000_10000.bin", 0x2000, 32, 32, "touchpad"),  # Back (the PS4 driver's touch pad click)
    ("mem_18A00000_10000.bin", 0x4000, 32, 32, "triangle"),  # Y
    ("mem_18A00000_10000.bin", 0x6000, 32, 32, "cross"),     # A
    ("mem_18A00000_10000.bin", 0xA000, 32, 32, "square"),    # X
    ("mem_18A00000_10000.bin", 0xC000, 32, 32, "r2"),        # RT
    ("mem_18A00000_10000.bin", 0xE000, 32, 32, "options"),   # Start
    ("mem_09000000_10000.bin", 0x2000, 64, 32, "l1"),        # LB
    ("mem_09000000_10000.bin", 0x6000, 64, 32, "r1"),        # RB
]

COLORS = {"cross": (124, 178, 255), "circle": (255, 102, 102), "square": (242, 140, 222), "triangle": (64, 226, 170)}


def gradient(h, w, top, bottom):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    return np.broadcast_to(np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t, (h, w, 3)).copy()


def shape_mask(w, h, draw_fn):
    """A float mask (0..1) of a shape drawn by draw_fn(ImageDraw) on a w x h canvas (already 8x)."""
    m = Image.new("L", (w, h), 0)
    draw_fn(ImageDraw.Draw(m))
    return np.asarray(m, np.float32) / 255


def button_body(w, h, mask, rim_mask):
    """A glossy dark button: a vertical gradient, darker towards the edge, a bevelled rim lit from above, a highlight."""
    body = gradient(h, w, (78, 82, 92), (12, 13, 16))
    edge = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(w / 14)),
                      np.float32) / 255
    body *= (0.55 + 0.45 * edge)[..., None]
    rim = gradient(h, w, (176, 182, 196), (26, 27, 31))
    body = body * (1 - rim_mask[..., None]) + rim * rim_mask[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gx, gy = (xx - w / 2) / (w * 0.42), (yy - h * 0.27) / (h * 0.24)
    gloss = np.clip(1 - (gx * gx + gy * gy), 0, 1) ** 1.6 * 0.30 * mask
    body = body + (255 - body) * gloss[..., None]
    return body


def layer(rgb, alpha):
    return np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255, 0, 255)]).astype(np.float32)


def over(dst, src):
    """src over dst, straight alpha float RGBA (0..255)."""
    sa, da = src[..., 3:4] / 255, dst[..., 3:4] / 255
    out_a = sa + da * (1 - sa)
    rgb = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(out_a, 1e-6)
    return np.dstack([rgb, out_a * 255])


def shadow_of(alpha, dx, dy, blur, strength):
    img = Image.fromarray((alpha * 255).astype(np.uint8))
    img = img.transform(img.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy)).filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(img, np.float32) / 255 * strength
    return layer(np.zeros(alpha.shape + (3,), np.float32), a)


def symbol_layers(w, h, mask, color):
    """The symbol: its color with a top-lit gradient, a dark drop shadow below it, a faint light edge above."""
    top = tuple(min(255, c * 1.18 + 20) for c in color)
    bottom = tuple(c * 0.72 for c in color)
    sym = layer(gradient(h, w, top, bottom), mask)
    return [shadow_of(mask, 0, SS * 0.7, SS * 0.5, 0.85), sym]


def face_button(kind, size=32):
    w = h = size * SS
    c, r = w / 2, w * 0.43
    disc = shape_mask(w, h, lambda d: d.ellipse([c - r, c - r, c + r, c + r], fill=255))
    inner = shape_mask(w, h, lambda d: d.ellipse([c - r * 0.88, c - r * 0.88, c + r * 0.88, c + r * 0.88], fill=255))
    img = shadow_of(disc, 0, SS * 1.1, SS * 1.2, 0.75)
    img = over(img, layer(button_body(w, h, disc, disc - inner), disc))
    s, lw = r * 0.48, int(r * 0.17)
    if kind == "cross":
        m = shape_mask(w, h, lambda d: (d.line([c - s, c - s, c + s, c + s], fill=255, width=lw),
                                        d.line([c - s, c + s, c + s, c - s], fill=255, width=lw)))
    elif kind == "circle":
        m = shape_mask(w, h, lambda d: d.ellipse([c - s, c - s, c + s, c + s], outline=255, width=lw))
    elif kind == "square":
        q = s * 0.9
        m = shape_mask(w, h, lambda d: d.rectangle([c - q, c - q, c + q, c + q], outline=255, width=lw))
    else:  # triangle
        t = s * 1.12
        pts = [(c, c - t), (c + t * 0.97, c + t * 0.62), (c - t * 0.97, c + t * 0.62)]
        m = shape_mask(w, h, lambda d: d.line(pts + [pts[0], pts[1]], fill=255, width=lw, joint="curve"))
    for part in symbol_layers(w, h, m, COLORS[kind]):
        img = over(img, part)
    return img


def label_font(size, condensed):
    if not condensed:
        return ImageFont.truetype(FONT, size)
    font = ImageFont.truetype(CONDENSED, size)
    font.set_variation_by_name("Bold Condensed")
    return font


def label_mask(w, h, text, box, size_ratio, condensed=False):
    """The label centered in box, as large as size_ratio of the canvas height allows and narrow enough to fit."""
    bx0, by0, bx1, by1 = box
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    size = int(h * size_ratio)
    while True:
        font = label_font(size, condensed)
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
        if x1 - x0 <= (bx1 - bx0) * 0.84 or size <= 8:
            break
        size -= 2
    d.text(((bx0 + bx1 - (x1 - x0)) / 2 - x0, (by0 + by1 - (y1 - y0)) / 2 - y0), text, font=font, fill=255)
    return np.asarray(m, np.float32) / 255


def pill_button(w_px, h_px, box, radius, text=None, lines=False, pad=False, condensed=False, text_ratio=None):
    w, h = w_px * SS, h_px * SS
    x0, y0, x1, y1 = (v * SS for v in box)
    rr = radius * SS
    body = shape_mask(w, h, lambda d: d.rounded_rectangle([x0, y0, x1, y1], radius=rr, fill=255))
    k = 1.2 * SS
    inner = shape_mask(w, h, lambda d: d.rounded_rectangle([x0 + k, y0 + k, x1 - k, y1 - k], radius=max(rr - k, 1),
                                                           fill=255))
    img = shadow_of(body, 0, SS * 1.0, SS * 1.1, 0.75)
    img = over(img, layer(button_body(w, h, body, body - inner), body))
    if text:
        ratio = text_ratio or (0.40 if h_px == 32 and w_px == 64 else 0.36)
        m = label_mask(w, h, text, (x0, y0, x1, y1), ratio, condensed)
        for part in symbol_layers(w, h, m, (236, 238, 244)):
            img = over(img, part)
    if lines:
        cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * 0.22
        lw = int(SS * 1.3)
        m = shape_mask(w, h, lambda d: [d.line([cx - half, cy + o, cx + half, cy + o], fill=255, width=lw)
                                        for o in (-3.2 * SS, 0, 3.2 * SS)])
        for part in symbol_layers(w, h, m, (236, 238, 244)):
            img = over(img, part)
    if pad:
        # The touch pad's surface: a faint inset rectangle and a light press dot.
        m = shape_mask(w, h, lambda d: d.rounded_rectangle([x0 + 3 * SS, y0 + 3 * SS, x1 - 3 * SS, y1 - 3 * SS],
                                                           radius=2 * SS, outline=255, width=int(SS * 0.9)))
        img = over(img, layer(np.full((h, w, 3), 150, np.float32), m * 0.55))
        cx, cy, rd = (x0 + x1) / 2, (y0 + y1) / 2, 2.6 * SS
        dot = shape_mask(w, h, lambda d: d.ellipse([cx - rd, cy - rd, cx + rd, cy + rd], fill=255))
        for part in symbol_layers(w, h, dot, (236, 238, 244)):
            img = over(img, part)
    return img


def downscale(img, w, h):
    """Premultiplied area downscaling (no dark fringes), back to straight alpha uint8 RGBA."""
    a = img[..., 3:4] / 255
    pre = np.dstack([img[..., :3] * a, img[..., 3:4]])
    out = np.zeros((h, w, 4), np.float32)
    fy, fx = img.shape[0] // h, img.shape[1] // w
    out = pre.reshape(h, fy, w, fx, 4).mean(axis=(1, 3))
    alpha = out[..., 3:4] / 255
    rgb = out[..., :3] / np.maximum(alpha, 1e-6)
    return np.clip(np.dstack([rgb, out[..., 3:4]]), 0, 255).round().astype(np.uint8)


def render(name, w, h):
    if name in COLORS:
        big = face_button(name, 32)
    elif name in ("l1", "r1"):
        big = pill_button(64, 32, (3, 5, 61, 26), 9, text=name.upper())
    elif name == "r2":
        big = pill_button(32, 32, (3, 3, 29, 28), 7, text="R2")
    elif name == "options":
        # The DualShock 4's OPTIONS button: a small dark pill with the word (the three lines are the DualSense's).
        big = pill_button(32, 32, (1, 9, 31, 23), 7, text="OPTIONS", condensed=True, text_ratio=0.30)
    else:  # touchpad
        big = pill_button(32, 32, (2, 6, 30, 25), 5, pad=True)
    return downscale(big, w, h)


def block_bytes(data, w, h):
    """The texture's blocks as stored (byte-swapped), in row-major block order: what the game hashes."""
    out = bytearray()
    for by in range(h // 4):
        for bx in range(w // 4):
            o = icons.tiled_offset_2d(bx, by, icons.PITCH_BLOCKS, 4)
            out += data[o:o + icons.BLOCK_BYTES]
    return bytes(out)


def fnv1a64(data):
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def main():
    dump_dir, inc_path, preview_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(preview_dir, exist_ok=True)
    entries, previews = [], []
    for fname, offset, w, h, name in XBOX:
        path = glob.glob(os.path.join(dump_dir, "**", fname), recursive=True)[0]
        dump = open(path, "rb").read()
        xbox = dump[offset:offset + icons.TEXTURE_BYTES].ljust(icons.TEXTURE_BYTES, b"\0")
        xbox_hash = fnv1a64(block_bytes(xbox, w, h))
        ps = render(name, w, h)
        Image.fromarray(ps, "RGBA").save(os.path.join(preview_dir, f"{name}_{w}x{h}.png"))
        ps_blocks = block_bytes(icons.encode(ps, w, h), w, h)
        entries.append((name, w, h, xbox_hash, ps_blocks))
        previews.append((name, icons.decode(icons.encode(ps, w, h), w, h)))
        print(f"{name:9s} {w}x{h} xbox hash {xbox_hash:016X}")
    with open(inc_path, "w", newline="\n") as f:
        f.write("// Generated by tools/ps_icons.py: the PlayStation button icons (DXT5 blocks as the game stores its icons:\n"
                "// byte-swapped, in row-major block order) and the FNV-1a hash of the Xbox icon each one replaces.\n\n")
        for name, w, h, _, blocks in entries:
            f.write(f"static const uint8_t kIcon_{name}[{len(blocks)}] = {{\n")
            for i in range(0, len(blocks), 24):
                f.write("    " + ", ".join(f"0x{b:02X}" for b in blocks[i:i + 24]) + ",\n")
            f.write("};\n\n")
        f.write("static const ReplacementIcon kIcons[] = {\n")
        for name, w, h, xbox_hash, _ in entries:
            f.write(f"    {{{w}, {h}, 0x{xbox_hash:016X}ull, kIcon_{name}, \"{name}\"}},\n")
        f.write("};\n")
    # A preview sheet: each icon as the game will decode it, 6x, on the game's dark UI grey and on a light grey.
    tiles = []
    for name, rgba in previews:
        for bgv in (28, 150):
            a = rgba[..., 3:4].astype(np.float32) / 255
            comp = (rgba[..., :3] * a + bgv * (1 - a)).astype(np.uint8)
            img = Image.fromarray(comp).resize((rgba.shape[1] * 6, rgba.shape[0] * 6), Image.NEAREST)
            tile = Image.new("RGB", (64 * 6 + 12, 32 * 6 + 12), (60, 60, 60))
            tile.paste(img, (6, 6))
            tiles.append(tile)
    cols = 6
    sheet = Image.new("RGB", (cols * tiles[0].width, -(-len(tiles) // cols) * tiles[0].height), (60, 60, 60))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * t.width, (i // cols) * t.height))
    sheet.save(os.path.join(preview_dir, "sheet.png"))


if __name__ == "__main__":
    main()
