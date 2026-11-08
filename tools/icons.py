#!/usr/bin/env python3
"""Max Payne 3's button icons: small DXT5 (k_DXT4_5) textures, Xenos-tiled, 8-in-16 byte order, 16 KB each (a 32x32
or 64x32 icon padded to the 32-block tiled pitch). Decodes them from a memory dump (the live console's "memdump") to
PNGs, and encodes a replacement PNG back into the same layout.

  py tools/icons.py decode <dump.bin> <dump base hex> <texture address hex> <w> <h> <out.png>
  py tools/icons.py encode <in.png> <w> <h> <out.bin>          (16 KB, ready to copy over the guest texture)
"""
import sys

import cv2
import numpy as np

PITCH_BLOCKS = 32  # tiled textures: rows aligned to 32 blocks
BLOCK_BYTES = 16   # DXT5
TEXTURE_BYTES = 16384


def tiled_offset_2d(x, y, pitch, bpb_log2):
    """GetTiledOffset2D (sdk texture util), in blocks."""
    pitch = (pitch + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (bpb_log2 + 7)
    micro = ((x & 7) + ((y & 0xE) << 2)) << bpb_log2
    offset = macro + ((micro & ~0xF) << 1) + (micro & 0xF) + ((y & 1) << 4)
    return (((offset & ~0x1FF) << 3) + ((y & 16) << 7) + ((offset & 0x1C0) << 2) +
            (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 0x3F))


def swap16(block):
    a = np.frombuffer(block, dtype=np.uint8).reshape(-1, 2)[:, ::-1]
    return a.reshape(-1).tobytes()


def rgb565(c):
    return np.array([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], np.int32)


def decode_dxt5_block(b):
    a0, a1 = b[0], b[1]
    alpha_bits = int.from_bytes(b[2:8], "little")
    alphas = [a0, a1]
    if a0 > a1:
        alphas += [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
    else:
        alphas += [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255]
    c0 = int.from_bytes(b[8:10], "little")
    c1 = int.from_bytes(b[10:12], "little")
    p0, p1 = rgb565(c0), rgb565(c1)
    colors = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
    bits = int.from_bytes(b[12:16], "little")
    out = np.zeros((4, 4, 4), np.uint8)
    for i in range(16):
        out[i // 4, i % 4, :3] = colors[(bits >> (2 * i)) & 3]
        out[i // 4, i % 4, 3] = alphas[(alpha_bits >> (3 * i)) & 7]
    return out


def encode_dxt5_block(px):
    """px: 4x4x4 RGBA uint8. Endpoints from the color range, a plain fit (icons are flat colors)."""
    rgba = px.reshape(16, 4).astype(np.int32)
    a = rgba[:, 3]
    a0, a1 = int(a.max()), int(a.min())
    if a0 == a1:
        alpha_idx = [0] * 16
    else:
        levels = [a0, a1] + [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
        alpha_idx = [int(np.argmin([abs(v - l) for l in levels])) for v in a]
    alpha_bits = 0
    for i, idx in enumerate(alpha_idx):
        alpha_bits |= idx << (3 * i)
    rgb = rgba[:, :3]
    visible = a > 16
    opaque = rgb[visible] if visible.any() else rgb
    to565 = lambda c: (((int(round(c[0])) * 31 + 127) // 255) << 11) | \
        (((int(round(c[1])) * 63 + 127) // 255) << 5) | ((int(round(c[2])) * 31 + 127) // 255)
    # Endpoints along the visible colors' principal axis, then refined by least squares on the chosen indices (shaded
    # icons have gradients inside a block; DXT5's color block is always the four-color mode).
    pts = opaque.astype(np.float64)
    mean = pts.mean(axis=0)
    if len(pts) > 1 and np.ptp(pts, axis=0).max() > 0:
        _, _, vt = np.linalg.svd(pts - mean, full_matrices=False)
        proj = (pts - mean) @ vt[0]
        hi, lo = mean + vt[0] * proj.max(), mean + vt[0] * proj.min()
    else:
        hi = lo = mean
    weights = np.array([[1, 0], [0, 1], [2 / 3, 1 / 3], [1 / 3, 2 / 3]])
    perceptual = np.array([0.30, 0.59, 0.11]) * 3  # error weights: green counts most, blue least

    def block_error(e0, e1):
        q0, q1 = rgb565(to565(np.clip(e0, 0, 255))), rgb565(to565(np.clip(e1, 0, 255)))
        palette = np.array([q0, q1, (2 * q0 + q1) / 3, (q0 + 2 * q1) / 3])
        err = (((pts[:, None, :] - palette[None, :, :]) ** 2) * perceptual).sum(axis=2)
        return err.min(axis=1).sum(), err.argmin(axis=1)

    def refine(e0, e1):
        for _ in range(3):
            _, chosen = block_error(e0, e1)
            wts = weights[chosen]
            m = wts.T @ wts
            if abs(np.linalg.det(m)) < 1e-9:
                break
            sol = np.linalg.solve(m, wts.T @ pts)
            e0, e1 = sol[0], sol[1]
        return e0, e1

    # Candidates: the principal-axis fit, and every pair of the block's own colors (rim, body and a symbol color
    # meet in some blocks), each refined; the lowest perceptual error wins.
    candidates = [refine(hi, lo)]
    uniq = np.unique(pts, axis=0)
    if len(uniq) <= 16:
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                candidates.append((uniq[i], uniq[j]))
                candidates.append(refine(uniq[i], uniq[j]))
    hi, lo = min(candidates, key=lambda e: block_error(e[0], e[1])[0])
    c0, c1 = to565(np.clip(hi, 0, 255)), to565(np.clip(lo, 0, 255))
    if c0 == c1:
        idx = [0] * 16
    else:
        p0, p1 = rgb565(c0), rgb565(c1)
        palette = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
        idx = [int(np.argmin([int(((c - p) ** 2).sum()) for p in palette])) for c in rgb]
    bits = 0
    for i, k in enumerate(idx):
        bits |= k << (2 * i)
    return (bytes([a0, a1]) + alpha_bits.to_bytes(6, "little") + c0.to_bytes(2, "little") + c1.to_bytes(2, "little") +
            bits.to_bytes(4, "little"))


def decode(data, w, h):
    img = np.zeros((h, w, 4), np.uint8)
    for by in range(h // 4):
        for bx in range(w // 4):
            o = tiled_offset_2d(bx, by, PITCH_BLOCKS, 4)
            block = swap16(data[o:o + BLOCK_BYTES])
            img[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4] = decode_dxt5_block(block)
    return img


def encode(img, w, h):
    out = bytearray(TEXTURE_BYTES)
    for by in range(h // 4):
        for bx in range(w // 4):
            o = tiled_offset_2d(bx, by, PITCH_BLOCKS, 4)
            out[o:o + BLOCK_BYTES] = swap16(encode_dxt5_block(img[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4]))
    return bytes(out)


if __name__ == "__main__":
    if sys.argv[1] == "decode":
        dump = open(sys.argv[2], "rb").read()
        base, address = int(sys.argv[3], 16), int(sys.argv[4], 16)
        w, h = int(sys.argv[5]), int(sys.argv[6])
        rgba = decode(dump[address - base:address - base + TEXTURE_BYTES], w, h)
        cv2.imwrite(sys.argv[7], cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    elif sys.argv[1] == "encode":
        rgba = cv2.cvtColor(cv2.imread(sys.argv[2], cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA)
        w, h = int(sys.argv[3]), int(sys.argv[4])
        open(sys.argv[5], "wb").write(encode(rgba[:h, :w], w, h))
