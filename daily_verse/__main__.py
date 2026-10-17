"""Command line: render slides, then create Buffer drafts that use them.

    python -m daily_verse render [--start YYYY-MM-DD] [--days N] [--force]
    python -m daily_verse drafts [--start YYYY-MM-DD] [--days N]
    python -m daily_verse redo --start YYYY-MM-DD [--days N]   (new background, then drafts refresh)
    python -m daily_verse prune [--keep-days N]
    python -m daily_verse preview [--start YYYY-MM-DD] [--days N] --out DIR [--kind narration|backgrounds]
    python -m daily_verse status-page   (phone page for sharing the videos to WhatsApp Status)
    python -m daily_verse verse --message TEXT --result FILE   (check verses picked in Teams)
    python -m daily_verse verse-apply --result FILE   (save them to custom-verses.csv)
    python -m daily_verse verse-reply --result FILE   (answer in Teams)
    python -m daily_verse notify   (tell Teams which picked or changed days are in Buffer)

Each day gets YYYY/MM/DD-{ta,en,de}.png (feed carousel), YYYY/MM/DD.mp4 (Reel
and YouTube Short) and a DD.json manifest in $MEDIA_DIR (default ./images). The
manifest records the verse texts and the Buffer drafts already created, so
re-running never duplicates work. Days listed in custom-verses.csv use the
church's own verse; if a prepared day's pick changes, it is re-rendered and its
drafts are updated.
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

from . import buffer, captions, custom, imagery, music, render, sources, speech, status_page, teams, video

IMAGES = Path(os.environ.get("MEDIA_DIR", render.ROOT / "images"))
TIMEZONE = ZoneInfo("Europe/Berlin")
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/franklinis/clp-daily-verse/media"
ORDER = ("ta", "en", "de")


def manifest_path(day: date) -> Path:
    return IMAGES / f"{day:%Y/%m/%d}.json"


def image_name(day: date, lang: str) -> str:
    return f"{day:%Y/%m/%d}-{lang}.png"


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def posting_day(day: date) -> bool:
    """False on weekdays listed in church.json's skip_days (Sundays): nothing is prepared then."""
    return WEEKDAYS[day.weekday()] not in {d.lower() for d in captions.CHURCH.get("skip_days", [])}


def days(start: date, count: int) -> list[date]:
    return [d for d in (start + timedelta(days=i) for i in range(count)) if posting_day(d)]


def narration_on() -> bool:
    """Read-aloud is used once the church switches it on and Azure is configured."""
    return os.environ.get("NARRATION", "").lower() == "on" and speech.enabled()


def language_video_name(day: date, lang: str) -> str:
    return f"{day:%Y/%m/%d}-{lang}.mp4"


def render_language_video(
    verse: sources.Verse, day: date, out: Path, narrate: bool, scene: Path | None = None
) -> bool:
    """One vertical slide with music (and the reading, if narrated); returns whether it is narrated."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        voice = timeline = None
        if narrate:
            # Follow-along: each word lights up as it is read.
            looks = render.render_highlight(verse, day, work / "looks", scene)
            slide = looks["bright"]
            reading = speech.narrate_one(verse.lang, asdict(verse), day, work)
            seconds, starts = video.narrated_timing([reading.seconds])
            voice = speech.combine([reading], starts, seconds[0], work / "narration.wav")
            times = [(starts[0] + a, starts[0] + b) for a, b in speech.word_times(reading, verse.text)]
            print(f"{day} {verse.lang}: {reading.voice}, {reading.seconds:.1f}s, "
                  f"{speech.LAST_MATCHED}/{len(times)} words on screen timed by Azure "
                  f"(first at {times[0][0]:.2f}s, last ends {times[-1][1]:.2f}s)")
            timeline = video.highlight_timeline(looks, times, seconds[0], work / "frames")
        else:
            slide = render.render(verse, day, work / f"{verse.lang}.png", "video", scene)
            seconds = [video.reading_seconds(verse.text) + 1.5]
        track, _ = music.track_for(day, seconds[0], work)
        video.make_video([slide], seconds, out, music=track, narration=voice, timeline=timeline)
    return voice is not None


def cmd_render(args: argparse.Namespace) -> int:
    picks = custom.load()
    for day in days(args.start, args.days):
        path = manifest_path(day)
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        pick = picks.get(day)
        wanted = pick.reference if pick else None
        # The church picked (or dropped) a verse after the day was prepared.
        changed = manifest is not None and manifest.get("custom") != wanted
        if manifest and not args.force and not changed:
            verses = {lang: sources.Verse(**manifest["verses"][lang]) for lang in ORDER}
            scene = IMAGES / manifest["scene"] if manifest.get("scene") else None
        else:
            try:
                verses, topics = sources.fetch_custom(pick.reference, pick.topics) if pick else sources.fetch_day(day)
            except sources.SourceError as err:
                print(f"{day}: skipped, {err}")
                continue
            if changed:
                (IMAGES / imagery.scene_name(day)).unlink(missing_ok=True)  # a background for the new verse
            scene = imagery.scene_for(day, {lang: asdict(verses[lang]) for lang in ORDER}, topics, IMAGES)
            for lang in ORDER:
                render.render(verses[lang], day, IMAGES / image_name(day, lang), scene=scene)
            old = manifest or {}
            manifest = {
                "date": day.isoformat(),
                "verses": {lang: asdict(verses[lang]) for lang in ORDER},
                "topics": topics,
                "images": {lang: image_name(day, lang) for lang in ORDER},
                "scene": imagery.scene_name(day) if scene else None,
                "buffer": old.get("buffer", {}),
                **{key: old[key] for key in ("revision", "refresh", "announce") if key in old},
            }
            if wanted:
                manifest["custom"] = wanted
                manifest.setdefault("announce", "new")
            if changed:
                # New links so no app shows the old slides, and the drafts already in Buffer get updated.
                manifest.update(revision=old.get("revision", 0) + 1, refresh=bool(manifest["buffer"]),
                                announce="changed" if manifest["buffer"] else "new")
        # Days from before per-language videos keep their trilingual video and drafts.
        videos = manifest.get("videos", {})
        if "video" not in manifest and (
            args.force or changed or set(videos) != set(ORDER)
            or not all((IMAGES / v).exists() for v in videos.values())
        ):
            narrate = narration_on()
            manifest["videos"] = {}
            for lang in ORDER:
                render_language_video(verses[lang], day, IMAGES / language_video_name(day, lang), narrate, scene)
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


def draft_jobs(
    manifest: dict, base_url: str, carousel_channels: list, video_channels: list, ai_label: bool = False
) -> list[Job]:
    """Every draft a day needs: the carousel per feed channel, and each language's video per video channel.

    `ai_label` marks narrated videos as AI-generated where Buffer supports it (Instagram, YouTube).
    """
    verses = manifest["verses"]
    jobs = []
    # A new background bumps the revision, so links change and no app shows a cached copy.
    version = f"?v={manifest['revision']}" if manifest.get("revision") else ""
    image_urls = [f"{base_url}/{manifest['images'][lang]}{version}" for lang in ORDER]
    images = [
        {"image": {"url": url, "metadata": {"altText": f"{verses[lang]['reference']}: {verses[lang]['text']}"}}}
        for url, lang in zip(image_urls, ORDER, strict=True)
    ]
    for channel_id, service in carousel_channels:
        metadata = buffer.carousel_metadata(service, ai_image=ai_label and bool(manifest.get("scene")))
        jobs.append(Job(channel_id, channel_id, service, "carousel",
                        captions.carousel_text(verses, service), images, metadata, image_urls))
    label = ai_label and (manifest.get("narrated", False) or bool(manifest.get("scene")))
    for lang, name in manifest.get("videos", {}).items():
        url = f"{base_url}/{name}{version}"
        clip = [{"video": {"url": url, "metadata": {"thumbnailOffset": 500}}}]
        for channel_id, service in video_channels:
            text = (captions.language_youtube_description(verses, lang) if service == "youtube"
                    else captions.language_reel_text(verses, lang, service))
            metadata = buffer.video_metadata(service, captions.language_youtube_title(verses, lang), ai_voice=label)
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
    ai_label = os.environ.get("AI_LABEL", "off").lower() == "on"

    failed = False
    for day in days(args.start, args.days):
        path = manifest_path(day)
        if not path.exists():
            print(f"{day}: no slides yet, run render first")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        due_at = datetime.combine(day, post_time, TIMEZONE)
        jobs = draft_jobs(manifest, base_url, carousel_channels, video_channels, ai_label)
        pending = [job for job in jobs if job.key not in manifest["buffer"]]
        # After a new background, drafts already in Buffer get the new slides, videos and text.
        refresh = [job for job in jobs if job.key in manifest["buffer"]] if manifest.get("refresh") else []
        for url in dict.fromkeys(url for job in pending + refresh for url in job.urls):
            wait_until_public(url)
        refreshed = True
        for job in refresh:
            try:
                status = buffer.update_post(api_key, manifest["buffer"][job.key], job.text, job.assets, job.metadata)
                print(f"{day} {job.service} {job.kind}: updated ({status})")
            except buffer.BufferError as err:
                # Posts already published can't change; everything else should.
                print(f"::warning::{day} {job.service} {job.kind}: not updated: {err}")
                refreshed = False
        if refresh and refreshed:
            manifest["refresh"] = False
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


def cmd_redo(args: argparse.Namespace) -> int:
    """A new verse-matched background for each day: re-render its slides and videos, then refresh its drafts."""
    if not imagery.enabled():
        print("Set BACKGROUNDS=ai and the Azure image settings to make new backgrounds", file=sys.stderr)
        return 2
    failed = False
    for day in days(args.start, args.days):
        path = manifest_path(day)
        if not path.exists():
            print(f"{day}: not prepared yet, nothing to redo")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        verses = {lang: sources.Verse(**manifest["verses"][lang]) for lang in ORDER}
        (IMAGES / imagery.scene_name(day)).unlink(missing_ok=True)
        scene = imagery.scene_for(day, manifest["verses"], manifest.get("topics", []), IMAGES)
        if not scene:
            failed = True
            continue
        for lang in ORDER:
            render.render(verses[lang], day, IMAGES / image_name(day, lang), scene=scene)
        if "videos" in manifest:
            narrate = narration_on()
            for lang in ORDER:
                render_language_video(verses[lang], day, IMAGES / language_video_name(day, lang), narrate, scene)
            manifest["narrated"] = narrate
        manifest.update(scene=imagery.scene_name(day), revision=manifest.get("revision", 0) + 1, refresh=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{day}: new background ({verses['en'].reference}), revision {manifest['revision']}")
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


def _verses_for_preview(day: date) -> tuple[dict[str, sources.Verse], list[str]]:
    path = manifest_path(day)
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return {lang: sources.Verse(**manifest["verses"][lang]) for lang in ORDER}, manifest.get("topics", [])
    return sources.fetch_day(day)


def cmd_preview(args: argparse.Namespace) -> int:
    """Test output in --out, without touching the media branch or Buffer.

    --kind narration: the three narrated videos per day; --kind backgrounds: the
    verse-matched image and the slides that would use it.
    """
    out_dir = Path(args.out)
    if args.kind == "narration" and not speech.enabled():
        print("Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION to preview narration", file=sys.stderr)
        return 2
    if args.kind == "backgrounds" and not all(
        os.environ.get(n) for n in ("AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_IMAGE_DEPLOYMENT")
    ):
        print("Set AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT and AZURE_IMAGE_DEPLOYMENT to preview backgrounds",
              file=sys.stderr)
        return 2
    failed = False
    for day in days(args.start, args.days):
        try:
            verses, topics = _verses_for_preview(day)
        except sources.SourceError as err:
            print(f"{day}: skipped, {err}")
            continue
        if args.kind == "narration":
            for lang in ORDER:
                out = out_dir / f"{day}-{lang}.mp4"
                render_language_video(verses[lang], day, out, narrate=True)
                print(f"{day}: {out} ({speech.voices_for(day)[lang]})")
            continue
        texts = {lang: asdict(verses[lang]) for lang in ORDER}
        print(f"{day}: {verses['en'].reference}, topics {topics}; {imagery.art_direction(day)}")
        try:
            scene = imagery.generate(imagery.prompt(texts, topics, day), out_dir / f"{day}-scene.jpg")
        except imagery.ImageError as err:
            print(f"{day}: no image: {err}")
            failed = True
            continue
        render.render(verses["en"], day, out_dir / f"{day}-post-en.png", scene=scene)
        render.render(verses["ta"], day, out_dir / f"{day}-video-ta.png", "video", scene)
        print(f"{day}: {scene.name}, overlay {imagery.shade(str(scene))}")
    return 1 if failed else 0


LOCKED = {"scheduled", "sending", "sent"}


def _locked(day: date, api_key: str | None) -> str | None:
    """Why a day's verse can't change any more: its posts are approved (or out) in Buffer."""
    path = manifest_path(day)
    if not api_key or not path.exists():
        return None
    statuses = set()
    for post_id in json.loads(path.read_text(encoding="utf-8")).get("buffer", {}).values():
        try:
            statuses.add(buffer.post_status(api_key, post_id))
        except buffer.BufferError:
            continue  # deleted in Buffer: nothing to protect
    if statuses & LOCKED:
        return (f"{teams.short_date(day)} is already approved in Buffer. To change it, move that day's posts back "
                "to drafts in Buffer, then send this again.")
    return None


def _day_problem(day: date, today: date) -> str | None:
    if day <= today:
        return f"{teams.short_date(day)} is today or already past."
    if not posting_day(day):
        return f"Nothing is posted on {day:%A}s, so {teams.short_date(day)} has no verse."
    return None


def _when(day: date, today: date) -> str:
    if manifest_path(day).exists():
        return "That day's slides and Buffer drafts switch over in a few minutes."
    if day <= today + timedelta(days=3):
        return "Slides and Buffer drafts follow in a few minutes."
    return f"Slides and Buffer drafts are made on {teams.short_date(day - timedelta(days=3))}."


def check_command(command: teams.Command, picks: dict, today: date, api_key: str | None) -> dict:
    """One line of a Teams message: what to answer and, if it's fine, what to change."""
    if command.kind == "help":
        return {"title": "How to pick a verse", "message": teams.HELP}
    if command.kind == "list":
        upcoming = sorted((day, pick) for day, pick in picks.items() if day > today)
        lines = [f"- {teams.short_date(day)}: {pick.reference}" + (f" (theme: {pick.theme})" if pick.theme else "")
                 for day, pick in upcoming]
        return {"title": "Verses you've picked",
                "message": "\n".join(lines) or "None yet; DailyVerses.net picks every day."}
    day = command.day
    if command.kind == "clear":
        if day not in picks:
            return {"title": f"{teams.short_date(day)} already uses DailyVerses.net"}
        if problem := _day_problem(day, today) or _locked(day, api_key):
            return {"title": f"⚠️ {teams.short_date(day)} not changed", "message": problem, "error": True}
        return {"title": f"🗑 {teams.short_date(day)} goes back to DailyVerses.net", "message": _when(day, today),
                "change": {"date": day.isoformat(), "clear": True}}
    if problem := _day_problem(day, today) or _locked(day, api_key):
        return {"title": f"⚠️ {teams.short_date(day)} not changed", "message": problem, "error": True}
    try:
        verses, _ = sources.fetch_custom(command.reference)
    except sources.SourceError as err:
        return {"title": f"⚠️ {teams.short_date(day)}: {command.reference}", "message": str(err), "error": True}
    reference = verses["en"].reference
    result = {"title": f"✅ {teams.short_date(day)}: {reference}", "verses": {k: asdict(v) for k, v in verses.items()},
              "theme": command.theme}
    if picks.get(day) == custom.Entry(reference, command.theme):
        return {**result, "message": "Already picked for that day."}
    return {**result, "message": _when(day, today),
            "change": {"date": day.isoformat(), "reference": reference, "theme": command.theme}}


def _github_output(**values: str) -> None:
    if target := os.environ.get("GITHUB_OUTPUT"):
        with open(target, "a", encoding="utf-8") as file:
            file.writelines(f"{key}={value}\n" for key, value in values.items())


def cmd_verse(args: argparse.Namespace) -> int:
    """Check each line of a Teams message; --result gets the answers and the changes to save."""
    today = datetime.now(TIMEZONE).date()
    picks = custom.load()
    api_key = os.environ.get("BUFFER_API_KEY")
    results = []
    for item in teams.parse_message(args.message, today):
        if isinstance(item, teams.MessageError):
            results.append({"title": "⚠️ I couldn't read that line", "message": str(item), "error": True})
        else:
            results.append(check_command(item, picks, today, api_key))
            if change := results[-1].get("change"):  # so later lines (e.g. "list") see it
                day = date.fromisoformat(change["date"])
                picks = {d: e for d, e in picks.items() if d != day}
                if not change.get("clear"):
                    picks[day] = custom.Entry(change["reference"], change["theme"])
        print(f"{results[-1]['title']}: {results[-1].get('message', '')}")
    changes = [r["change"] for r in results if "change" in r]
    soon = today + timedelta(days=3)
    prepare = any(date.fromisoformat(c["date"]) <= soon for c in changes)
    Path(args.result).write_text(json.dumps({"results": results, "changes": changes}, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    _github_output(changes=str(bool(changes)).lower(), prepare=str(prepare).lower())
    return 0


def cmd_verse_apply(args: argparse.Namespace) -> int:
    """Save the checked changes into custom-verses.csv (safe to repeat)."""
    picks = custom.load()
    for change in json.loads(Path(args.result).read_text(encoding="utf-8"))["changes"]:
        day = date.fromisoformat(change["date"])
        if change.get("clear"):
            picks.pop(day, None)
        else:
            picks[day] = custom.Entry(change["reference"], change.get("theme", ""))
    custom.save(picks)
    return 0


def cmd_verse_reply(args: argparse.Namespace) -> int:
    """Post the answers to the Teams channel (or print them when no webhook is set)."""
    results = json.loads(Path(args.result).read_text(encoding="utf-8"))["results"]
    if os.environ.get("SAVED") == "failure":
        results.append({"title": "⚠️ Saving failed", "message": "Nothing was changed; please send it again.",
                        "error": True})
    message = teams.results_card(results)
    if url := os.environ.get("TEAMS_WEBHOOK_URL"):
        teams.post(url, message)
    else:
        print(json.dumps(message, ensure_ascii=False, indent=2))
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    """Tell Teams when a picked (or changed) day is in Buffer, waiting for approval."""
    url = os.environ.get("TEAMS_WEBHOOK_URL")
    if not url:
        return 0
    base_url = os.environ.get("IMAGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    for path in sorted(IMAGES.glob("*/*/*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not manifest.get("announce") or not manifest.get("buffer") or manifest.get("refresh"):
            continue
        day = date.fromisoformat(manifest["date"])
        version = f"?v={manifest['revision']}" if manifest.get("revision") else ""
        try:
            teams.post(url, teams.ready_card(day, manifest["verses"]["en"]["reference"],
                                             f"{base_url}/{manifest['images']['en']}{version}",
                                             len(manifest["buffer"]), manifest["announce"] == "changed"))
        except OSError as err:
            print(f"::warning::{day}: Teams didn't take the message ({err}); trying again next run")
            continue
        manifest["announce"] = False
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{day}: told Teams")
    return 0


def cmd_status_page(args: argparse.Namespace) -> int:
    page = status_page.build(IMAGES, datetime.now(TIMEZONE).date())
    print(f"Status page: {page}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="daily_verse")
    parser.add_argument("command", choices=["render", "drafts", "redo", "prune", "preview", "status-page", "verse",
                                            "verse-apply", "verse-reply", "notify"])
    parser.add_argument("--start", type=date.fromisoformat,
                        default=datetime.now(TIMEZONE).date() + timedelta(days=1))
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="re-render days that already exist")
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--out", default="preview", help="folder for preview output")
    parser.add_argument("--kind", choices=["narration", "backgrounds"], default="narration", help="what to preview")
    parser.add_argument("--message", default="", help="a Teams message picking verses")
    parser.add_argument("--result", default="verse.json", help="where verse writes its answers and changes")
    args = parser.parse_args()
    commands = {"render": cmd_render, "drafts": cmd_drafts, "redo": cmd_redo, "prune": cmd_prune,
                "preview": cmd_preview, "status-page": cmd_status_page, "verse": cmd_verse,
                "verse-apply": cmd_verse_apply, "verse-reply": cmd_verse_reply, "notify": cmd_notify}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
