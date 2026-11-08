#!/usr/bin/env python3
"""Disassemble the dumped Max Payne 3 image (tools/codegen.sh's image.bin, loaded at 0x82000000).

  dis.py <image.bin> <hex address> [instructions]       PowerPC (Xenon) big-endian, capstone
  dis.py <image.bin> --find-u32 <hex value>             addresses of a big-endian word
  dis.py <image.bin> --find-f32 <float>                 addresses of a big-endian float
"""
import struct
import sys

import capstone

BASE = 0x82000000
img = open(sys.argv[1], "rb").read()

if sys.argv[2] == "--find-u32":
    pat = struct.pack(">I", int(sys.argv[3], 16))
elif sys.argv[2] == "--find-f32":
    pat = struct.pack(">f", float(sys.argv[3]))
else:
    pat = None
if pat is not None:
    i = img.find(pat)
    while i >= 0:
        if i % 4 == 0:
            print(f"{BASE + i:08X}")
        i = img.find(pat, i + 1)
    sys.exit(0)

addr = int(sys.argv[2], 16)
count = int(sys.argv[3]) if len(sys.argv) > 3 else 40
md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
off = addr - BASE
for n in range(count):
    word = img[off + 4 * n: off + 4 * n + 4]
    ins = next(md.disasm(word, addr + 4 * n), None)
    text = f"{ins.mnemonic} {ins.op_str}" if ins else f".long 0x{word.hex()}"
    print(f"{addr + 4 * n:08X}  {word.hex()}  {text}")
