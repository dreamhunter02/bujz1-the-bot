"""Generate Bujji's eye animations as 284x126 GIFs.

Bujji (BU-JZ1) has angular red visor slits, not organic eyes. Each emotion is
a different slit geometry: the inner-edge angle carries most of the feeling,
the way it does on the film's droid. Resting face slants down toward the
centre, which reads as focused and faintly unimpressed.

Output filenames match the stock esp-brookesia emotion assets so they drop
straight into core/brookesia_core/systems/speaker/assets/animations/emotion/.

    .venv/bin/python eyes/make_eyes.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 284, 126
OUT = Path(__file__).parent / "gif"

CORE = (255, 90, 65)     # hot centre, slightly orange like a hot LED
EDGE = (225, 25, 15)     # saturated red body
BG = (0, 0, 0)

EYE_W = 96
GAP = 30
CY = H // 2
LCX = W // 2 - GAP // 2 - EYE_W // 2
RCX = W // 2 + GAP // 2 + EYE_W // 2


def slit(d: ImageDraw.ImageDraw, cx: int, mirror: bool, *,
         inner_h: int, outer_h: int, y_off: int = 0, fill=EDGE) -> None:
    """One angular slit.

    inner_h/outer_h are half-heights at the inner and outer edge. inner<outer
    slants down toward the face centre (stern); inner>outer slants up (worried).
    """
    half = EYE_W // 2
    sign = -1 if mirror else 1          # inner edge faces the centre
    xi = cx + half * sign
    xo = cx - half * sign
    cy = CY + y_off
    d.polygon([
        (xo, cy - outer_h), (xi, cy - inner_h),
        (xi, cy + inner_h), (xo, cy + outer_h),
    ], fill=fill)


def arc(d: ImageDraw.ImageDraw, cx: int, mirror: bool, *,
        thickness: int, rise: int, fill=EDGE) -> None:
    """A curved slit. rise>0 bows upward (happy), rise<0 downward (sad)."""
    half, steps = EYE_W // 2, 48
    top, bot = [], []
    for i in range(steps + 1):
        t = i / steps
        x = cx - half + t * EYE_W
        y = CY - rise * 4 * t * (1 - t)
        top.append((x, y - thickness))
        bot.append((x, y + thickness))
    d.polygon(top + bot[::-1], fill=fill)


def render(shape, glow: float = 1.0) -> Image.Image:
    """Shape + additive bloom. The bloom is what sells it as a lit element."""
    body = Image.new("RGB", (W, H), BG)
    slit_d = ImageDraw.Draw(body)
    shape(slit_d, EDGE)

    # wide soft halo
    halo = body.filter(ImageFilter.GaussianBlur(14))
    halo = Image.eval(halo, lambda v: int(v * 0.75 * glow))
    # tight bright bloom
    near = body.filter(ImageFilter.GaussianBlur(4))
    near = Image.eval(near, lambda v: int(v * 0.55 * glow))

    out = ImageChops.add(halo, near)
    out = ImageChops.add(out, Image.eval(body, lambda v: int(v * glow)))

    # hot core: the same shape, inset, in a lighter tone
    core = Image.new("RGB", (W, H), BG)
    shape(ImageDraw.Draw(core), CORE)
    core = core.filter(ImageFilter.GaussianBlur(1))
    return ImageChops.add(out, Image.eval(core, lambda v: int(v * 0.35 * glow)))


def both(fn):
    """Mirror a single-eye draw into a symmetric pair."""
    def draw(d, fill):
        fn(d, LCX, False, fill)
        fn(d, RCX, True, fill)
    return draw


def slits(inner_h, outer_h, y_off=0):
    return both(lambda d, cx, m, f: slit(
        d, cx, m, inner_h=inner_h, outer_h=outer_h, y_off=y_off, fill=f))


def arcs(thickness, rise):
    return both(lambda d, cx, m, f: arc(
        d, cx, m, thickness=thickness, rise=rise, fill=f))


def breathe(shape, n=18, lo=0.82, hi=1.0):
    return [render(shape, glow=lo + (hi - lo) * (0.5 + 0.5 * math.cos(2 * math.pi * i / n)))
            for i in range(n)]


def blink(inner, outer, n_close=4, hold=1, n_open=5):
    seq = ([1 - i / n_close for i in range(n_close)] + [0.05] * hold
           + [i / n_open for i in range(1, n_open + 1)])
    return [render(slits(max(2, int(inner * s)), max(2, int(outer * s)))) for s in seq]


EMOTIONS: dict[str, list[Image.Image]] = {
    # resting: narrow, slanted down toward the centre
    "neutral":    breathe(slits(7, 19)),
    "angry":      breathe(slits(3, 24), lo=0.72),
    "happy":      breathe(arcs(7, 18)),
    "sad":        breathe(arcs(6, -15), lo=0.55, hi=0.8),
    "surprise":   breathe(slits(23, 23), lo=0.92),
    "fear":       breathe(slits(19, 11), n=14, lo=0.5, hi=1.0),
    "sleep":      breathe(slits(2, 3), n=24, lo=0.2, hi=0.5),
    "blink_fast": blink(7, 19, n_close=2, hold=1, n_open=3),
    "blink_slow": blink(7, 19, n_close=6, hold=3, n_open=7),
    "blink1":     blink(7, 19),
    "dizzy":      [render(slits(9 + int(5 * math.sin(2 * math.pi * i / 20)),
                                17 - int(5 * math.sin(2 * math.pi * i / 20)),
                                y_off=int(6 * math.sin(4 * math.pi * i / 20))))
                   for i in range(20)],
}

FILENAMES = {
    "angry": "emotion_angry_284_126", "blink1": "emotion_blink1_284_126",
    "blink_fast": "emotion_blink_fast_284_126", "blink_slow": "emotion_blink_slow_284_126",
    "dizzy": "emotion_dizzy_284_126", "happy": "emotion_happy_284_126",
    "sad": "emotion_sad_284_126", "sleep": "emotion_sleep_284_126",
    "neutral": "emotion_neutral_284_126", "surprise": "emotion_surprise_284_126",
    "fear": "emotion_fear_284_126",
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT.parent / "preview").mkdir(parents=True, exist_ok=True)
    total = 0
    for name, frames in EMOTIONS.items():
        stem = FILENAMES[name]
        path = OUT / f"{stem}.gif"
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=60, loop=0, optimize=False)
        frames[len(frames) // 3].save(OUT.parent / "preview" / f"{name}.png")
        total += path.stat().st_size
        print(f"{name:<12} {len(frames):>3} frames  {path.stat().st_size:>7}B")
    print(f"{'total':<12} {'':>3}         {total:>7}B")
