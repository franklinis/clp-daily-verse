"""Which Buffer drafts a day gets (no network)."""

from daily_verse.__main__ import draft_jobs, language_video_name

FEED = [("fb1", "facebook"), ("ig1", "instagram")]
VIDEO = [("fb1", "facebook"), ("ig1", "instagram"), ("yt1", "youtube")]
VERSES = {
    "ta": {"lang": "ta", "reference": "சங்கீதம் 119:14", "text": "களிகூருகிறேன்."},
    "en": {"lang": "en", "reference": "Psalm 119:14", "text": "I have rejoiced."},
    "de": {"lang": "de", "reference": "Psalm 119,14", "text": "Ich freue mich."},
}


def manifest(**extra: object) -> dict:
    return {
        "verses": VERSES,
        "images": {lang: f"2026/10/16-{lang}.png" for lang in ("ta", "en", "de")},
        "buffer": {},
        **extra,
    }


def test_carousel_plus_a_video_per_language_per_channel() -> None:
    from datetime import date

    day = date(2026, 10, 16)
    videos = {lang: language_video_name(day, lang) for lang in ("ta", "en", "de")}
    assert videos["de"] == "2026/10/16-de.mp4"
    jobs = draft_jobs(manifest(videos=videos, narrated=True), "https://m", FEED, VIDEO)
    assert len(jobs) == 2 + 3 * 3
    assert len({job.key for job in jobs}) == len(jobs)
    youtube_de = next(job for job in jobs if job.key == "video-de:yt1")
    assert youtube_de.metadata["youtube"]["title"] == "Psalm 119,14 | Vers des Tages #shorts"
    assert youtube_de.metadata["youtube"]["isAiGenerated"] is True
    assert youtube_de.urls == ["https://m/2026/10/16-de.mp4"]
    reel_ta = next(job for job in jobs if job.key == "video-ta:ig1")
    assert reel_ta.metadata == {"instagram": {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}}
    assert "களிகூருகிறேன்" in reel_ta.text and "I have rejoiced" not in reel_ta.text


def test_older_days_keep_only_their_existing_drafts() -> None:
    """14-15 Oct were made with one trilingual video; no per-language drafts are added."""
    jobs = draft_jobs(manifest(video="2026/10/14.mp4"), "https://m", FEED, VIDEO)
    assert [job.kind for job in jobs] == ["carousel", "carousel"]


def test_unnarrated_videos_are_not_labelled_ai() -> None:
    jobs = draft_jobs(manifest(videos={"en": "2026/10/16-en.mp4"}, narrated=False), "https://m", [], VIDEO)
    assert all(not job.metadata.get(job.service, {}).get("isAiGenerated", False) for job in jobs)
