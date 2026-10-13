"""Generated misty-mountain backgrounds, echoing the church website's artwork.

Each date gets its own ridgelines (seeded by the date, so re-rendering a day
gives the same picture) and a palette that follows the day of the week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import random

WIDTH, HEIGHT = 1080, 1350


@dataclass(frozen=True)
class Palette:
    name: str
    sky_top: str
    sky_bottom: str
    far: str  # farthest ridge, closest to the sky colour
    near: str  # nearest ridge, darkest
    accent: str  # label, rule, reference, frame
    quote: str  # quotation marks


# Monday first, matching date.weekday(). Sunday keeps the church's green.
PALETTES = [
    Palette("dawn", "#1b2f4a", "#3d6188", "#5a7ba0", "#0e1b2b", "#e2c08d", "#9cc3e6"),
    Palette("earth", "#43291f", "#7a5243", "#8c6455", "#2a1813", "#ecd0b0", "#e0a98a"),
    Palette("teal", "#103b44", "#2c6f78", "#4d9198", "#09232a", "#d8b598", "#8fd3cc"),
    Palette("dusk", "#2a2040", "#5c4677", "#78618f", "#171124", "#e8c7a4", "#c7a8e0"),
    Palette("gold", "#3f2a12", "#8a6430", "#9b7745", "#26190a", "#f3d9a4", "#f0c070"),
    Palette("slate", "#1b242c", "#46596a", "#607485", "#0e1418", "#d9b89c", "#a9c2d6"),
    Palette("petra", "#173f37", "#2f6d5f", "#448676", "#0d2823", "#cba590", "#7cc4b3"),
]


def palette_for(day: date) -> Palette:
    return PALETTES[day.weekday()]


def _mix(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives a, t=1 gives b."""
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb, strict=True))


def _ridge(rng: random.Random, base: float, amplitude: float) -> str:
    """A smooth, closed ridgeline path from a few layered sine waves and one peak."""
    waves = [(rng.uniform(0.8, 2.2), rng.uniform(0, math.tau), 1.0),
             (rng.uniform(2.5, 5.0), rng.uniform(0, math.tau), 0.45),
             (rng.uniform(6.0, 11.0), rng.uniform(0, math.tau), 0.15)]
    peak_x, peak_w = rng.uniform(0.15, 0.85), rng.uniform(0.08, 0.2)
    points = []
    for i in range(0, 37):
        x = i / 36
        y = sum(w * math.sin(f * math.tau * x + p) for f, p, w in waves) / 1.6
        y += 1.4 * math.exp(-(((x - peak_x) / peak_w) ** 2))
        points.append((x * WIDTH, base - amplitude * y))
    # Catmull-Rom through the points, as cubic Béziers, for soft hills.
    d = f"M{-10},{HEIGHT + 10} L{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0, p1, p2 = points[max(i - 1, 0)], points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d + f" L{WIDTH + 10},{HEIGHT + 10} Z"


def svg(day: date) -> str:
    """The full-bleed background for a date, as inline SVG."""
    rng = random.Random(day.toordinal())
    pal = palette_for(day)
    layers = 6
    defs = [
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{pal.sky_top}"/><stop offset="1" stop-color="{pal.sky_bottom}"/></linearGradient>',
        '<radialGradient id="sun"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
        '<stop offset=".25" stop-color="#fff" stop-opacity=".18"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        "</radialGradient>",
        # Darkens the middle slightly so white text stays readable on any ridge.
        '<radialGradient id="scrim" cx=".5" cy=".55" r=".6"><stop offset="0" stop-color="#000" stop-opacity=".28"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>',
    ]
    shapes = [f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#sky)"/>']
    sun_x, sun_y = rng.uniform(0.2, 0.8) * WIDTH, rng.uniform(0.2, 0.32) * HEIGHT
    shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="260" fill="url(#sun)"/>')
    for i in range(layers):
        t = i / (layers - 1)
        colour = _mix(pal.far, pal.near, t)
        mist = _mix(colour, pal.sky_bottom, 0.55)
        defs.append(
            f'<linearGradient id="l{i}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{colour}"/><stop offset=".55" stop-color="{mist}"/>'
            f'<stop offset="1" stop-color="{mist}"/></linearGradient>'
        )
        base = HEIGHT * (0.40 + 0.11 * i)
        shapes.append(f'<path d="{_ridge(rng, base, 70 - 6 * i)}" fill="url(#l{i})"/>')
    shapes.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#scrim)"/>')
    return (
        f'<svg class="bg" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<defs>{"".join(defs)}</defs>{"".join(shapes)}</svg>'
    )
