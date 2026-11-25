from dataclasses import dataclass
from .model import Design

__all__ = ["Hoop", "HOOP_PRESETS", "check_fit"]

@dataclass(frozen=True)
class Hoop:
    name: str
    width: float      # mm, full hoop inner size
    height: float
    margin: float = 5.0   # mm unusable band per side (machine/hoop specific; user-editable)

    def usable(self):
        return (max(0, self.width - 2 * self.margin), max(0, self.height - 2 * self.margin))

# Generic metric sizes only; real usable areas differ per machine, so margin is editable.
HOOP_PRESETS = [Hoop("100 x 100", 100, 100), Hoop("130 x 180", 130, 180), Hoop("160 x 260", 160, 260),
                Hoop("200 x 200", 200, 200), Hoop("200 x 300", 200, 300)]

def check_fit(d: Design, hoop: Hoop, hoop_center=(0.0, 0.0)):
    """Does the design (in its current coordinates) fit the usable area of a hoop centred at hoop_center?"""
    x0, y0, x1, y1 = d.bounds()
    uw, uh = hoop.usable()
    cx, cy = hoop_center
    L, R, B, T = cx - uw / 2, cx + uw / 2, cy - uh / 2, cy + uh / 2
    over = {"left": max(0, L - x0), "right": max(0, x1 - R), "bottom": max(0, B - y0), "top": max(0, y1 - T)}
    return {"fits": all(v < 1e-9 for v in over.values()), "overflow_mm": over,
            "margins_mm": {"left": x0 - L, "right": R - x1, "bottom": y0 - B, "top": T - y1}}
