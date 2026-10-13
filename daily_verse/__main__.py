"""Command line: render slides, then create Buffer drafts that use them.

    python -m daily_verse render [--start YYYY-MM-DD] [--days N] [--force]
    python -m daily_verse drafts [--start YYYY-MM-DD] [--days N]
    python -m daily_verse prune [--keep-days N]

Each day gets YYYY/MM/DD-{ta,en,de}.png and a DD.json manifest in $MEDIA_DIR
(default ./images). The manifest records the verse texts and the Buffer drafts
already created, so re-running never duplicates work.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import sys
import time as clock
import urllib.request
from zoneinfo import ZoneInfo

from . import buffer, render, sources

IMAGES = Path(os.environ.get("MEDIA_DIR", render.ROOT / "images"))
TIMEZONE = ZoneInfo("Europe/Berlin")
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/franklinis/clp-daily-verse/media"
ORDER = ("ta", "en", "de")


def manifest_path(day: date) -> Path:
    return IMAGES / f"{day:%Y/%m/%d}.json"


def image_name(day: date, lang: str) -> str:
    return f"{day:%Y/%m/%d}-{lang}.png"


def caption(verses: dict[str, dict[str, str]]) -> str:
    """Post text: references in all three languages plus credits."""
    refs = " · ".join(verses[lang]["reference"] for lang in ORDER)
    return "\n".join([
        "இன்றைய வசனம் · Verse of the Day · Vers des Tages",
        "",
        refs,
        "",
        "தமிழ் · English · Deutsch ➜",
        "",
        "Bible texts: tamil-bible.com · King James Version · Lutherbibel 1912",
        "Verse selection: DailyVerses.net",
        "",
        "#ChristTheLivingPetra #VerseOfTheDay #VersDesTages #TamilChurch #München",
    ])


def days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def cmd_render(args: argparse.Namespace) -> int:
    for day in days(args.start, args.days):
        path = manifest_path(day)
        if path.exists() and not args.force:
            print(f"{day}: already rendered")
            continue
        try:
            verses = sources.fetch_day(day)
        except sources.SourceError as err:
            print(f"{day}: skipped, {err}")
            continue
        for lang in ORDER:
            render.render(verses[lang], day, IMAGES / image_name(day, lang))
        previous = json.loads(path.read_text()) if path.exists() else {}
        path.write_text(json.dumps({
            "date": day.isoformat(),
            "verses": {lang: asdict(verses[lang]) for lang in ORDER},
            "images": {lang: image_name(day, lang) for lang in ORDER},
            "buffer": previous.get("buffer", {}),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{day}: {verses['en'].reference}")
    return 0


def wait_until_public(url: str, attempts: int = 10) -> None:
    """Buffer fetches images when the draft is created, so they must be live first."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30):
                return
        except OSError:
            clock.sleep(min(5 * (attempt + 1), 30))
    raise RuntimeError(f"{url} is not reachable")


def cmd_drafts(args: argparse.Namespace) -> int:
    api_key = os.environ.get("BUFFER_API_KEY")
    channels = [c.split(":") for c in os.environ.get("BUFFER_CHANNELS", "").split(",") if c]
    if not channels:
        print("Set BUFFER_CHANNELS (id:facebook,id:instagram)", file=sys.stderr)
        return 2
    if not api_key:
        # Slides still publish; drafts start once the secret is added.
        print("::warning::BUFFER_API_KEY is not set, so no Buffer drafts were created")
        return 0
    base_url = os.environ.get("IMAGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    post_time = time.fromisoformat(os.environ.get("POST_TIME", "07:00"))

    failed = False
    for day in days(args.start, args.days):
        path = manifest_path(day)
        if not path.exists():
            print(f"{day}: no slides yet, run render first")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        verses = manifest["verses"]
        images = [
            (f"{base_url}/{manifest['images'][lang]}", f"{verses[lang]['reference']}: {verses[lang]['text']}")
            for lang in ORDER
        ]
        due_at = datetime.combine(day, post_time, TIMEZONE)
        if any(channel_id not in manifest["buffer"] for channel_id, _ in channels):
            for url, _ in images:
                wait_until_public(url)
        for channel_id, service in channels:
            if channel_id in manifest["buffer"]:
                continue
            try:
                post_id = buffer.create_draft(api_key, channel_id, service, caption(verses), images, due_at)
            except buffer.BufferError as err:
                print(f"{day} {service}: {err}", file=sys.stderr)
                failed = True
                continue
            manifest["buffer"][channel_id] = post_id
            print(f"{day} {service}: draft {post_id}")
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


def cmd_prune(args: argparse.Namespace) -> int:
    """Delete slides older than --keep-days; Buffer only needs them until they post."""
    cutoff = datetime.now(TIMEZONE).date() - timedelta(days=args.keep_days)
    for path in sorted(IMAGES.glob("*/*/*")):
        try:
            day = date(int(path.parts[-3]), int(path.parts[-2]), int(path.name[:2]))
        except ValueError:
            continue
        if day < cutoff:
            path.unlink()
    for folder in sorted(IMAGES.glob("*/*"), reverse=True) + sorted(IMAGES.glob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="daily_verse")
    parser.add_argument("command", choices=["render", "drafts", "prune"])
    parser.add_argument("--start", type=date.fromisoformat,
                        default=datetime.now(TIMEZONE).date() + timedelta(days=1))
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="re-render days that already exist")
    parser.add_argument("--keep-days", type=int, default=30)
    args = parser.parse_args()
    return {"render": cmd_render, "drafts": cmd_drafts, "prune": cmd_prune}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
