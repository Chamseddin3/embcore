"""Melco EXP. Units 0.1 mm. Plain: 2 signed bytes (dx,dy). Commands: 0x80 + opcode, then 2 bytes.
Opcodes used: 0x01 colour change, 0x04 (and 0x02) jump, 0x80 trim. y orientation assumed y-up like DST.
STATUS: implemented from documented convention; NOT verified against real machine files in this environment."""
import math

from .model import (Design, DesignError, Stitch, STITCH, JUMP, TRIM, COLOR_CHANGE, STOP, END)
from .edit import ensure_start_jump

MAX_STEP = 127

def _s8(b): return b - 256 if b > 127 else b

def read_exp(data: bytes, name="") -> Design:
    if len(data) < 2:
        raise DesignError("File too small to be an EXP design")
    out, x, y, i, n = [], 0, 0, 0, len(data)
    while i < n:
        b0 = data[i]
        if b0 == 0x80:
            if i + 1 >= n: break
            op = data[i + 1]
            if op == 0x01:
                out.append(Stitch(x / 10, y / 10, COLOR_CHANGE)); i += 4
            elif op in (0x02, 0x04):
                if i + 3 >= n: raise DesignError("Truncated EXP jump record")
                x += _s8(data[i + 2]); y += _s8(data[i + 3]); out.append(Stitch(x / 10, y / 10, JUMP)); i += 4
            elif op == 0x80:
                out.append(Stitch(x / 10, y / 10, TRIM)); i += 4
            elif op == 0x10:
                break
            else:
                raise DesignError(f"Unknown EXP opcode 0x{op:02X} at byte {i}")
        else:
            if i + 1 >= n: raise DesignError("Truncated EXP stitch record")
            x += _s8(data[i]); y += _s8(data[i + 1]); out.append(Stitch(x / 10, y / 10, STITCH)); i += 2
        if abs(x) > 1_000_000 or abs(y) > 1_000_000:
            raise DesignError("Coordinate out of range")
    if not out:
        raise DesignError("Design contains no stitches")
    return Design(tuple(out), (), name or "design", "EXP", {})

def write_exp(d: Design):
    warns, b, cx, cy = [], bytearray(), 0, 0
    d0 = d; d = ensure_start_jump(d)
    if d is not d0: warns.append("Design did not start at origin; an explicit jump was added")
    sb = lambda v: v & 0xFF
    for s in d.stitches:
        if s.cmd == END: continue
        if s.cmd == COLOR_CHANGE or s.cmd == STOP: b += b"\x80\x01\x00\x00"; continue
        if s.cmd == TRIM: b += b"\x80\x80\x00\x00"; continue
        tx, ty = round(s.x * 10), round(s.y * 10)
        dx, dy = tx - cx, ty - cy
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) / MAX_STEP))
        if steps > 1 and s.cmd == STITCH: warns.append("Stitches longer than 12.7 mm were split")
        px = py = 0
        for j in range(1, steps + 1):
            nx, ny = round(dx * j / steps), round(dy * j / steps)
            if s.cmd == JUMP: b += bytes([0x80, 0x04])
            b += bytes([sb(nx - px), sb(ny - py)]); px, py = nx, ny
        cx, cy = tx, ty
    if d.threads: warns.append("EXP stores no thread colours; colours are not preserved")
    return bytes(b), sorted(set(warns))
