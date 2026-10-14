"""Reading verse picks from a Teams message and answering them (no network)."""

from datetime import date

import pytest

from daily_verse import __main__ as main
from daily_verse import custom, sources, teams
from daily_verse.teams import Command, MessageError

TODAY = date(2026, 10, 14)  # a Wednesday


def test_message_lines_drop_the_mention_and_html() -> None:
    text = "<at>DailyVerse</at>&nbsp;20.10 Psalm 23:1<br>21.10 R&ouml;mer 8,28</p><p>list</p>"
    assert teams.message_lines(text) == ["20.10 Psalm 23:1", "21.10 Römer 8,28", "list"]


@pytest.mark.parametrize(
    ("text", "day", "rest"),
    [
        ("20.10 Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("20.10. Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("20.10.2026: Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("2026-10-20 - Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("20/10 Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("20 Oct Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("20. Oktober Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("October 20th Psalm 23:1", date(2026, 10, 20), "Psalm 23:1"),
        ("3.1 Psalm 23:1", date(2027, 1, 3), "Psalm 23:1"),  # already past this year
        ("tomorrow Psalm 23:1", date(2026, 10, 15), "Psalm 23:1"),
        ("übermorgen Psalm 23:1", date(2026, 10, 16), "Psalm 23:1"),
        ("Montag Psalm 23:1", date(2026, 10, 19), "Psalm 23:1"),
        ("Wednesday Psalm 23:1", date(2026, 10, 21), "Psalm 23:1"),  # next week, not today
    ],
)
def test_parse_date(text: str, day: date, rest: str) -> None:
    assert teams.parse_date(text, TODAY) == (day, rest)


def test_parse_date_problems() -> None:
    with pytest.raises(MessageError, match="Start the line with a date"):
        teams.parse_date("Psalm 23:1", TODAY)
    with pytest.raises(MessageError, match="doesn't exist"):
        teams.parse_date("31.11 Psalm 23:1", TODAY)


def test_parse_line() -> None:
    assert teams.parse_line("21.10 Römer 8,28 theme: hope, trust", TODAY) == Command(
        "set", "21.10 Römer 8,28 theme: hope, trust", date(2026, 10, 21), "Römer 8,28", "hope, trust")
    assert teams.parse_line("21.10 Psalm 23:1 | shepherd", TODAY).theme == "shepherd"
    assert teams.parse_line("clear 20.10", TODAY) == Command("clear", "clear 20.10", date(2026, 10, 20))
    assert teams.parse_line("List", TODAY).kind == "list"
    assert teams.parse_line("hilfe", TODAY).kind == "help"
    with pytest.raises(MessageError, match="Add the verse"):
        teams.parse_line("20.10", TODAY)


def test_parse_message_keeps_errors_per_line() -> None:
    results = teams.parse_message("<at>DailyVerse</at> 20.10 Psalm 23:1<br>whenever John 3:16", TODAY)
    assert isinstance(results[0], Command) and isinstance(results[1], MessageError)
    assert teams.parse_message("<at>DailyVerse</at>", TODAY) == [Command("help", "")]


VERSES = {lang: sources.Verse(lang, f"{lang} ref", f"{lang} text") for lang in ("ta", "en", "de")}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """No Tamil lookups and no media folder."""
    monkeypatch.setattr(main, "IMAGES", tmp_path)
    monkeypatch.setattr(sources, "fetch_custom", lambda reference, topics=None: (
        {**VERSES, "en": sources.Verse("en", "Psalm 23:1", "The LORD is my shepherd")}, []))


def test_check_command_set(offline) -> None:
    result = main.check_command(Command("set", "", date(2026, 10, 16), "ps 23:1", "rest"), {}, TODAY, None)
    assert result["title"] == "✅ Fri 16 Oct: Psalm 23:1"
    assert result["change"] == {"date": "2026-10-16", "reference": "Psalm 23:1", "theme": "rest"}
    assert result["message"] == "Slides and Buffer drafts follow in a few minutes."
    later = main.check_command(Command("set", "", date(2026, 10, 30), "Psalm 23:1"), {}, TODAY, None)
    assert later["message"] == "Slides and Buffer drafts are made on Tue 27 Oct."
    same = main.check_command(Command("set", "", date(2026, 10, 30), "Psalm 23:1"),
                              {date(2026, 10, 30): custom.Entry("Psalm 23:1")}, TODAY, None)
    assert "change" not in same


@pytest.mark.parametrize(
    ("day", "message"),
    [(date(2026, 10, 14), "today or already past"), (date(2026, 10, 18), "Nothing is posted on Sundays")],
)
def test_check_command_refuses_days(offline, day: date, message: str) -> None:
    result = main.check_command(Command("set", "", day, "Psalm 23:1"), {}, TODAY, None)
    assert result["error"] and message in result["message"] and "change" not in result


def test_check_command_refuses_approved_days(offline, monkeypatch) -> None:
    import json

    path = main.manifest_path(date(2026, 10, 16))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"buffer": {"fb": "1", "ig": "2"}}))
    monkeypatch.setattr(main.buffer, "post_status", lambda key, post_id: "scheduled" if post_id == "2" else "draft")
    result = main.check_command(Command("set", "", date(2026, 10, 16), "Psalm 23:1"), {}, TODAY, "key")
    assert "already approved in Buffer" in result["message"]
    monkeypatch.setattr(main.buffer, "post_status", lambda key, post_id: "draft")
    result = main.check_command(Command("set", "", date(2026, 10, 16), "Psalm 23:1"), {}, TODAY, "key")
    assert result["message"] == "That day's slides and Buffer drafts switch over in a few minutes."


def test_check_command_list_and_clear(offline) -> None:
    picks = {date(2026, 10, 10): custom.Entry("John 3:16"), date(2026, 10, 20): custom.Entry("Psalm 23:1", "rest")}
    listed = main.check_command(Command("list", ""), picks, TODAY, None)
    assert listed["message"] == "- Tue 20 Oct: Psalm 23:1 (theme: rest)"
    cleared = main.check_command(Command("clear", "", date(2026, 10, 20)), picks, TODAY, None)
    assert cleared["change"] == {"date": "2026-10-20", "clear": True}
    nothing = main.check_command(Command("clear", "", date(2026, 10, 21)), picks, TODAY, None)
    assert "change" not in nothing


def test_results_card() -> None:
    message = teams.results_card([
        {"title": "✅ Fri 16 Oct: Psalm 23:1", "verses": {k: v.__dict__ for k, v in VERSES.items()}, "message": "ok"},
        {"title": "⚠️ I couldn't read that line", "message": "nope", "error": True},
    ])
    content = message["attachments"][0]["content"]
    texts = [block.get("text") for block in content["body"]]
    assert "**en ref** en text" in texts and "nope" in texts
    assert content["body"][-1]["color"] == "Attention"
