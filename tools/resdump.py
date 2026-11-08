#!/usr/bin/env python3
"""Turns one frame's resolve dump (the live console's "dumpres", sdk vulkan/command_processor.cpp ResDumpWrite) into
images: each resolve untiled (the Xenos 2D tiling, texture_util GetTiledOffset2D), endian-swapped back and decoded,
written as a PNG beside a contact sheet in resolve order.

  py tools/resdump.py --host <PS4 IP> /data/MP3/dumps/frame_N <local dir>    fetch the dump over FTP, then decode
  py tools/resdump.py <local dir>                                           decode a dump already fetched

HDR formats are shown tonemapped (x / (1 + x)) after the game's own scale (the resolve's exponent bias undone), float
and depth ones normalised to their range; the PNG names keep the index, address and format.
"""
import argparse
import ftplib
import os
import re
import sys

import cv2
import numpy as np

# Xenos texture formats (xenos.h TextureFormat): bytes per pixel and a decoder name.
FORMATS = {
    2: (1, "u8x1"),      # k_8
    6: (4, "u8x4"),      # k_8_8_8_8
    7: (4, "u2101010"),  # k_2_10_10_10
    10: (2, "u8x2"),     # k_8_8
    24: (2, "u16x1"),    # k_16
    25: (4, "u16x2"),    # k_16_16
    26: (8, "u16x4"),    # k_16_16_16_16
    30: (2, "f16x1"),    # k_16_FLOAT
    31: (4, "f16x2"),    # k_16_16_FLOAT
    32: (8, "f16x4"),    # k_16_16_16_16_FLOAT
    36: (4, "f32x1"),    # k_32_FLOAT
    37: (8, "f32x2"),    # k_32_32_FLOAT
    38: (16, "f32x4"),   # k_32_32_32_32_FLOAT
}


def tiled_offset_2d(x, y, pitch, bpb_log2):
    """GetTiledOffset2D (sdk/src/graphics/pipeline/texture/util.cpp), vectorised over x and y."""
    pitch = (pitch + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (bpb_log2 + 7)
    micro = ((x & 7) + ((y & 0xE) << 2)) << bpb_log2
    offset = macro + ((micro & ~0xF) << 1) + (micro & 0xF) + ((y & 1) << 4)
    return ((offset & ~0x1FF) << 3) + ((y & 16) << 7) + ((offset & 0x1C0) << 2) + \
        (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 0x3F)


def endian_swap(data, endian):
    """Endian128: 0 none, 1 8in16, 2 8in32, 3 16in32, 4 8in64, 5 8in128."""
    a = np.frombuffer(data, dtype=np.uint8)
    n = {1: 2, 2: 4, 4: 8, 5: 16}.get(endian)
    if n:
        a = a[: len(a) // n * n].reshape(-1, n)[:, ::-1].reshape(-1)
    elif endian == 3:
        a = a[: len(a) // 4 * 4].reshape(-1, 2, 2)[:, ::-1, :].reshape(-1)
    return a.tobytes()


def untile(data, w, h, bpp):
    bpb_log2 = int(bpp).bit_length() - 1
    ys, xs = np.mgrid[0:h, 0:w].astype(np.int64)
    offsets = tiled_offset_2d(xs, ys, w, bpb_log2)
    raw = np.frombuffer(data, dtype=np.uint8)
    need = int(offsets.max()) + bpp
    if len(raw) < need:
        raw = np.concatenate([raw, np.zeros(need - len(raw), np.uint8)])
    idx = offsets[..., None] + np.arange(bpp)
    return raw[idx].reshape(h, w, bpp)


def to_image(px, kind, entry):
    """A displayable 8-bit BGR image and a short value summary."""
    h, w, bpp = px.shape
    flat = px.reshape(h, w * bpp).copy()
    if kind == "u8x4":
        img = px[..., :3][..., ::-1] if entry["source"].startswith("depth") is False else px[..., :3]
        if entry["source"].startswith("depth"):
            d = (px[..., 0].astype(np.uint32) | (px[..., 1].astype(np.uint32) << 8) | (px[..., 2].astype(np.uint32) << 16))
            v = d.astype(np.float64)
            lo, hi = np.percentile(v, 1), np.percentile(v, 99)
            g = np.clip((v - lo) / max(hi - lo, 1), 0, 1)
            return (np.stack([g] * 3, -1) * 255).astype(np.uint8), f"depth24 {lo:.0f}..{hi:.0f}"
        return np.ascontiguousarray(px[..., [0, 1, 2]]), f"8888 mean {px[..., :3].mean():.1f}"
    if kind in ("u8x1", "u8x2"):
        g = px[..., 0]
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), f"8bit mean {g.mean():.1f}"
    if kind.startswith("u16"):
        comps = int(kind[-1])
        v = flat.view(np.uint16).reshape(h, w, comps).astype(np.float64)
        scale = 2.0 ** -11 if entry["number"] == 2 else 1.0 / 65535.0
        c = v * scale
        if comps == 1:
            c = np.repeat(c, 3, -1)
        rgb = c[..., :3]
        disp = rgb / (1.0 + rgb)
        return (disp[..., ::-1] * 255).astype(np.uint8), f"u16 raw max {v.max():.0f} mean {v.mean():.1f} (x2^-11: max {c.max():.3f})"
    if kind.startswith("f16") or kind.startswith("f32"):
        comps = int(kind[-1])
        dt = np.float16 if kind.startswith("f16") else np.float32
        v = flat.view(dt).reshape(h, w, comps).astype(np.float64)
        v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
        lo, hi = np.percentile(v, 1), np.percentile(v, 99)
        g = np.clip((v - lo) / max(hi - lo, 1e-9), 0, 1)
        if comps == 1:
            g = np.repeat(g, 3, -1)
        elif comps == 2:
            g = np.concatenate([g, np.zeros_like(g[..., :1])], -1)
        return (g[..., :3][..., ::-1] * 255).astype(np.uint8), f"float {v.min():.3g}..{v.max():.3g} mean {v.mean():.3g}"
    if kind == "u2101010":
        d = flat.view(np.uint32).reshape(h, w)
        r, g, b = d & 0x3FF, (d >> 10) & 0x3FF, (d >> 20) & 0x3FF
        return (np.stack([b, g, r], -1) / 4).astype(np.uint8), "2_10_10_10"
    return np.zeros((h, w, 3), np.uint8), "?"


def fetch(host, remote, local):
    os.makedirs(local, exist_ok=True)
    f = ftplib.FTP()
    f.connect(host, 2121, timeout=60)
    f.login()
    f.voidcmd("TYPE I")
    f.cwd(remote)
    names = []
    f.retrlines("NLST", names.append)
    for name in names:
        name = name.rsplit("/", 1)[-1]
        if name in (".", ".."):
            continue
        with open(os.path.join(local, name), "wb") as fh:
            f.retrbinary("RETR " + name, fh.write)
    f.quit()
    print(f"{len(names)} files from {remote}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    if a.host:
        remote, local = a.paths[0], a.paths[1]
        fetch(a.host, remote, local)
    else:
        local = a.paths[0]
    entries = []
    for line in open(os.path.join(local, "index.txt"), encoding="utf-8", errors="replace"):
        parts = line.split()
        if not parts:
            continue
        e = {"file": parts[0]}
        for kv in parts[1:]:
            k, _, v = kv.partition("=")
            e[k] = v
        for k in ("length", "format_id", "pitch", "height", "endian", "number", "msaa"):
            e[k] = int(e.get(k, "0"))
        e["exp_bias"] = int(e.get("exp_bias", "0"))
        entries.append(e)
    out = os.path.join(local, "png")
    os.makedirs(out, exist_ok=True)
    tiles = []
    for e in entries:
        fmt = FORMATS.get(e["format_id"])
        path = os.path.join(local, e["file"])
        if not fmt or not os.path.exists(path):
            print(f"{e['file']}: format {e['format']} not decoded")
            continue
        bpp, kind = fmt
        data = endian_swap(open(path, "rb").read(), e["endian"])
        w, h = max(e["pitch"], 1), max(e["height"], 1)
        img, summary = to_image(untile(data, w, h, bpp), kind, e)
        name = os.path.splitext(e["file"])[0] + ".png"
        cv2.imwrite(os.path.join(out, name), img)
        print(f"{e['file']}: {e['source']} -> {e['format']} {w}x{h} number{e['number']} bias{e['exp_bias']}: {summary}")
        t = cv2.resize(img, (320, 180), interpolation=cv2.INTER_AREA)
        cv2.putText(t, f"{e['file'][:4]} {e['format'][2:14]} {w}x{h}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 255, 255), 1)
        tiles.append(t)
    cols = 5
    rows = [np.hstack(tiles[i:i + cols] + [np.zeros_like(tiles[0])] * (cols - len(tiles[i:i + cols])))
            for i in range(0, len(tiles), cols)]
    for k in range(0, len(rows), 4):
        cv2.imwrite(os.path.join(out, f"sheet_{k // 4}.jpg"), np.vstack(rows[k:k + 4]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("sheets in", out)


if __name__ == "__main__":
    sys.exit(main())
