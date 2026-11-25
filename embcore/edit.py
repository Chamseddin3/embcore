"""Pure edit operations: Design -> Design. Never mutate; original is preserved."""
import math

from .model import (Design, DesignError, Stitch, STITCH, JUMP, TRIM, COLOR_CHANGE, STOP, END, dist)

def _map(d, f): return d.with_stitches(Stitch(*f(s.x, s.y), s.cmd) for s in d.stitches)

def translate(d, dx, dy): return _map(d, lambda x, y: (x + dx, y + dy))
def center_at(d, cx=0.0, cy=0.0):
    c = d.center(); return translate(d, cx - c[0], cy - c[1])
def scale(d, sx, sy=None):
    sy = sx if sy is None else sy
    if sx <= 0 or sy <= 0: raise DesignError("Scale must be positive")
    c = d.center(); return _map(d, lambda x, y: (c[0] + (x - c[0]) * sx, c[1] + (y - c[1]) * sy))
def resize_to(d, width=None, height=None, lock_aspect=True):
    w, h = d.size()
    if w <= 0 or h <= 0: raise DesignError("Design has zero width or height")
    sx = width / w if width else None; sy = height / h if height else None
    if sx is None and sy is None: return d
    if lock_aspect: sx = sy = sx if sx is not None else sy
    return scale(d, sx or 1.0, sy or 1.0)
def rotate(d, degrees):
    a = math.radians(degrees); ca, sa = math.cos(a), math.sin(a); c = d.center()
    return _map(d, lambda x, y: (c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca))
def flip_h(d): c = d.center(); return _map(d, lambda x, y: (2 * c[0] - x, y))
def flip_v(d): c = d.center(); return _map(d, lambda x, y: (x, 2 * c[1] - y))

def limit_stitch_length(d, max_mm=12.1):
    """Split over-long STITCH/JUMP moves into equal parts (needed after upscaling)."""
    out, prev = [], None
    for s in d.stitches:
        if prev and s.cmd in (STITCH, JUMP):
            L = dist(s, prev)
            k = math.ceil(L / max_mm - 1e-9)
            for j in range(1, k):
                t = j / k; out.append(Stitch(prev.x + (s.x - prev.x) * t, prev.y + (s.y - prev.y) * t, s.cmd))
        out.append(s); prev = s
    return d.with_stitches(out)

# ---- spacing (NOT regeneration: only adds/removes points along existing paths) ----
def increase_density(d, max_spacing_mm):
    """Spacing modification: subdivide stitches longer than max_spacing_mm."""
    if max_spacing_mm <= 0: raise DesignError("Spacing must be positive")
    out, prev = [], None
    for s in d.stitches:
        if prev and s.cmd == STITCH:
            k = math.ceil(dist(s, prev) / max_spacing_mm - 1e-9)
            for j in range(1, k):
                t = j / k; out.append(Stitch(prev.x + (s.x - prev.x) * t, prev.y + (s.y - prev.y) * t, STITCH))
        out.append(s); prev = s
    return d.with_stitches(out)

def reduce_density(d, min_spacing_mm):
    """Spacing modification: drop stitches closer than min_spacing_mm to the previous kept stitch.
    Keeps the last stitch before any non-stitch command so run endpoints are preserved."""
    out, last = [], None
    s_list = d.stitches
    for i, s in enumerate(s_list):
        if s.cmd != STITCH: out.append(s); last = s; continue
        nxt = s_list[i + 1] if i + 1 < len(s_list) else None
        is_end = nxt is None or nxt.cmd != STITCH
        if last is None or is_end or dist(s, last) >= min_spacing_mm: out.append(s); last = s
    return d.with_stitches(out)

# ---- jumps / trims ----
def ensure_start_jump(d):
    """Machines start at (0,0). If the first stitch is elsewhere, make the approach an explicit JUMP."""
    s = d.stitches
    if s and s[0].cmd == STITCH and (abs(s[0].x) > 0.05 or abs(s[0].y) > 0.05):
        return d.with_stitches((Stitch(s[0].x, s[0].y, JUMP),) + tuple(s))
    return d

def find_jumps(d):
    res, prev = [], None
    for i, s in enumerate(d.stitches):
        if s.cmd == JUMP and prev: res.append((i, dist(s, prev)))
        prev = s
    return res

def convert_jumps_to_trims(d, min_len_mm):
    """Insert a TRIM before each jump >= min_len_mm that is not already preceded by one."""
    out, prev = [], None
    for s in d.stitches:
        if s.cmd == JUMP and prev and dist(s, prev) >= min_len_mm and prev.cmd != TRIM:
            out.append(Stitch(prev.x, prev.y, TRIM))
        out.append(s); prev = s
    return d.with_stitches(out)

def remove_short_jumps(d, max_len_mm=0.3):
    """Safe removal: only jumps shorter than max_len_mm become ordinary stitches (no visible connector)."""
    out, prev = [], None
    for s in d.stitches:
        if s.cmd == JUMP and prev and prev.cmd == STITCH and dist(s, prev) <= max_len_mm: s = Stitch(s.x, s.y, STITCH)
        out.append(s); prev = s
    return d.with_stitches(out)

def delete_range(d, start, end):
    """Delete stitches [start,end). Inserts a JUMP so the next stitch isn't connected by a thread."""
    if not (0 <= start < end <= len(d.stitches)): raise DesignError("Invalid range")
    out = list(d.stitches[:start]); rest = list(d.stitches[end:])
    if out and rest and rest[0].cmd == STITCH and dist(out[-1], rest[0]) > 1e-9:
        rest.insert(0, Stitch(rest[0].x, rest[0].y, JUMP))
    return d.with_stitches(out + rest)

# ---- colours ----
def _threads(d): return [d.thread_for(i) for i in range(d.block_count())]
def set_thread_color(d, block, hexv):
    import re
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hexv): raise DesignError("Invalid HEX colour")
    t = _threads(d)
    if not 0 <= block < len(t): raise DesignError("No such colour block")
    t[block] = hexv.upper(); return Design(d.stitches, tuple(t), d.name, d.source_format, d.metadata)
def merge_same_color_blocks(d):
    t, out, nt, blk = _threads(d), [], [], 0
    nt.append(t[0]) if t else None
    for s in d.stitches:
        if s.cmd == COLOR_CHANGE:
            blk += 1
            if t[blk].upper() == nt[-1].upper(): continue
            nt.append(t[blk])
        out.append(s)
    return Design(tuple(out), tuple(nt), d.name, d.source_format, d.metadata)
def reorder_blocks(d, order):
    bl = d.blocks(); t = _threads(d)
    if sorted(order) != list(range(len(bl))): raise DesignError("Order must be a permutation of blocks")
    out = []
    for k, bi in enumerate(order):
        b = [s for s in bl[bi] if s.cmd != END]
        if k > 0 and out:
            out.append(Stitch(out[-1].x, out[-1].y, COLOR_CHANGE))
            first = next((s for s in b if s.cmd in (STITCH, JUMP)), None)
            if first and first.cmd == STITCH and dist(first, out[-1]) > 1e-9:
                out.append(Stitch(first.x, first.y, JUMP))
        out += b
    return Design(tuple(out), tuple(t[i] for i in order), d.name, d.source_format, d.metadata)

# ---- analysis ----
def stats(d, spm=700, color_change_s=30):
    st = [s for s in d.stitches if s.cmd == STITCH]
    thread, prev = 0.0, None
    for s in d.stitches:
        if prev and s.cmd == STITCH: thread += dist(s, prev)
        prev = s
    w, h = d.size(); cc = sum(1 for s in d.stitches if s.cmd == COLOR_CHANGE)
    return {"stitches": len(st), "jumps": len(find_jumps(d)), "trims": sum(1 for s in d.stitches if s.cmd == TRIM),
            "stops": sum(1 for s in d.stitches if s.cmd == STOP), "color_changes": cc, "blocks": d.block_count(),
            "width_mm": w, "height_mm": h, "center_mm": d.center(),
            "est_thread_m": thread / 1000, "est_minutes": (len(st) / spm) + cc * color_change_s / 60,
            "estimates_note": f"estimates: {spm} stitches/min, {color_change_s}s per colour change"}
