"""Generated misty-mountain backgrounds, echoing the church website's artwork.

Every date gets its own picture: the palette comes from a shuffled yearly
rotation (Sundays cycle through the church greens, feast days get their own),
and the sky, sun, light rays, fog and ridgelines are drawn from a random
generator seeded by the date, so re-rendering a day always gives the same image.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math
import random

WIDTH, HEIGHT = 1080, 1350


@dataclass(frozen=True)
class Palette:
    name: str
    sky: tuple[str, ...]  # top of the sky down to the horizon
    far: str  # farthest ridge, closest to the sky colour
    near: str  # nearest ridge, darkest
    accent: str  # label, rule, reference, frame
    quote: str  # quotation marks
    glow: str = "#ffffff"  # sun, moon, star and light-ray colour
    night: bool = False  # starry sky with a crescent moon instead of a sun
    sky_object: str = ""  # override: "star" (Christmas) or "none" (Good Friday)


SUNDAY = [
    Palette("petra", ("#173f37", "#2f6d5f"), "#448676", "#0d2823", "#cba590", "#7cc4b3"),
    Palette("emerald", ("#0f3b2e", "#1f6b4f"), "#3c8b6b", "#08231b", "#e3c79a", "#8fe0b8", "#fff3d6"),
    Palette("forest", ("#14281c", "#2e5138"), "#4c6e52", "#0a1610", "#d9c49a", "#a7d39a", "#f6e7c1"),
    Palette("sage", ("#22332c", "#4e6b5d"), "#678a78", "#141f1a", "#efd9b8", "#b9dcc6"),
]

WEEKDAY = [
    # Blues
    Palette("dawn", ("#1b2f4a", "#3d6188"), "#5a7ba0", "#0e1b2b", "#e2c08d", "#9cc3e6"),
    Palette("ocean", ("#0b2a3f", "#1d5a7a"), "#3a7d9c", "#061723", "#f0c99a", "#86d0f0"),
    Palette("indigo", ("#1c1b4a", "#3b3a85"), "#5755a0", "#0f0e2a", "#f1cf96", "#b3b0ff"),
    Palette("storm", ("#1e2a36", "#4a5d70"), "#667a8e", "#11181f", "#e6c7a5", "#b5cde0"),
    Palette("arctic", ("#12324a", "#2f6e8f"), "#4f88a6", "#0b1f2d", "#fde2b0", "#bfe6ff"),
    Palette("harbour", ("#16283d", "#2c4f6e", "#4b6f86"), "#567d96", "#0c1824", "#f2d3a2", "#a3d2ee", "#ffeccc"),
    # Purples and pinks
    Palette("dusk", ("#2a2040", "#5c4677"), "#78618f", "#171124", "#e8c7a4", "#c7a8e0"),
    Palette("lavender", ("#2e2a4f", "#5f5590"), "#7a6fa5", "#1a1730", "#f6d9b0", "#d9cff7"),
    Palette("plum", ("#2c1530", "#5e2f5f"), "#7b4a7a", "#180b1a", "#f0c9a2", "#e3a6d8"),
    Palette("rose dusk", ("#2e1a2b", "#6e3a55", "#9a5566"), "#8c5468", "#1b0f19", "#ffd9b8", "#f7b3c2", "#ffd2b0"),
    Palette("wine", ("#2a0f17", "#5c1f2f"), "#7a3a48", "#17070c", "#f1c79b", "#f0a3a9"),
    Palette("orchid", ("#24173a", "#4f2f6b", "#7a4a7e"), "#6f4a80", "#140c22", "#f8d7a8", "#e9b6f0", "#ffd9e8"),
    # Warm
    Palette("earth", ("#43291f", "#7a5243"), "#8c6455", "#2a1813", "#ecd0b0", "#e0a98a"),
    Palette("terracotta", ("#3d1f17", "#7e4430"), "#955a45", "#24110c", "#ffd8b0", "#f4a98a", "#ffe0c0"),
    Palette("gold", ("#3f2a12", "#8a6430"), "#9b7745", "#26190a", "#f3d9a4", "#f0c070", "#fff1c9"),
    Palette("amber", ("#3a2208", "#8a5212"), "#9c6a2c", "#241405", "#ffe1a8", "#ffc56b", "#ffe9b0"),
    Palette("sunrise", ("#1f2a4a", "#5e4466", "#a8694f"), "#7e5862", "#1a1426", "#ffe0b5", "#ffb98a", "#ffd9a0"),
    Palette("sunset", ("#2a1838", "#7a3a4c", "#b8703f"), "#8a4b4b", "#1c0d16", "#ffe3b8", "#ffb070", "#ffcf8a"),
    Palette("copper", ("#2e1c14", "#6e4630"), "#8a5d42", "#1a0f0a", "#f5d2a8", "#e8a878"),
    Palette("desert", ("#3e3022", "#7a6346"), "#8d7656", "#2a2016", "#fff0d0", "#f3d29a", "#fff4dc"),
    Palette("olive", ("#2a2d17", "#575c30"), "#70754a", "#16180b", "#f0dca8", "#d3dc8f"),
    # Teal and neutrals
    Palette("teal", ("#103b44", "#2c6f78"), "#4d9198", "#09232a", "#d8b598", "#8fd3cc"),
    Palette("lagoon", ("#0b3a3f", "#146e6e"), "#2c8a86", "#05211f", "#ffdcae", "#8ff0e0"),
    Palette("slate", ("#1b242c", "#46596a"), "#607485", "#0e1418", "#d9b89c", "#a9c2d6"),
    Palette("charcoal", ("#1a1a1d", "#3d3c42"), "#57565d", "#0d0d0f", "#d9b98f", "#c9c3b8"),
    Palette("mist", ("#26323a", "#55666e"), "#6f8088", "#151c20", "#f3dcc0", "#cfe0e6"),
    # Night skies
    Palette("midnight", ("#0b1026", "#1d2752"), "#33406e", "#070a17", "#d8c08a", "#a7b6ff", "#fff6dc", True),
    Palette("aurora", ("#081c2a", "#0f4a4a", "#1f6a52"), "#1f5a55", "#051318", "#e8d7a2", "#9ff5c8", "#dffff0", True),
    Palette("starlight", ("#0a0f1f", "#202a4f"), "#2e3b66", "#060914", "#e7cf95", "#b8c6ff", "#ffffff", True),
    Palette("violet night", ("#120c24", "#2f1f52"), "#463670", "#0a0716", "#f0d39c", "#cdb8ff", "#fff3e0", True),
]

FEAST = {
    "christmas": Palette("christmas", ("#0a1030", "#23306a"), "#34437c", "#060a1d", "#f3d58a", "#ffe08a", "#fff1c0", True, "star"),
    "new year": Palette("new year", ("#1f2a4a", "#5e4466", "#b0704a"), "#7e5862", "#1a1426", "#ffe0b5", "#ffc98a", "#ffe2b0"),
    "good friday": Palette("good friday", ("#1a1022", "#3a2442"), "#4f3a58", "#0e0814", "#d9c3a0", "#c3a6cf", sky_object="none"),
    "easter": Palette("easter", ("#2a2a4a", "#7a5368", "#c08250"), "#8a6266", "#1b1626", "#fff0c8", "#ffd27a", "#fff3c8"),
    "pentecost": Palette("pentecost", ("#2a0e0e", "#6a2618", "#a8461c"), "#84402a", "#190707", "#ffe1b0", "#ffb35c", "#ffd59a"),
}

PALETTES = SUNDAY + WEEKDAY + list(FEAST.values())


def easter(year: int) -> date:
    """Western Easter Sunday (Meeus/Jones/Butcher Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def feast(day: date) -> str | None:
    """The feast a date belongs to, if any."""
    easter_day = easter(day.year)
    if day.month == 12 and 24 <= day.day <= 26:
        return "christmas"
    if (day.month, day.day) == (1, 1):
        return "new year"
    return {
        easter_day - timedelta(days=2): "good friday",
        easter_day: "easter",
        easter_day + timedelta(days=49): "pentecost",
    }.get(day)


def _weekday_rotation(year: int, count: int) -> list[Palette]:
    """Weekday palettes for a year: shuffled cycles with no palette twice in a row."""
    order: list[Palette] = []
    cycle = 0
    while len(order) < count:
        batch = WEEKDAY[:]
        random.Random(year * 1000 + cycle).shuffle(batch)
        if order and batch[0] == order[-1]:
            batch.append(batch.pop(0))
        order.extend(batch)
        cycle += 1
    return order


def palette_for(day: date) -> Palette:
    """Feast days first, then a Sunday green, then the weekday rotation."""
    if name := feast(day):
        return FEAST[name]
    if day.weekday() == 6:
        return SUNDAY[day.isocalendar().week % len(SUNDAY)]
    weekdays_before = sum(
        1 for i in range((day - date(day.year, 1, 1)).days) if (date(day.year, 1, 1) + timedelta(days=i)).weekday() != 6
    )
    return _weekday_rotation(day.year, weekdays_before + 1)[weekdays_before]


def _rgb(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _mix(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives a, t=1 gives b."""
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(_rgb(a), _rgb(b), strict=True))


def luminance(colour: str) -> float:
    """WCAG relative luminance."""
    def channel(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ridge(rng: random.Random, base: float, amplitude: float, style: str) -> str:
    """A smooth, closed ridgeline: layered sine waves plus one or two peaks."""
    waves = [(rng.uniform(0.8, 2.2), rng.uniform(0, math.tau), 1.0),
             (rng.uniform(2.5, 5.0), rng.uniform(0, math.tau), 0.45),
             (rng.uniform(6.0, 11.0), rng.uniform(0, math.tau), 0.15 if style != "alpine" else 0.3)]
    peaks = [(rng.uniform(0.12, 0.88), rng.uniform(0.05, 0.12) if style == "alpine" else rng.uniform(0.1, 0.22),
              rng.uniform(1.0, 1.8)) for _ in range(1 if style == "rolling" else 2)]
    points = []
    for i in range(0, 49):
        x = i / 48
        y = sum(w * math.sin(f * math.tau * x + p) for f, p, w in waves) / 1.6
        y += sum(h * math.exp(-(((x - px) / pw) ** 2)) for px, pw, h in peaks)
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
    style = rng.choice(["rolling", "layered", "alpine"])
    layers = {"rolling": rng.randint(4, 5), "layered": rng.randint(6, 7), "alpine": rng.randint(4, 6)}[style]
    first_base = rng.uniform(0.36, 0.48)
    spacing = (0.95 - first_base) / layers
    mist = rng.uniform(0.4, 0.7)
    # Keep the sun or moon to either side, clear of the centred label and date.
    sun_x = rng.choice([rng.uniform(0.12, 0.3), rng.uniform(0.7, 0.88)]) * WIDTH
    sun_y = rng.uniform(0.14, 0.32) * HEIGHT
    horizon = HEIGHT * first_base

    stops = "".join(
        f'<stop offset="{i / (len(pal.sky) - 1):.2f}" stop-color="{c}"/>' for i, c in enumerate(pal.sky)
    )
    tilt = rng.uniform(-0.25, 0.25)
    defs = [
        f'<linearGradient id="sky" x1="{0.5 - tilt:.2f}" y1="0" x2="{0.5 + tilt:.2f}" y2="{first_base + 0.1:.2f}">'
        f"{stops}</linearGradient>",
        f'<radialGradient id="sun"><stop offset="0" stop-color="{pal.glow}" stop-opacity=".6"/>'
        f'<stop offset=".22" stop-color="{pal.glow}" stop-opacity=".2"/>'
        f'<stop offset="1" stop-color="{pal.glow}" stop-opacity="0"/></radialGradient>',
        # Warm or cool glow rising from the horizon below the sun; fades out in every direction.
        f'<radialGradient id="horizon" gradientUnits="userSpaceOnUse" cx="{sun_x:.0f}" cy="{horizon:.0f}" r="{WIDTH * 0.9:.0f}">'
        f'<stop offset="0" stop-color="{pal.glow}" stop-opacity="{rng.uniform(0.08, 0.2):.2f}"/>'
        f'<stop offset="1" stop-color="{pal.glow}" stop-opacity="0"/></radialGradient>',
        '<filter id="soft" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="28"/></filter>',
    ]
    # Stronger centre darkening on lighter palettes keeps white text readable.
    scrim = 0.24 + max(0.0, luminance(pal.far) - 0.08) * 1.4
    defs.append(
        '<radialGradient id="scrim" cx=".5" cy=".55" r=".62">'
        f'<stop offset="0" stop-color="#000" stop-opacity="{min(scrim, 0.42):.2f}"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
    )

    shapes = [f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#sky)"/>',
              f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#horizon)"/>']
    if pal.night:
        for _ in range(rng.randint(70, 130)):
            x, y = rng.uniform(0, WIDTH), rng.uniform(0, horizon)
            if 250 < x < 830 and 80 < y < 430:  # keep the logo, label and date clear
                continue
            shapes.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.uniform(0.8, 2.4):.1f}" '
                          f'fill="{pal.glow}" opacity="{rng.uniform(0.25, 0.9):.2f}"/>')
    if pal.sky_object == "star":  # the star of Bethlehem
        arm, waist = 46, 7
        points = []
        for k in range(8):
            angle = k * math.pi / 4 - math.pi / 2
            length = arm if k % 2 == 0 else waist
            points.append((sun_x + length * math.cos(angle), sun_y + length * math.sin(angle)))
        shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="230" fill="url(#sun)" opacity=".8"/>')
        shapes.append(f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in points)}" fill="{pal.glow}"/>')
    elif pal.night:
        r = rng.uniform(34, 52)
        defs.append(f'<mask id="crescent"><circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{r:.0f}" fill="#fff"/>'
                    f'<circle cx="{sun_x + r * 0.45:.0f}" cy="{sun_y - r * 0.2:.0f}" r="{r:.0f}" fill="#000"/></mask>')
        shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{r * 4:.0f}" fill="url(#sun)" opacity=".5"/>')
        shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{r:.0f}" fill="{pal.glow}" '
                      'opacity=".85" mask="url(#crescent)"/>')
    elif pal.sky_object != "none":
        radius = rng.uniform(170, 320)
        shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{radius:.0f}" fill="url(#sun)"/>')
        if rng.random() < 0.4:
            shapes.append(f'<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{radius * 0.14:.0f}" '
                          f'fill="{pal.glow}" opacity=".35"/>')
        if rng.random() < 0.35:  # soft light rays
            for _ in range(rng.randint(3, 5)):
                angle = rng.uniform(math.pi * 0.15, math.pi * 0.85)
                spread = rng.uniform(0.04, 0.09)
                pts = [(sun_x, sun_y)] + [
                    (sun_x + 1800 * math.cos(angle + s), sun_y + 1800 * math.sin(angle + s)) for s in (-spread, spread)
                ]
                shapes.append(f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in pts)}" '
                              f'fill="{pal.glow}" opacity="{rng.uniform(0.03, 0.06):.3f}"/>')

    fog_layers = set(rng.sample(range(1, layers), k=min(2, layers - 1)))
    for i in range(layers):
        t = i / (layers - 1)
        colour = _mix(pal.far, pal.near, t ** 0.9)
        haze = _mix(colour, pal.sky[-1], mist)
        defs.append(
            f'<linearGradient id="l{i}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{colour}"/><stop offset=".5" stop-color="{haze}"/>'
            f'<stop offset="1" stop-color="{haze}"/></linearGradient>'
        )
        base = HEIGHT * (first_base + spacing * (i + 0.6))
        amplitude = (90 if style == "alpine" else 70) * (1 - 0.1 * i)
        shapes.append(f'<path d="{_ridge(rng, base, amplitude, style)}" fill="url(#l{i})"/>')
        if i in fog_layers:  # a drifting band of mist between ridges
            shapes.append(f'<ellipse cx="{rng.uniform(0.2, 0.8) * WIDTH:.0f}" cy="{base - 20:.0f}" rx="{WIDTH * 0.7:.0f}" '
                          f'ry="38" fill="{pal.sky[-1]}" opacity="{rng.uniform(0.18, 0.32):.2f}" filter="url(#soft)"/>')
    shapes.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#scrim)"/>')
    return (
        f'<svg class="bg" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<defs>{"".join(defs)}</defs>{"".join(shapes)}</svg>'
    )
