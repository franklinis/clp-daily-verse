"""Look up any verse by reference, for days the church picks its own verse.

English (King James Version) and German (Lutherbibel 1912) come from the
public-domain texts bundled in daily_verse/bible/ (see tools/build_bible.py);
the Tamil text comes from tamil-bible.com, like on DailyVerses.net days.

References can be typed in English or German: "Psalm 23:1", "Ps 23:1-3",
"1 Cor 13:4", "Römer 8,38-39", "1. Mose 1,1". A colon means English verse
numbers; a comma means German (Luther) numbers, which differ in many Psalms,
e.g. Psalm 51:10 = Psalm 51,12.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import gzip
import json
from pathlib import Path
import re

DATA = Path(__file__).parent / "bible"
MAX_VERSES = 6
MAX_CHARACTERS = 450  # longer passages don't fit a slide

# (English name, German name, other names and abbreviations) in canonical order.
BOOKS = [
    ("Genesis", "1. Mose", "gen gn 1mo 1mos"),
    ("Exodus", "2. Mose", "ex exo exod 2mo 2mos"),
    ("Leviticus", "3. Mose", "lev lv 3mo 3mos"),
    ("Numbers", "4. Mose", "num nm numb 4mo 4mos"),
    ("Deuteronomy", "5. Mose", "deut dt deu 5mo 5mos deuteronomium"),
    ("Joshua", "Josua", "josh jos"),
    ("Judges", "Richter", "judg jdg ri"),
    ("Ruth", "Rut", "rt"),
    ("1 Samuel", "1. Samuel", "1sam 1sa 1sm"),
    ("2 Samuel", "2. Samuel", "2sam 2sa 2sm"),
    ("1 Kings", "1. Könige", "1kgs 1ki 1kg 1kon 1koenige"),
    ("2 Kings", "2. Könige", "2kgs 2ki 2kg 2kon 2koenige"),
    ("1 Chronicles", "1. Chronik", "1chron 1chr 1ch"),
    ("2 Chronicles", "2. Chronik", "2chron 2chr 2ch"),
    ("Ezra", "Esra", "ezr esr"),
    ("Nehemiah", "Nehemia", "neh"),
    ("Esther", "Ester", "esth est"),
    ("Job", "Hiob", "hi ijob"),
    ("Psalm", "Psalm", "ps psa pss psalms psalmen"),
    ("Proverbs", "Sprüche", "prov prv pro spr sprueche"),
    ("Ecclesiastes", "Prediger", "eccl ecc eccles qoh pred kohelet"),
    ("Song of Solomon", "Hoheslied", "song songofsongs sos hld hohelied"),
    ("Isaiah", "Jesaja", "isa jes"),
    ("Jeremiah", "Jeremia", "jer"),
    ("Lamentations", "Klagelieder", "lam klgl"),
    ("Ezekiel", "Hesekiel", "ezek eze ezk hes ez ezechiel"),
    ("Daniel", "Daniel", "dan dn"),
    ("Hosea", "Hosea", "hos"),
    ("Joel", "Joel", "jl"),
    ("Amos", "Amos", "am"),
    ("Obadiah", "Obadja", "obad ob obd"),
    ("Jonah", "Jona", "jon"),
    ("Micah", "Micha", "mic mi"),
    ("Nahum", "Nahum", "nah"),
    ("Habakkuk", "Habakuk", "hab"),
    ("Zephaniah", "Zefanja", "zeph zep zef zephanja"),
    ("Haggai", "Haggai", "hag hagg"),
    ("Zechariah", "Sacharja", "zech zec sach"),
    ("Malachi", "Maleachi", "mal"),
    ("Matthew", "Matthäus", "matt mt mat matthaeus"),
    ("Mark", "Markus", "mk mrk mar"),
    ("Luke", "Lukas", "lk luk"),
    ("John", "Johannes", "jn jhn joh"),
    ("Acts", "Apostelgeschichte", "act apg"),
    ("Romans", "Römer", "rom ro rm roemer"),
    ("1 Corinthians", "1. Korinther", "1cor 1co 1kor"),
    ("2 Corinthians", "2. Korinther", "2cor 2co 2kor"),
    ("Galatians", "Galater", "gal"),
    ("Ephesians", "Epheser", "eph"),
    ("Philippians", "Philipper", "phil php"),
    ("Colossians", "Kolosser", "col kol"),
    ("1 Thessalonians", "1. Thessalonicher", "1thess 1th 1thes"),
    ("2 Thessalonians", "2. Thessalonicher", "2thess 2th 2thes"),
    ("1 Timothy", "1. Timotheus", "1tim 1ti"),
    ("2 Timothy", "2. Timotheus", "2tim 2ti"),
    ("Titus", "Titus", "tit"),
    ("Philemon", "Philemon", "philem phlm phm"),
    ("Hebrews", "Hebräer", "heb hebr hebraeer"),
    ("James", "Jakobus", "jas jak jm"),
    ("1 Peter", "1. Petrus", "1pet 1pe 1pt 1petr"),
    ("2 Peter", "2. Petrus", "2pet 2pe 2pt 2petr"),
    ("1 John", "1. Johannes", "1jn 1jo 1joh"),
    ("2 John", "2. Johannes", "2jn 2jo 2joh"),
    ("3 John", "3. Johannes", "3jn 3jo 3joh"),
    ("Jude", "Judas", "jud"),
    ("Revelation", "Offenbarung", "rev re offb apk revelations"),
]

_REFERENCE = re.compile(
    r"^(?P<book>(?:[1-3]\.?\s*)?[^\d]+?)\s*(?P<chapter>\d+)"
    r"(?:\s*(?P<sep>[:,.])\s*(?P<first>\d+)(?:\s*[-–—]\s*(?P<last>\d+))?)?\s*$"
)


class BibleError(Exception):
    """The reference could not be read or is not in the Bible."""


@dataclass(frozen=True)
class Passage:
    """Verses first..last of one chapter, in English verse numbering; book is 1-66."""

    book: int
    chapter: int
    first: int
    last: int

    @property
    def english(self) -> str:
        verses = str(self.first) if self.first == self.last else f"{self.first}-{self.last}"
        return f"{BOOKS[self.book - 1][0]} {self.chapter}:{verses}"


def _key(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"^(iii|3rd|third)\b\.?", "3", name)
    name = re.sub(r"^(ii|2nd|second)\b\.?", "2", name)
    name = re.sub(r"^(i|1st|first)\b\.?", "1", name)
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        name = name.replace(umlaut, plain)
    return re.sub(r"[^a-z0-9]", "", name)


@cache
def _names() -> dict[str, int]:
    names = {}
    for index, (english, german, others) in enumerate(BOOKS, start=1):
        for name in (english, german, *others.split()):
            names[_key(name)] = index
    return names


def find_book(name: str) -> int:
    """Book number (1-66) for an English or German name or abbreviation, or a unique beginning of one."""
    key = _key(name)
    names = _names()
    if key in names:
        return names[key]
    matches = {index for full, index in names.items() if len(key) >= 3 and full.startswith(key)}
    if len(matches) == 1:
        return matches.pop()
    raise BibleError(f"I don't know the book “{name.strip()}”")


@cache
def _load(name: str) -> dict:
    return json.loads(gzip.decompress((DATA / f"{name}.json.gz").read_bytes()))


def _verse_count(book: int, chapter: int) -> int:
    chapters = _load("kjv")["books"][book - 1]
    if not 1 <= chapter <= len(chapters):
        raise BibleError(f"{BOOKS[book - 1][0]} has {len(chapters)} chapters")
    return len(chapters[chapter - 1])


def _to_german(book: int, chapter: int, verse: int) -> tuple[int, int]:
    mapped = _load("lu12")["refs"].get(f"{book}:{chapter}:{verse}")
    if not mapped:
        return chapter, verse
    c, v = mapped.split(":")
    return int(c), int(v)


def _from_german(book: int, chapter: int, verse: int) -> tuple[int, int]:
    """English numbering for a German (Luther) chapter and verse."""
    for key, mapped in _load("lu12")["refs"].items():
        b, c, v = (int(n) for n in key.split(":"))
        if b == book and mapped == f"{chapter}:{verse}":
            return c, v
    if f"{book}:{chapter}:{verse}" in _load("lu12")["refs"]:
        # That number is used differently in German, e.g. the title verse of a psalm.
        raise BibleError(f"{BOOKS[book - 1][1]} {chapter},{verse} has no English verse (in Psalms it's the title)")
    return chapter, verse


def parse(reference: str) -> Passage:
    """Read a typed reference into English verse numbering."""
    match = _REFERENCE.match(reference.strip())
    if not match:
        raise BibleError(f"I couldn't read “{reference.strip()}”; write it like “Psalm 23:1” or “Römer 8,38-39”")
    book = find_book(match["book"])
    chapter = int(match["chapter"])
    if match["first"] is None:
        if len(_load("kjv")["books"][book - 1]) != 1:
            raise BibleError(f"Please add the verse, e.g. “{BOOKS[book - 1][0]} {chapter}:1”")
        chapter, first, last = 1, chapter, chapter  # "Jude 24" means Jude 1:24
    else:
        first = int(match["first"])
        last = int(match["last"] or first)
    german = match["sep"] == ","
    if german:
        c1, first = _from_german(book, chapter, first)
        c2, last = _from_german(book, chapter, last)
        if c1 != c2:
            raise BibleError("Please keep the verses within one chapter")
        chapter = c1
    count = _verse_count(book, chapter)
    if not 1 <= first <= last <= count:
        raise BibleError(f"{BOOKS[book - 1][0]} {chapter} has verses 1-{count}")
    if last - first + 1 > MAX_VERSES:
        raise BibleError(f"That's {last - first + 1} verses; please pick at most {MAX_VERSES}")
    return Passage(book, chapter, first, last)


def text(translation: str, passage: Passage) -> str:
    verses = _load(translation)["books"][passage.book - 1][passage.chapter - 1]
    return " ".join(verses[passage.first - 1:passage.last])


def german_reference(passage: Passage) -> str:
    """"Psalm 51,12", "Joel 3,1-5", in Luther's numbering."""
    c1, v1 = _to_german(passage.book, passage.chapter, passage.first)
    c2, v2 = _to_german(passage.book, passage.chapter, passage.last)
    name = BOOKS[passage.book - 1][1]
    if c1 != c2:
        return f"{name} {c1},{v1}–{c2},{v2}"
    return f"{name} {c1},{v1}" if v1 == v2 else f"{name} {c1},{v1}-{v2}"


def check_length(passage: Passage) -> None:
    length = len(text("kjv", passage))
    if length > MAX_CHARACTERS:
        raise BibleError(f"{passage.english} is {length} characters; slides fit about {MAX_CHARACTERS}")
