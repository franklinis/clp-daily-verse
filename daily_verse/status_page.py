"""A phone page for posting the day's videos to WhatsApp Status in a few taps.

WhatsApp has no official way to post a Status automatically, so this page
does the next best thing: each video gets a button that opens the phone's
share sheet with the video attached (choose WhatsApp → My status), plus a
caption to copy. It is written into the media folder, which GitHub Pages
serves at https://franklinis.github.io/clp-daily-verse/.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from .captions import CHURCH
from .render import ROOT

LANGUAGE_NAMES = {"ta": "தமிழ்", "en": "English", "de": "Deutsch"}
TEMPLATE = (Path(__file__).parent / "status_page.html").read_text(encoding="utf-8")


def caption(manifest: dict, lang: str) -> str:
    """The Status text: label and reference, then the website."""
    reference = manifest["verses"][lang]["reference"]
    return f"{CHURCH['label'][lang]} · {reference}\n{CHURCH['website'].removeprefix('https://')}"


def collect(media: Path) -> list[dict]:
    """Every day that has per-language videos, oldest first."""
    days = []
    for path in sorted(media.glob("*/*/*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        videos = manifest.get("videos") or {}
        if not videos:
            continue
        days.append({
            "date": manifest["date"],
            "items": [
                {
                    "lang": lang,
                    "language": LANGUAGE_NAMES[lang],
                    "reference": manifest["verses"][lang]["reference"],
                    "video": name,
                    "filename": f"verse-{manifest['date']}-{lang}.mp4",
                    "caption": caption(manifest, lang),
                }
                for lang, name in videos.items()
            ],
        })
    return days


def _icon(out: Path) -> None:
    """Home-screen icon: the white church logo on the church green."""
    from PIL import Image

    logo = Image.open(ROOT / "assets" / "logo-white.png").convert("RGBA").resize((400, 400), Image.LANCZOS)
    icon = Image.new("RGBA", (512, 512), "#205b4f")
    icon.alpha_composite(logo, (56, 56))
    icon.convert("RGB").save(out)


def build(media: Path, today: date | None = None) -> Path:
    """Write index.html (with the days embedded), the icon and the web app manifest into `media`."""
    media.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"days": collect(media), "built": (today or date.today()).isoformat()}, ensure_ascii=False)
    # Keep the embedded JSON from ever closing the <script> tag early.
    page = TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))
    (media / "index.html").write_text(page, encoding="utf-8")
    _icon(media / "icon.png")
    (media / "manifest.webmanifest").write_text(json.dumps({
        "name": "Daily Verse · Christ the Living Petra",
        "short_name": "Daily Verse",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#173f37",
        "theme_color": "#205b4f",
        "icons": [{"src": "icon.png", "sizes": "512x512", "type": "image/png"}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (media / ".nojekyll").write_text("")  # serve files as they are
    return media / "index.html"
