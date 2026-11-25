"""Tomato/Tajima DST. Units 0.1 mm, y-up. Max 121 units (12.1 mm) per record.
Trim heuristic: DST has no trim opcode; machines use a run of tiny jumps. Reader treats each group of 3
consecutive jumps with |dx|,|dy|<=2 units as one TRIM; writer emits TRIM as 3 tiny jumps with net 0."""
import math

from .model import (Design, DesignError, Stitch, STITCH, JUMP, TRIM, COLOR_CHANGE, STOP, END)
from .edit import ensure_start_jump

MAX_STEP = 121
MAX_RECORDS = 5_000_000
# per trit position: byte index, (+bit, -bit) for x and y
_X = [(0, 0x01, 0x02), (1, 0x01, 0x02), (0, 0x04, 0x08), (1, 0x04, 0x08), (2, 0x04, 0x08)]
_Y = [(0, 0x80, 0x40), (1, 0x80, 0x40), (0, 0x20, 0x10), (1, 0x20, 0x10), (2, 0x20, 0x10)]


def encode_delta(dx, dy, flags):
    if abs(dx) > MAX_STEP or abs(dy) > MAX_STEP:
        raise DesignError("delta too large for one DST record")
    b = [0, 0, flags]
    for v, table in ((dx, _X), (dy, _Y)):
        for byte, plus, minus in table:
            d = ((v + 1) % 3) - 1
            v = (v - d) // 3
            if d == 1: b[byte] |= plus
            elif d == -1: b[byte] |= minus
    return bytes(b)


def decode_delta(b0, b1, b2):
    x = y = 0
    x += (1 if b0 & 0x01 else 0) - (1 if b0 & 0x02 else 0)
    x += 9 * ((1 if b0 & 0x04 else 0) - (1 if b0 & 0x08 else 0))
    y += (1 if b0 & 0x80 else 0) - (1 if b0 & 0x40 else 0)
    y += 9 * ((1 if b0 & 0x20 else 0) - (1 if b0 & 0x10 else 0))
    x += 3 * ((1 if b1 & 0x01 else 0) - (1 if b1 & 0x02 else 0))
    x += 27 * ((1 if b1 & 0x04 else 0) - (1 if b1 & 0x08 else 0))
    y += 3 * ((1 if b1 & 0x80 else 0) - (1 if b1 & 0x40 else 0))
    y += 27 * ((1 if b1 & 0x20 else 0) - (1 if b1 & 0x10 else 0))
    x += 81 * ((1 if b2 & 0x04 else 0) - (1 if b2 & 0x08 else 0))
    y += 81 * ((1 if b2 & 0x20 else 0) - (1 if b2 & 0x10 else 0))
    return x, y


def read_dst(data: bytes, name="") -> Design:
    if len(data) < 512 + 3:
        raise DesignError("File too small to be a DST design")
    header = data[:512].decode("latin-1")
    label = header[3:19].strip() if header.startswith("LA:") else ""
    body = data[512:]
    recs, i = [], 0
    n = len(body) // 3
    if n > MAX_RECORDS:
        raise DesignError("Too many records")
    ended = False
    while i < n:
        b0, b1, b2 = body[3 * i:3 * i + 3]
        i += 1
        if not (b2 & 0x03):
            raise DesignError(f"Invalid record flags at record {i}")
        if b2 & 0xF3 == 0xF3:
            ended = True; break
        dx, dy = decode_delta(b0, b1, b2)
        kind = "cc" if (b2 & 0xC0) == 0xC0 else "jump" if b2 & 0x80 else "stitch" if not (b2 & 0x40) else None
        if kind is None:
            raise DesignError(f"Unsupported record type at record {i}")
        recs.append((dx, dy, kind))
    out, x, y, k = [], 0, 0, 0
    small = lambda r: abs(r[0]) <= 2 and abs(r[1]) <= 2
    while k < len(recs):
        dx, dy, kind = recs[k]
        if kind == "jump" and k + 2 < len(recs) and all(r[2] == "jump" and small(r) for r in recs[k:k + 3]):
            for r in recs[k:k + 3]:
                x += r[0]; y += r[1]
            out.append(Stitch(x / 10, y / 10, TRIM)); k += 3; continue
        x += dx; y += dy
        out.append(Stitch(x / 10, y / 10, {"stitch": STITCH, "jump": JUMP, "cc": COLOR_CHANGE}[kind]))
        if abs(x) > 1_000_000 or abs(y) > 1_000_000:
            raise DesignError("Coordinate out of range")
        k += 1
    if not out:
        raise DesignError("Design contains no stitches")
    meta = {"label": label, "had_end_marker": ended}
    return Design(tuple(out), (), name or label or "design", "DST", meta)


def write_dst(d: Design):
    """Returns (bytes, warnings)."""
    warns, rec = [], []
    cx = cy = 0
    d0 = d; d = ensure_start_jump(d)
    if d is not d0: warns.append("Design did not start at origin; an explicit jump was added")
    for s in d.stitches:
        if s.cmd == END:
            continue
        if s.cmd in (TRIM, COLOR_CHANGE, STOP):
            if s.cmd == TRIM:
                for dx in (2, -1, -1):
                    rec.append(encode_delta(dx, 0, 0x83))
            else:
                rec.append(encode_delta(0, 0, 0xC3))
            continue
        tx, ty = round(s.x * 10), round(s.y * 10)
        dx, dy = tx - cx, ty - cy
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) / MAX_STEP))
        if steps > 1 and s.cmd == STITCH:
            warns.append("Stitches longer than 12.1 mm were split")
        px = py = 0
        for j in range(1, steps + 1):
            nx, ny = round(dx * j / steps), round(dy * j / steps)
            rec.append(encode_delta(nx - px, ny - py, 0x03 if s.cmd == STITCH else 0x83))
            px, py = nx, ny
        cx, cy = tx, ty
    rec.append(encode_delta(0, 0, 0xF3))
    xs = [round(s.x * 10) for s in d.stitches] or [0]
    ys = [round(s.y * 10) for s in d.stitches] or [0]
    cc = sum(1 for s in d.stitches if s.cmd == COLOR_CHANGE)
    h = (f"LA:{d.name[:16]:<16}\rST:{len(rec):7d}\rCO:{cc:3d}\r+X:{max(0,max(xs)):5d}\r-X:{max(0,-min(xs)):5d}\r"
         f"+Y:{max(0,max(ys)):5d}\r-Y:{max(0,-min(ys)):5d}\rAX:+{0:5d}\rAY:+{0:5d}\rMX:+{0:5d}\rMY:+{0:5d}\rPD:******\r\x1a")
    hb = h.encode("latin-1", "replace").ljust(512, b" ")
    warns = sorted(set(warns))
    if d.threads:
        warns.append("DST stores no thread colours; colours are not preserved")
    return hb + b"".join(rec), warns
