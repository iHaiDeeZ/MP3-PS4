#!/usr/bin/env python3
"""Functions reached only through pointers that the codegen's discovery missed (mp3-nx's runs 3 and 14, done ahead).

  scan_missed_functions.py <image.bin> <generated/default/mp3_init.cpp> [codegen/mp3_config.toml ...]

Two shapes, both where no known function starts, right after a blr, bctr or b (the end of the previous function):
  1. a code address another function builds with lis + addi/ori (a callback or vtable it registers); one built inside
     its own function is a label (an exception handler, a jump target) and is left alone, as mp3-nx did;
  2. a vtable thunk: lwz rX,N(r3), then mtctr rX and bctr within five instructions.
Prints TOML lines for codegen/mp3_config.toml [functions].
"""
import re
import struct
import sys

BASE = 0x82000000
img = open(sys.argv[1], "rb").read()
known = {int(a, 16) for a in re.findall(r"\{ 0x([0-9A-F]{8}), ", open(sys.argv[2]).read())}
# [extra.toml ...]: entries not in the generated code yet (a scan's earlier rounds) count as known, so a data table
# found next to them is seen too; run it again until it finds nothing.
for extra in sys.argv[3:]:
    known |= {int(a, 16) for a in re.findall(r'^"0x([0-9A-Fa-f]{8})"', open(extra).read(), re.M)}
lo, hi = min(known), max(known)
starts = sorted(known)


def owner(addr):
    import bisect
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else None
words = struct.unpack(f">{len(img) // 4}I", img[: len(img) // 4 * 4])


def w(addr):
    i = (addr - BASE) // 4
    return words[i] if 0 <= i < len(words) else 0


def ends_function(addr):
    p = w(addr - 4)
    return p in (0x4E800020, 0x4E800420) or (p >> 26) == 18 and (p & 3) == 0  # blr, bctr, b


found = {}
# 1. lis rX,hi ; addi/ori rY,rX,lo within 8 instructions.
for i, v in enumerate(words):
    if (v >> 26) != 15 or ((v >> 16) & 31) != 0:
        continue
    rt, hi16 = (v >> 21) & 31, v & 0xFFFF
    for j in range(1, 9):
        u = words[i + j] if i + j < len(words) else 0
        op = u >> 26
        if op in (14, 24) and ((u >> 16) & 31) == rt if op == 14 else ((u >> 21) & 31) == rt:
            low = u & 0xFFFF
            target = ((hi16 << 16) + (low - 0x10000 if op == 14 and low & 0x8000 else low)) & 0xFFFFFFFF
            if lo <= target <= hi and target % 4 == 0 and target not in known and ends_function(target)                     and owner(target) != owner(BASE + 4 * i):  # a label of the builder's own function: left alone
                found.setdefault(target, f"address built at {BASE + 4 * i:08X}")
            break
# 2. vtable thunks.
for addr in range(lo, hi, 4):
    if addr in known or not ends_function(addr):
        continue
    v = w(addr)
    if (v >> 26) == 32 and ((v >> 16) & 31) == 3:  # lwz rX, N(r3)
        rx = (v >> 21) & 31
        for k in range(1, 6):
            u = w(addr + 4 * k)
            if (u >> 26) == 32 and ((u >> 16) & 31) == rx:  # lwz rY, N(rX): the vtable, then its slot
                rx = (u >> 21) & 31
                continue
            if u == (0x7C0903A6 | (rx << 21)):  # mtctr rX
                if any(w(addr + 4 * m) == 0x4E800420 for m in range(k + 1, 6)):
                    found.setdefault(addr, "vtable thunk")
                break
# 3. code addresses stored in the data sections: vtables (with their this-adjusting thunks, addi r3,r3,-N ; b), the
#    C runtime's initializer tables (v00.01's first run: 7 static constructors at 0x830A4148... skipped), callback
#    tables. A switch's jump table holds labels too, so a target counts only when a word next to it in the same table
#    is a known function, or the table is one the C runtime walks (CRT_TABLES).
#    An exception handler's funclet (catch block, filter, unwind) is pointed at by its scope table too, but it runs on
#    its parent's frame (r31 read before it is set) and stays a label of the parent, as in mp3-nx: left out.
CODE_END = 0x830EF8F4  # "Function table initialized for module: code=821E0000-830EF8F4"


def funclet(addr):
    for k in range(16):
        u = w(addr + 4 * k)
        op, rt, ra = u >> 26, (u >> 21) & 31, (u >> 16) & 31
        d_form = op in (14, 32, 34, 36, 38, 40, 44, 48, 50, 52, 54, 58, 62)  # addi, lwz/lbz/stw/stb/lhz/sth/lfs/lfd/stfs/stfd, ld/std
        if (d_form or op == 31) and ra == 31:
            return True
        if op == 31 and ((u >> 11) & 31) == 31:  # rB = r31 (mr rX,r31, lwzx ...)
            return True
        if rt == 31 and (op in (14, 15, 24, 25, 32) or op == 31):  # r31 written first: an ordinary function
            return False
        if u in (0x4E800020, 0x4E800420) or (op == 18 and not u & 1):  # blr, bctr, b (a bl goes on)
            return False
    return False


CRT_TABLES = [(0x830F5C10, 0x830FB614)]  # walked at 0x821E1AEC (lwz, skip 0 and -1, bctrl)
for i, v in enumerate(words):
    at = BASE + 4 * i
    if lo <= at < CODE_END or not (lo <= v <= hi) or v % 4 or v in known or not ends_function(v) or funclet(v):
        continue
    in_crt = any(a <= at < b for a, b in CRT_TABLES)
    if in_crt or any(w(at + 4 * d) in known for d in (-2, -1, 1, 2)):
        found.setdefault(v, f"{'initializer table' if in_crt else 'pointer in data'} at {at:08X}")
# 4. shape 1 with the lis anywhere earlier in the same function: the compiler hoists a run of lis to the top of a
#    function that fills a table of handlers (v00.02's crash: 0x824A9FA0, built at 0x824ABD20 from a lis 70
#    instructions up, stored at +0x178 of an object, called by a message dispatcher). Registers are followed in
#    order (no branches): a write to a register forgets it; a call forgets the volatile ones; a known function start
#    forgets all.
DEST_RT = {7, 8, 12, 13, 14, 15, 32, 33, 34, 35, 40, 41, 42, 43, 46, 58}  # mulli subfic addic(.) addi addis, loads
DEST_RA = {20, 21, 23, 24, 25, 26, 27, 28, 29, 30}  # rlwimi rlwinm rlwnm ori oris xori xoris andi. andis. rld*
his = {}
for i, v in enumerate(words):
    at = BASE + 4 * i
    if not (lo <= at < CODE_END):
        continue
    if at in known:
        his.clear()
    op, rt, ra = v >> 26, (v >> 21) & 31, (v >> 16) & 31
    if op == 15 and ra == 0:  # lis rt, hi
        his[rt] = (v & 0xFFFF, at)
        continue
    if op in (14, 24) and (ra if op == 14 else rt) in his:  # addi rY,rX,lo / ori rY,rX,lo
        hi16, lis_at = his[ra if op == 14 else rt]
        low = v & 0xFFFF
        target = ((hi16 << 16) + (low - 0x10000 if op == 14 and low & 0x8000 else low)) & 0xFFFFFFFF
        if (lo <= target <= hi and target % 4 == 0 and target not in known and ends_function(target)
                and owner(target) != owner(at) and not funclet(target)):
            found.setdefault(target, f"address built at {at:08X} (lis at {lis_at:08X})")
    if op in DEST_RT:
        his.pop(rt, None)
    elif op in DEST_RA:
        his.pop(ra, None)
    elif op == 31:
        his.pop(rt, None)
        his.pop(ra, None)
    elif op == 18 and v & 1:  # bl: r0, r3-r12 are the callee's
        for r in (0, *range(3, 13)):
            his.pop(r, None)
for a in sorted(found):
    print(f'"0x{a:08X}" = {{}}   # {found[a]}')
print(f"# {len(found)} found", file=sys.stderr)
