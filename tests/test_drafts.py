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
    jobs = draft_jobs(manifest(videos=videos, narrated=True), "https://m", FEED, VIDEO, ai_label=True)
    assert len(jobs) == 2 + 3 * 3
    assert len({job.key for job in jobs}) == len(jobs)
    youtube_de = next(job for job in jobs if job.key == "video-de:yt1")
    assert youtube_de.metadata["youtube"]["title"] == "Psalm 119,14 | Gottes Wort für heute #shorts"
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


def test_narrated_videos_are_unlabelled_unless_switched_on() -> None:
    narrated = manifest(videos={"en": "2026/10/16-en.mp4"}, narrated=True)
    jobs = draft_jobs(narrated, "https://m", [], VIDEO)
    assert all(not job.metadata[job.service].get("isAiGenerated", False) for job in jobs)


def test_sundays_are_skipped() -> None:
    from datetime import date

    from daily_verse.__main__ import days, posting_day

    assert not posting_day(date(2026, 10, 18))  # Sunday
    assert days(date(2026, 10, 16), 4) == [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 19)]


def test_new_background_changes_every_link() -> None:
    jobs = draft_jobs(manifest(videos={"en": "2026/10/16-en.mp4"}, revision=2), "https://m", FEED, VIDEO)
    assert all(url.endswith("?v=2") for job in jobs for url in job.urls)
    assert jobs[0].assets[0]["image"]["url"] == "https://m/2026/10/16-ta.png?v=2"


def test_update_post_edits_in_place(monkeypatch) -> None:
    import io
    import json

    from daily_verse import buffer

    sent = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return Response(b'{"data": {"editPost": {"post": {"id": "p1", "status": "draft"}}}}')

    monkeypatch.setattr(buffer.urllib.request, "urlopen", fake_urlopen)
    assert buffer.update_post("key", "p1", "text", [{"image": {"url": "u"}}], {"facebook": {"type": "post"}}) == "draft"
    assert "editPost" in sent[0]["query"]
    assert sent[0]["variables"]["input"] == {
        "id": "p1", "text": "text", "assets": [{"image": {"url": "u"}}], "metadata": {"facebook": {"type": "post"}}
    }  # no time or approval fields, so both stay as they are


def test_drafts_are_refreshed_once_after_a_new_background(tmp_path, monkeypatch) -> None:
    import argparse
    from datetime import date
    import json

    from daily_verse import __main__ as cli

    day = date(2026, 10, 16)
    path = tmp_path / "2026/10/16.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest(videos={"en": "2026/10/16-en.mp4"}, revision=1, refresh=True,
                                        buffer={"fb1": "p-carousel", "video-en:yt1": "p-short"})))
    monkeypatch.setattr(cli, "IMAGES", tmp_path)
    monkeypatch.setattr(cli, "wait_until_public", lambda url: None)
    updated, created = [], []
    monkeypatch.setattr(cli.buffer, "update_post", lambda key, pid, *a: updated.append(pid) or "draft")
    monkeypatch.setattr(cli.buffer, "create_draft", lambda key, cid, *a: created.append(cid) or f"new-{cid}")
    monkeypatch.setenv("BUFFER_API_KEY", "k")
    monkeypatch.setenv("BUFFER_CHANNELS", "fb1:facebook")
    monkeypatch.setenv("BUFFER_VIDEO_CHANNELS", "yt1:youtube")
    args = argparse.Namespace(start=day, days=1)
    assert cli.cmd_drafts(args) == 0
    assert sorted(updated) == ["p-carousel", "p-short"] and created == []
    assert json.loads(path.read_text())["refresh"] is False
    updated.clear()
    cli.cmd_drafts(args)
    assert updated == []  # nothing left to refresh
