"""The WhatsApp Status page."""

from datetime import date
import json
from pathlib import Path
import re

from daily_verse import status_page

VERSES = {
    "ta": {"lang": "ta", "reference": "சங்கீதம் 119:14", "text": "களிகூருகிறேன்."},
    "en": {"lang": "en", "reference": "Psalm 119:14", "text": "I have rejoiced </script>."},
    "de": {"lang": "de", "reference": "Psalm 119,14", "text": "Ich freue mich."},
}


def _manifest(media: Path, day: str, **extra: object) -> None:
    path = media / f"{day[:4]}/{day[5:7]}/{day[8:]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": day, "verses": VERSES, "buffer": {}, **extra}, ensure_ascii=False))


def test_page_lists_days_with_per_language_videos(tmp_path: Path) -> None:
    _manifest(tmp_path, "2026-10-14", video="2026/10/14.mp4")  # older trilingual day: not shareable per language
    _manifest(tmp_path, "2026-10-15", videos={lang: f"2026/10/15-{lang}.mp4" for lang in ("ta", "en", "de")})
    page = status_page.build(tmp_path, date(2026, 10, 15)).read_text(encoding="utf-8")
    raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)[1]
    assert "</script>" not in raw  # the verse text cannot break out of the data block
    data = json.loads(raw.replace("<\\/", "</"))
    assert [d["date"] for d in data["days"]] == ["2026-10-15"]
    tamil = data["days"][0]["items"][0]
    assert tamil["video"] == "2026/10/15-ta.mp4" and tamil["language"] == "தமிழ்"
    assert tamil["caption"] == "இன்றைய வசனம் · சங்கீதம் 119:14\nchrist-livingpetra.de"
    assert (tmp_path / "icon.png").exists() and (tmp_path / ".nojekyll").exists()
    assert json.loads((tmp_path / "manifest.webmanifest").read_text())["short_name"] == "Daily Verse"
