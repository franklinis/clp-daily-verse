"""Looking up the church's own verse picks in the bundled texts (no network)."""

import pytest

from daily_verse import bible, captions, custom
from daily_verse.bible import BibleError, Passage


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("Psalm 23:1", Passage(19, 23, 1, 1)),
        ("ps 23:1-3", Passage(19, 23, 1, 3)),
        ("Psalms 23.1", Passage(19, 23, 1, 1)),
        ("1 Cor 13:4–7", Passage(46, 13, 4, 7)),
        ("I Corinthians 13:4", Passage(46, 13, 4, 4)),
        ("1. Korinther 13,4", Passage(46, 13, 4, 4)),
        ("Römer 8,38-39", Passage(45, 8, 38, 39)),
        ("Roemer 8:28", Passage(45, 8, 28, 28)),
        ("Joh 3,16", Passage(43, 3, 16, 16)),
        ("Matth 5:9", Passage(40, 5, 9, 9)),
        ("Jude 24", Passage(65, 1, 24, 24)),
        ("Offb 21:4", Passage(66, 21, 4, 4)),
    ],
)
def test_parse(reference: str, expected: Passage) -> None:
    assert bible.parse(reference) == expected


def test_german_numbering_is_mapped_to_english() -> None:
    # Luther counts the title of Psalm 51 as verses 1-2, and Joel 3 is English 2:28-32.
    assert bible.parse("Psalm 51,12") == Passage(19, 51, 10, 10)
    assert bible.parse("Joel 3,1") == Passage(29, 2, 28, 28)
    with pytest.raises(BibleError, match="title"):
        bible.parse("Psalm 51,1")


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ("Psalm 23", "add the verse"),
        ("Hezekiah 1:1", "don't know the book"),
        ("Psalm 23:7", "verses 1-6"),
        ("Genesis 51:1", "50 chapters"),
        ("Psalm 119:1-20", "at most"),
        ("23:1", "couldn't read"),
    ],
)
def test_parse_explains_problems(reference: str, message: str) -> None:
    with pytest.raises(BibleError, match=message):
        bible.parse(reference)


def test_english_and_german_text_and_references() -> None:
    passage = bible.parse("Psalm 51:10")
    assert passage.english == "Psalm 51:10"
    assert bible.text("kjv", passage) == "Create in me a clean heart, O God; and renew a right spirit within me."
    assert bible.german_reference(passage) == "Psalm 51,12"
    assert bible.text("lu12", passage).startswith("Schaffe in mir, Gott, ein reines Herz")


def test_psalm_titles_are_left_out() -> None:
    passage = bible.parse("Psalm 23:1")
    assert bible.text("kjv", passage) == "The LORD is my shepherd; I shall not want."
    assert bible.text("lu12", passage) == "Der HERR ist mein Hirte; mir wird nichts mangeln."
    assert bible.german_reference(bible.parse("Psalm 3:1")) == "Psalm 3,2"
    assert bible.text("lu12", bible.parse("Psalm 3:1")).startswith("Ach HERR")


def test_ranges_and_books_with_german_names() -> None:
    passage = bible.parse("Romans 8:38-39")
    assert bible.german_reference(passage) == "Römer 8,38-39"
    assert bible.text("kjv", passage).endswith("which is in Christ Jesus our Lord.")
    assert bible.german_reference(bible.parse("Gen 1:1")) == "1. Mose 1,1"


def test_long_passages_are_refused() -> None:
    bible.check_length(bible.parse("John 3:16"))
    with pytest.raises(BibleError, match="characters"):
        bible.check_length(bible.parse("Esther 8:9"))


def test_credits_drop_dailyverses_on_the_church_s_own_picks() -> None:
    line = "Bibel: Lutherbibel 1912 · Versauswahl: DailyVerses.net"
    assert captions.credits(line) == line
    assert captions.credits(line, selection=False) == "Bibel: Lutherbibel 1912"
    assert captions.credits(captions.CREDITS, selection=False).endswith("Lutherbibel 1912")


def test_custom_verses_round_trip(tmp_path) -> None:
    from datetime import date

    path = tmp_path / "custom-verses.csv"
    assert custom.load(path) == {}
    picks = {date(2026, 10, 21): custom.Entry("Romans 8:28", "hope, trust"), date(2026, 10, 20): custom.Entry("Psalm 23:1")}
    custom.save(picks, path)
    assert path.read_text().splitlines() == [
        "date,reference,theme", "2026-10-20,Psalm 23:1,", '2026-10-21,Romans 8:28,"hope, trust"',
    ]
    assert custom.load(path) == picks
    assert picks[date(2026, 10, 21)].topics == ["hope", "trust"]
