from collections import namedtuple
from dataclasses import dataclass, field, replace
import math

__all__ = ["STITCH", "JUMP", "TRIM", "COLOR_CHANGE", "STOP", "END", "CMD_NAMES", "Stitch",
           "DEFAULT_PALETTE", "DesignError", "Design", "dist", "validate"]

STITCH, JUMP, TRIM, COLOR_CHANGE, STOP, END = range(6)
CMD_NAMES = ["stitch", "jump", "trim", "color_change", "stop", "end"]
Stitch = namedtuple("Stitch", "x y cmd")  # x,y in mm
DEFAULT_PALETTE = ["#1E88E5", "#E53935", "#43A047", "#FDD835", "#8E24AA", "#FB8C00", "#00ACC1", "#6D4C41"]


class DesignError(Exception):
    """Raised for invalid, corrupt or unsupported input."""


@dataclass(frozen=True)
class Design:
    stitches: tuple = ()
    threads: tuple = ()          # hex strings, one per color block (may be shorter; see thread_for)
    name: str = "untitled"
    source_format: str = ""
    metadata: dict = field(default_factory=dict)

    def with_stitches(self, s):
        return replace(self, stitches=tuple(s))

    def thread_for(self, block):
        return self.threads[block] if block < len(self.threads) else DEFAULT_PALETTE[block % len(DEFAULT_PALETTE)]

    def bounds(self):
        pts = [(s.x, s.y) for s in self.stitches]
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        xs, ys = zip(*pts)
        return (min(xs), min(ys), max(xs), max(ys))

    def size(self):
        a, b, c, d = self.bounds()
        return (c - a, d - b)

    def center(self):
        a, b, c, d = self.bounds()
        return ((a + c) / 2, (b + d) / 2)

    def block_count(self):
        return 1 + sum(1 for s in self.stitches if s.cmd == COLOR_CHANGE) if self.stitches else 0

    def blocks(self):
        """List of lists of stitches, split at COLOR_CHANGE (separators excluded)."""
        out, cur = [], []
        for s in self.stitches:
            if s.cmd == COLOR_CHANGE:
                out.append(cur); cur = []
            else:
                cur.append(s)
        out.append(cur)
        return out


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def validate(d, max_stitch_mm=None, max_coord_mm=2000.0):
    """Return list of human-readable issues (empty = OK)."""
    issues = []
    prev = None
    for i, s in enumerate(d.stitches):
        if not (math.isfinite(s.x) and math.isfinite(s.y)):
            issues.append(f"#{i}: non-finite coordinate"); break
        if abs(s.x) > max_coord_mm or abs(s.y) > max_coord_mm:
            issues.append(f"#{i}: coordinate out of range"); break
        if s.cmd not in (STITCH, JUMP, TRIM, COLOR_CHANGE, STOP):
            issues.append(f"#{i}: invalid command {s.cmd}"); break
        if max_stitch_mm and prev and s.cmd == STITCH and dist(s, prev) > max_stitch_mm + 1e-9:
            issues.append(f"#{i}: stitch {dist(s, prev):.1f} mm exceeds {max_stitch_mm} mm")
        prev = s
    return issues
