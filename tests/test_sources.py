"""Parsing tests against small hand-written pages shaped like the real sites."""

from datetime import date

import pytest

from daily_verse import sources
from daily_verse.__main__ import caption
from daily_verse.render import build_html

DAY = date(2026, 10, 15)


def dailyverses_page(text: str, path: str, ref: str, prefix: str = "", translation: str = "kjv") -> str:
    return (
        f'<a href="https://www.facebook.com/sharer/sharer.php?u=https://dailyverses.net{prefix}'
        f'/2026/10/15/{translation}">share</a>'
        f'<div class="b1"><span class="v1">{text}</span><div class="vr">'
        f'<a href="{path}" class="vc">{ref}</a> <a href="/joy/kjv" class="t">joy</a></div>'
    )


def test_clean_keeps_small_caps_lord_and_joins_lines() -> None:
    raw = 'The L<span style="font-variant:all-small-caps">ord</span> is my shepherd;<br> I shall not want.'
    assert sources.clean(raw) == "The LORD is my shepherd; I shall not want."


def test_parse_dailyverses() -> None:
    page = dailyverses_page("I have rejoiced,<br> as much as in all riches.", "/psalms/119/14/kjv", "Psalm 119:14")
    assert sources.parse_dailyverses(page, DAY, "", "kjv") == (
        "Psalm 119:14",
        "/psalms/119/14/kjv",
        "I have rejoiced, as much as in all riches.",
    )


def test_parse_dailyverses_refuses_a_different_day() -> None:
    page = dailyverses_page("text", "/john/4/14/kjv", "John 4:14")
    with pytest.raises(sources.SourceError, match="no verse"):
        sources.parse_dailyverses(page, date(2026, 10, 16), "", "kjv")


def test_parse_dailyverses_reports_layout_changes() -> None:
    page = "dailyverses.net/2026/10/15/kjv <p>redesigned</p>"
    with pytest.raises(sources.SourceError, match="layout changed"):
        sources.parse_dailyverses(page, DAY, "", "kjv")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/psalms/23/1-2/kjv", ("psalms", 23, 1, 2)),
        ("/john/4/14", ("john", 4, 14, 14)),
        ("/de/johannes/4/14/lu12", ("johannes", 4, 14, 14)),
    ],
)
def test_parse_path(path: str, expected: tuple) -> None:
    assert sources.parse_path(path) == expected


def test_parse_path_rejects_cross_chapter_ranges() -> None:
    with pytest.raises(sources.SourceError):
        sources.parse_path("/john/3/16-4/1/kjv")


@pytest.mark.parametrize(
    ("slug", "book"),
    [
        ("john", "John"),
        ("1-timothy", "I_Timothy"),
        ("2-corinthians", "II_Corinthians"),
        ("3-john", "III_John"),
        ("psalms", "Psalms"),
        ("song-of-songs", "Song_of_Solomon"),
        ("isaiah", "Isaiah"),
    ],
)
def test_tamil_book(slug: str, book: str) -> None:
    assert sources.tamil_book(slug) == book


def test_every_tamil_book_maps_to_itself() -> None:
    assert len(sources.TAMIL_BOOKS) == 66
    for book in sources.TAMIL_BOOKS:
        assert sources.tamil_book(book) == book


def test_parse_tamil_joins_a_verse_range() -> None:
    page = (
        "<title>சங்கீதம் 23 — Tamil Bible</title>"
        + "".join(
            f'<div class="verse-row" id="v{n}"><div class="verse-num">{n}</div>'
            f'<div class="verse-content"><div class="verse-tamil">வசனம் {n}.</div></div></div>'
            for n in (1, 2, 3)
        )
    )
    assert sources.parse_tamil(page, 23, 1, 2) == ("சங்கீதம் 23:1-2", "வசனம் 1. வசனம் 2.")
    assert sources.parse_tamil(page, 23, 3, 3) == ("சங்கீதம் 23:3", "வசனம் 3.")


def test_parse_tamil_missing_verse() -> None:
    page = "<title>யோவான் 4 — Tamil Bible</title>"
    with pytest.raises(sources.SourceError, match="no verse 4:14"):
        sources.parse_tamil(page, 4, 14, 14)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [("3 Mose 20:26", "3. Mose 20,26"), ("Psalm 119:14", "Psalm 119,14"), ("1 Korinther 13:4-7", "1. Korinther 13,4-7")],
)
def test_german_reference(ref: str, expected: str) -> None:
    assert sources.german_reference(ref) == expected


def test_slide_escapes_verse_text() -> None:
    page = build_html(sources.Verse("en", "John 4:14", "<script>alert(1)</script>"), DAY)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "Thursday, 15 October 2026" in page


def test_caption_lists_all_three_references() -> None:
    verses = {
        "ta": {"reference": "யோவான் 4:14"},
        "en": {"reference": "John 4:14"},
        "de": {"reference": "Johannes 4,14"},
    }
    assert "யோவான் 4:14 · John 4:14 · Johannes 4,14" in caption(verses)
