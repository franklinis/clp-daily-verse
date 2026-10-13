"""Render a verse slide to a 1080×1350 PNG with headless Chrome.

Chrome is used instead of an image library because it shapes Tamil script
correctly and loads the same web fonts as the church website.
"""

from __future__ import annotations

from datetime import date
import html
import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import tempfile

from . import background
from .sources import Verse

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Template((Path(__file__).parent / "template.html").read_text(encoding="utf-8"))
LOGO = ROOT / "assets" / "logo-white.png"

LANGUAGES = {
    "ta": {
        "label": "இன்றைய வசனம்",
        "days": ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"],
        "months": ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை",
                   "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"],
        "date": "{day}, {d} {month} {y}",
        "credit": "பரிசுத்த வேதாகமம் · tamil-bible.com",
        "quotes": ("“", "”"),
        "serif": "'Noto Serif Tamil', serif",
        "sans": "'Noto Sans Tamil', 'Roboto', sans-serif",
        "size": 58,
        "line_height": 1.6,
        "label_spacing": ".02em",
    },
    "en": {
        "label": "Verse of the Day",
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "date": "{day}, {d} {month} {y}",
        "credit": "King James Version · Public domain",
        "quotes": ("“", "”"),
        "serif": "'Noto Serif', serif",
        "sans": "'Roboto', sans-serif",
        "size": 76,
        "line_height": 1.35,
        "label_spacing": ".22em",
    },
    "de": {
        "label": "Vers des Tages",
        "days": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                   "August", "September", "Oktober", "November", "Dezember"],
        "date": "{day}, {d}. {month} {y}",
        "credit": "Lutherbibel 1912 · gemeinfrei",
        "quotes": ("„", "“"),
        "serif": "'Noto Serif', serif",
        "sans": "'Roboto', sans-serif",
        "size": 76,
        "line_height": 1.35,
        "label_spacing": ".22em",
    },
}


# Feed posts, and vertical video frames whose margins keep text clear of the
# Reels/Shorts overlays (top bar, caption and buttons at the bottom, icons on the right).
FORMATS = {
    "post": {"size": (1080, 1350), "padding": "84px 96px 64px", "frame": "block", "text_scale": 1.0},
    "video": {"size": (1080, 1920), "padding": "250px 120px 470px", "frame": "none", "text_scale": 1.1},
}


def find_chrome() -> str:
    """Locate Chrome: $CHROME, then the usual Linux and macOS installs."""
    candidates = [
        os.environ.get("CHROME"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("Chrome not found; set the CHROME environment variable")


def build_html(verse: Verse, day: date, fmt: str = "post") -> str:
    """Fill the slide template for one language."""
    cfg = LANGUAGES[verse.lang]
    layout = FORMATS[fmt]
    width, height = layout["size"]
    palette = background.palette_for(day)
    return TEMPLATE.substitute(
        lang=verse.lang,
        width=width,
        height=height,
        padding=layout["padding"],
        frame=layout["frame"],
        background=background.svg(day, width, height),
        sky_top=palette.sky[0],
        accent=palette.accent,
        quote=palette.quote,
        sans=cfg["sans"],
        serif=cfg["serif"],
        size=round(cfg["size"] * layout["text_scale"]),
        line_height=cfg["line_height"],
        label_spacing=cfg["label_spacing"],
        logo=LOGO.as_uri(),
        label=html.escape(cfg["label"]),
        date=html.escape(cfg["date"].format(
            day=cfg["days"][day.weekday()], d=day.day, month=cfg["months"][day.month - 1], y=day.year
        )),
        q_open=cfg["quotes"][0],
        q_close=cfg["quotes"][1],
        # Each word in its own span so narrated videos can light words up as they are read.
        text=" ".join(f'<span class="w">{html.escape(word)}</span>' for word in verse.text.split()),
        reference=html.escape(verse.reference),
        credit=html.escape(cfg["credit"]).replace(" ", "&nbsp;").replace("&nbsp;·&nbsp;", " · "),
    )


def _chrome(page: Path, profile: Path, width: int, height: int, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            find_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
            f"--user-data-dir={profile}", "--allow-file-access-from-files", "--force-device-scale-factor=1",
            f"--window-size={width},{height}", "--virtual-time-budget=10000", *extra,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def render_highlight(verse: Verse, day: date, workdir: Path) -> dict:
    """The video slide in three looks (dim, bright, accent) and each word's box on screen.

    The layout is identical in all three, so a word cut from one image lines up
    exactly with the others.
    """
    width, height = FORMATS["video"]["size"]
    workdir.mkdir(parents=True, exist_ok=True)
    page = workdir / f"{verse.lang}-slide.html"
    page.write_text(build_html(verse, day, "video"), encoding="utf-8")
    profile = workdir / "profile"
    dom = _chrome(page, profile, width, height, "--dump-dom", page.as_uri()).stdout.decode("utf-8", "replace")
    match = re.search(r'data-boxes="([^"]*)"', dom)
    if not match:
        raise RuntimeError("Chrome did not report word positions")
    looks = {}
    for mode in ("dim", "bright", "accent"):
        out = workdir / f"{verse.lang}-{mode}.png"
        _chrome(page, profile, width, height, f"--screenshot={out}", f"{page.as_uri()}?mode={mode}")
        looks[mode] = out
    return {**looks, "boxes": json.loads(html.unescape(match[1]))}


def render(verse: Verse, day: date, out: Path, fmt: str = "post") -> Path:
    """Write the slide for one language to `out` and return its path."""
    width, height = FORMATS[fmt]["size"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "slide.html"
        page.write_text(build_html(verse, day, fmt), encoding="utf-8")
        subprocess.run(
            [
                find_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--no-sandbox", f"--user-data-dir={Path(tmp) / 'profile'}",
                "--allow-file-access-from-files", "--force-device-scale-factor=1",
                f"--window-size={width},{height}", "--virtual-time-budget=10000",
                f"--screenshot={out.resolve()}", page.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    if not out.exists():
        raise RuntimeError(f"Chrome did not write {out}")
    return out
