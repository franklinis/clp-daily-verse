"""Sending a day to the church app for approval (no network)."""

from datetime import date

from daily_verse import app, teams
from daily_verse.__main__ import app_post, draft_jobs, language_video_name
from tests.test_drafts import FEED, VIDEO, manifest


def test_off_unless_switched_on(monkeypatch) -> None:
    monkeypatch.delenv("POST_TARGET", raising=False)
    assert not app.enabled()
    monkeypatch.setenv("POST_TARGET", "app")
    assert app.enabled()


def test_posts_are_named_by_kind_and_service_and_go_unchanged() -> None:
    day = date(2026, 10, 16)
    videos = {lang: language_video_name(day, lang) for lang in ("ta", "en", "de")}
    jobs = draft_jobs(manifest(videos=videos), "https://m", FEED, VIDEO)
    posts = [app_post(job) for job in jobs]
    keys = [p["key"] for p in posts]
    assert keys[:2] == ["carousel:facebook", "carousel:instagram"]
    assert "video-de:youtube" in keys and len(set(keys)) == len(keys) == 11
    youtube_de = next(p for p in posts if p["key"] == "video-de:youtube")
    job = next(j for j in jobs if j.key == "video-de:yt1")
    assert youtube_de == {"key": "video-de:youtube", "channel": "youtube", "text": job.text,
                          "assets": job.assets, "metadata": job.metadata}


def test_review_link_and_teams_card_point_to_the_app(monkeypatch) -> None:
    monkeypatch.setenv("APP_URL", "https://app.example.test/")
    day = date(2026, 10, 30)
    assert app.batch_key(day) == "daily-verse:2026-10-30"
    assert app.review_url(day) == "https://app.example.test/en/admin/social/batch/daily-verse%3A2026-10-30"
    card = teams.ready_card(day, "Psalm 23:1", "https://m/en.png", 11, False, app.review_url(day))
    text = str(card)
    assert "in the church app" in text and "Open in the app" in text and "publish.buffer.com" not in text
    assert "publish.buffer.com" in str(teams.ready_card(day, "Psalm 23:1", "https://m/en.png", 11, False))


def test_days_with_buffer_drafts_stay_in_buffer(monkeypatch, tmp_path) -> None:
    import argparse
    import json

    from daily_verse import __main__ as main

    path = tmp_path / "16.json"
    path.write_text(json.dumps(manifest(buffer={"fb1": "buf-1"})), encoding="utf-8")
    monkeypatch.setattr(main, "manifest_path", lambda day: path)
    monkeypatch.setattr(main, "days", lambda start, count: [date(2026, 10, 16)])
    sent = []
    monkeypatch.setattr(app, "send_day", lambda *a: sent.append(a) or False)
    assert main.send_to_app(argparse.Namespace(start=None, days=1), FEED, VIDEO) == 0
    assert sent == []


def test_picks_from_the_app_replace_the_automatic_verse(monkeypatch, tmp_path) -> None:
    import argparse
    from datetime import datetime as real_datetime

    from daily_verse import __main__ as main
    from daily_verse import custom, sources

    csv_path = tmp_path / "custom-verses.csv"
    custom.save({date(2026, 10, 1): custom.Entry("John 3:16")}, csv_path)  # a past day stays
    monkeypatch.setattr(custom, "PATH", csv_path)
    monkeypatch.setattr(custom.load, "__defaults__", (csv_path,))
    monkeypatch.setattr(custom.save, "__defaults__", (csv_path,))
    monkeypatch.setenv("POST_TARGET", "app")

    class Today(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 10, 30, 9, 0, tzinfo=tz)

    monkeypatch.setattr(main, "datetime", Today)
    monkeypatch.setattr(app, "fetch_picks", lambda: [
        {"date": "2026-11-02", "reference": "Psalm 23,1", "theme": "trust"},
        {"date": "2026-11-03", "reference": "Nowhere 99:99", "theme": ""},
        {"date": "2026-11-01", "reference": "Psalm 1:1", "theme": ""},  # a Sunday
    ])

    def fetch(reference, topics=None):
        if reference.startswith("Nowhere"):
            raise sources.SourceError("No such book")
        verse = sources.Verse(lang="en", reference="Psalm 23:1", text="The LORD is my shepherd")
        return {"en": verse}, []

    monkeypatch.setattr(sources, "fetch_custom", fetch)
    reported = []
    monkeypatch.setattr(app, "send_pick_results", reported.extend)
    assert main.cmd_pull_picks(argparse.Namespace()) == 0
    assert custom.load(csv_path) == {
        date(2026, 10, 1): custom.Entry("John 3:16"),
        date(2026, 11, 2): custom.Entry("Psalm 23:1", "trust"),
    }
    assert {r["date"]: r.get("found") or r.get("problem") for r in reported} == {
        "2026-11-02": "Psalm 23:1",
        "2026-11-03": "No such book",
        "2026-11-01": "Nothing is posted on Sundays.",
    }


def test_stops_the_run_if_the_app_cant_be_reached(monkeypatch) -> None:
    import argparse

    from daily_verse import __main__ as main

    monkeypatch.setenv("POST_TARGET", "app")

    def down():
        raise app.AppError("HTTP 503")

    monkeypatch.setattr(app, "fetch_picks", down)
    assert main.cmd_pull_picks(argparse.Namespace()) == 1
