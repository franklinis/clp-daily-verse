"""Command line: render slides, then create Buffer drafts that use them.

    python -m daily_verse render [--start YYYY-MM-DD] [--days N] [--force]
    python -m daily_verse drafts [--start YYYY-MM-DD] [--days N]
    python -m daily_verse prune [--keep-days N]
    python -m daily_verse preview [--start YYYY-MM-DD] [--days N] --out DIR   (narrated test videos)

Each day gets YYYY/MM/DD-{ta,en,de}.png (feed carousel), YYYY/MM/DD.mp4 (Reel
and YouTube Short) and a DD.json manifest in $MEDIA_DIR (default ./images). The
manifest records the verse texts and the Buffer drafts already created, so
re-running never duplicates work.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import time as clock
import urllib.request
from zoneinfo import ZoneInfo

from . import buffer, captions, music, render, sources, speech, video

IMAGES = Path(os.environ.get("MEDIA_DIR", render.ROOT / "images"))
TIMEZONE = ZoneInfo("Europe/Berlin")
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/franklinis/clp-daily-verse/media"
ORDER = ("ta", "en", "de")


def manifest_path(day: date) -> Path:
    return IMAGES / f"{day:%Y/%m/%d}.json"


def image_name(day: date, lang: str) -> str:
    return f"{day:%Y/%m/%d}-{lang}.png"


def days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def narration_on() -> bool:
    """Read-aloud is used once the church switches it on and Azure is configured."""
    return os.environ.get("NARRATION", "").lower() == "on" and speech.enabled()


def language_video_name(day: date, lang: str) -> str:
    return f"{day:%Y/%m/%d}-{lang}.mp4"


def render_language_video(verse: sources.Verse, day: date, out: Path, narrate: bool) -> bool:
    """One vertical slide with music (and the reading, if narrated); returns whether it is narrated."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        slide = render.render(verse, day, work / f"{verse.lang}.png", "video")
        voice = None
        if narrate:
            reading = speech.narrate_one(verse.lang, asdict(verse), day, work)
            seconds, starts = video.narrated_timing([reading.seconds])
            voice = speech.combine([reading], starts, seconds[0], work / "narration.wav")
        else:
            seconds = [video.reading_seconds(verse.text) + 1.5]
        track, _ = music.track_for(day, seconds[0], work)
        video.make_video([slide], seconds, out, music=track, narration=voice)
    return voice is not None


def cmd_render(args: argparse.Namespace) -> int:
    for day in days(args.start, args.days):
        path = manifest_path(day)
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if manifest and not args.force:
            verses = {lang: sources.Verse(**manifest["verses"][lang]) for lang in ORDER}
        else:
            try:
                verses = sources.fetch_day(day)
            except sources.SourceError as err:
                print(f"{day}: skipped, {err}")
                continue
            for lang in ORDER:
                render.render(verses[lang], day, IMAGES / image_name(day, lang))
            manifest = {
                "date": day.isoformat(),
                "verses": {lang: asdict(verses[lang]) for lang in ORDER},
                "images": {lang: image_name(day, lang) for lang in ORDER},
                "buffer": (manifest or {}).get("buffer", {}),
            }
        # Days from before per-language videos keep their trilingual video and drafts.
        videos = manifest.get("videos", {})
        if "video" not in manifest and (
            args.force or set(videos) != set(ORDER) or not all((IMAGES / v).exists() for v in videos.values())
        ):
            narrate = narration_on()
            manifest["videos"] = {}
            for lang in ORDER:
                render_language_video(verses[lang], day, IMAGES / language_video_name(day, lang), narrate)
                manifest["videos"][lang] = language_video_name(day, lang)
            manifest["narrated"] = narrate
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


def _channels(variable: str) -> list[tuple[str, str]]:
    """Parse "id:service,id:service" from an environment variable."""
    return [tuple(c.split(":", 1)) for c in os.environ.get(variable, "").split(",") if c]  # type: ignore[misc]


@dataclass(frozen=True)
class Job:
    """One Buffer draft to create; `key` records it in the day's manifest."""

    key: str
    channel_id: str
    service: str
    kind: str
    text: str
    assets: list
    metadata: dict
    urls: list


def draft_jobs(manifest: dict, base_url: str, carousel_channels: list, video_channels: list) -> list[Job]:
    """Every draft a day needs: the carousel per feed channel, and each language's video per video channel."""
    verses = manifest["verses"]
    jobs = []
    image_urls = [f"{base_url}/{manifest['images'][lang]}" for lang in ORDER]
    images = [
        {"image": {"url": url, "metadata": {"altText": f"{verses[lang]['reference']}: {verses[lang]['text']}"}}}
        for url, lang in zip(image_urls, ORDER, strict=True)
    ]
    for channel_id, service in carousel_channels:
        jobs.append(Job(channel_id, channel_id, service, "carousel", captions.carousel_text(verses, service),
                        images, buffer.carousel_metadata(service), image_urls))
    narrated = manifest.get("narrated", False)
    for lang, name in manifest.get("videos", {}).items():
        url = f"{base_url}/{name}"
        clip = [{"video": {"url": url, "metadata": {"thumbnailOffset": 500}}}]
        for channel_id, service in video_channels:
            text = (captions.language_youtube_description(verses, lang) if service == "youtube"
                    else captions.language_reel_text(verses, lang, service))
            metadata = buffer.video_metadata(service, captions.language_youtube_title(verses, lang), ai_voice=narrated)
            jobs.append(Job(f"video-{lang}:{channel_id}", channel_id, service, f"{lang} video", text, clip,
                            metadata, [url]))
    return jobs


def cmd_drafts(args: argparse.Namespace) -> int:
    captions.check()
    api_key = os.environ.get("BUFFER_API_KEY")
    carousel_channels = _channels("BUFFER_CHANNELS")
    video_channels = _channels("BUFFER_VIDEO_CHANNELS")
    if not carousel_channels and not video_channels:
        print("Set BUFFER_CHANNELS and/or BUFFER_VIDEO_CHANNELS (id:service,...)", file=sys.stderr)
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
        due_at = datetime.combine(day, post_time, TIMEZONE)
        pending = [
            job for job in draft_jobs(manifest, base_url, carousel_channels, video_channels)
            if job.key not in manifest["buffer"]
        ]
        for url in dict.fromkeys(url for job in pending for url in job.urls):
            wait_until_public(url)
        for job in pending:
            try:
                post_id = buffer.create_draft(api_key, job.channel_id, job.text, job.assets, job.metadata, due_at)
            except buffer.BufferError as err:
                print(f"{day} {job.service} {job.kind}: {err}", file=sys.stderr)
                failed = True
                continue
            manifest["buffer"][job.key] = post_id
            print(f"{day} {job.service} {job.kind}: draft {post_id}")
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


def cmd_preview(args: argparse.Namespace) -> int:
    """Narrated videos in --out for listening, without touching the media branch or Buffer."""
    if not speech.enabled():
        print("Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION to preview narration", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    for day in days(args.start, args.days):
        path = manifest_path(day)
        try:
            verses = (
                {lang: sources.Verse(**json.loads(path.read_text(encoding="utf-8"))["verses"][lang]) for lang in ORDER}
                if path.exists() else sources.fetch_day(day)
            )
        except sources.SourceError as err:
            print(f"{day}: skipped, {err}")
            continue
        for lang in ORDER:
            out = out_dir / f"{day}-{lang}.mp4"
            render_language_video(verses[lang], day, out, narrate=True)
            print(f"{day}: {out} ({speech.voices_for(day)[lang]})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="daily_verse")
    parser.add_argument("command", choices=["render", "drafts", "prune", "preview"])
    parser.add_argument("--start", type=date.fromisoformat,
                        default=datetime.now(TIMEZONE).date() + timedelta(days=1))
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="re-render days that already exist")
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--out", default="preview", help="folder for preview videos")
    args = parser.parse_args()
    commands = {"render": cmd_render, "drafts": cmd_drafts, "prune": cmd_prune, "preview": cmd_preview}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
