"""Parsing tests against small hand-written pages shaped like the real sites."""

from datetime import date, timedelta

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


def test_background_is_stable_per_day_and_varies_between_days() -> None:
    from daily_verse import background

    assert background.svg(DAY) == background.svg(DAY)
    assert background.svg(DAY) != background.svg(date(2026, 10, 16))


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))],
)
def test_easter(year: int, expected: date) -> None:
    from daily_verse import background

    assert background.easter(year) == expected


@pytest.mark.parametrize(
    ("day", "name"),
    [
        (date(2026, 12, 25), "christmas"),
        (date(2027, 1, 1), "new year"),
        (date(2026, 4, 3), "good friday"),
        (date(2026, 4, 5), "easter"),
        (date(2026, 5, 24), "pentecost"),
        (date(2026, 10, 15), None),
    ],
)
def test_feast_days(day: date, name: str | None) -> None:
    from daily_verse import background

    assert background.feast(day) == name
    if name:
        assert background.palette_for(day).name == name


def test_a_year_of_palettes() -> None:
    """Sundays stay green, every weekday palette gets used, and no palette repeats on consecutive days."""
    from daily_verse import background

    year = [date(2027, 1, 1) + timedelta(days=i) for i in range(365)]
    palettes = [background.palette_for(day) for day in year]
    for day, palette in zip(year, palettes, strict=True):
        if day.weekday() == 6 and not background.feast(day):
            assert palette in background.SUNDAY
    for (day, a), b in zip(zip(year, palettes, strict=True), palettes[1:], strict=False):
        if not (background.feast(day) and a.name in background.FEAST):
            assert a != b, f"{day}: {a.name} two days running"
    used = {p.name for p in palettes}
    assert {p.name for p in background.WEEKDAY} <= used


def test_every_palette_keeps_white_text_readable() -> None:
    """WCAG large-text contrast (3:1) against the ridges and sky, before any darkening."""
    from daily_verse import background

    for palette in background.PALETTES:
        for colour in (palette.far, *palette.sky):
            contrast = 1.05 / (background.luminance(colour) + 0.05)
            assert contrast >= 3.0, f"{palette.name} {colour}: {contrast:.2f}"
