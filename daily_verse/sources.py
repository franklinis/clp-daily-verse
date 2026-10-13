"""Fetch the day's verse in Tamil, English and German.

DailyVerses.net picks the verse and supplies English and German text in
public-domain translations. The Tamil text of the same passage comes from
tamil-bible.com, which follows the English verse numbering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html
import re
import time
import urllib.request

DAILYVERSES = "https://dailyverses.net"
TAMIL_BIBLE = "https://www.tamil-bible.com"
USER_AGENT = "clp-daily-verse/1.0 (+https://github.com/franklinis/clp-daily-verse)"

# Both public domain. DailyVerses.net's "web" (World English Bible) says "Yahweh".
ENGLISH_TRANSLATION = "kjv"
GERMAN_TRANSLATION = "lu12"

# Book parameters used by tamil-bible.com's lookup.php, in canonical order.
TAMIL_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges",
    "Ruth", "I_Samuel", "II_Samuel", "I_Kings", "II_Kings", "I_Chronicles",
    "II_Chronicles", "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song_of_Solomon", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel",
    "Daniel", "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "I_Corinthians", "II_Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "I_Thessalonians", "II_Thessalonians", "I_Timothy",
    "II_Timothy", "Titus", "Philemon", "Hebrews", "James", "I_Peter", "II_Peter",
    "I_John", "II_John", "III_John", "Jude", "Revelation",
]
_ALIASES = {"songofsongs": "songofsolomon", "psalm": "psalms"}

_VERSE = re.compile(
    r'<span class="v1">(?P<text>.*?)</span><div class="vr">'
    r'<a href="(?P<path>[^"]+)" class="vc">(?P<ref>[^<]+)</a>',
    re.S,
)
_PATH = re.compile(r"^/(?:de/)?(?P<book>[a-z0-9-]+)/(?P<chapter>\d+)/(?P<verses>\d+(?:-\d+)?)(?:/[a-z0-9]+)?$")


class SourceError(Exception):
    """A source page was missing or did not look as expected."""


@dataclass(frozen=True)
class Verse:
    """One language's slide: display reference and text."""

    lang: str
    reference: str
    text: str


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    time.sleep(1)  # Be gentle with small, volunteer-run sites.
    return body


def clean(fragment: str) -> str:
    """Turn a verse's HTML into plain text, keeping KJV's small-caps LORD."""
    fragment = re.sub(
        r'<span[^>]*small-caps[^>]*>(.*?)</span>',
        lambda m: m.group(1).upper(),
        fragment,
        flags=re.S,
    )
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_dailyverses(page: str, day: date, lang_prefix: str, translation: str) -> tuple[str, str, str]:
    """Return (reference, path, text) from a DailyVerses.net day page."""
    # Unpublished future dates fall back to today's verse; refuse those.
    if f"dailyverses.net{lang_prefix}/{day:%Y/%m/%d}/{translation}" not in page:
        raise SourceError(f"DailyVerses.net has no verse for {day} yet")
    match = _VERSE.search(page)
    if not match:
        raise SourceError("DailyVerses.net page layout changed: verse not found")
    return html.unescape(match["ref"]).strip(), match["path"], clean(match["text"])


def parse_path(path: str) -> tuple[str, int, int, int]:
    """Split "/psalms/23/1-2/kjv" into ("psalms", 23, 1, 2)."""
    match = _PATH.match(path)
    if not match:
        raise SourceError(f"Unexpected verse path {path!r}")
    first, _, last = match["verses"].partition("-")
    return match["book"], int(match["chapter"]), int(first), int(last or first)


def _book_key(name: str) -> str:
    name = name.lower()
    name = re.sub(r"^iii_|^3-", "3", name)
    name = re.sub(r"^ii_|^2-", "2", name)
    name = re.sub(r"^i_|^1-", "1", name)
    key = re.sub(r"[^a-z0-9]", "", name)
    return _ALIASES.get(key, key)


_TAMIL_BY_KEY = {_book_key(book): book for book in TAMIL_BOOKS}


def tamil_book(slug: str) -> str:
    """Map a DailyVerses.net English book slug to tamil-bible.com's book parameter."""
    try:
        return _TAMIL_BY_KEY[_book_key(slug)]
    except KeyError as err:
        raise SourceError(f"No tamil-bible.com book for {slug!r}") from err


def parse_tamil(page: str, chapter: int, first: int, last: int) -> tuple[str, str]:
    """Return (Tamil reference, text) for verses first..last of a chapter page."""
    title = re.search(r"<title>\s*(.+?)\s+\d+\s+—", page, re.S)
    if not title:
        raise SourceError("tamil-bible.com page layout changed: book name not found")
    texts = []
    for number in range(first, last + 1):
        match = re.search(
            rf'<div class="verse-row" id="v{number}">.*?<div class="verse-tamil">(.*?)</div>',
            page,
            re.S,
        )
        if not match:
            raise SourceError(f"tamil-bible.com has no verse {chapter}:{number}")
        texts.append(clean(match.group(1)))
    verses = str(first) if first == last else f"{first}-{last}"
    return f"{html.unescape(title.group(1)).strip()} {chapter}:{verses}", " ".join(texts)


def german_reference(ref: str) -> str:
    """"3 Mose 20:26" -> "3. Mose 20,26", the usual German form."""
    return re.sub(r"^(\d) ", r"\1. ", ref).replace(":", ",")


def fetch_day(day: date) -> dict[str, Verse]:
    """Fetch the verse for a day in all three languages."""
    en_ref, en_path, en_text = parse_dailyverses(
        _get(f"{DAILYVERSES}/{day:%Y/%m/%d}/{ENGLISH_TRANSLATION}"), day, "", ENGLISH_TRANSLATION
    )
    de_ref, _, de_text = parse_dailyverses(
        _get(f"{DAILYVERSES}/de/{day:%Y/%m/%d}/{GERMAN_TRANSLATION}"), day, "/de", GERMAN_TRANSLATION
    )
    book, chapter, first, last = parse_path(en_path)
    ta_ref, ta_text = parse_tamil(
        _get(f"{TAMIL_BIBLE}/lookup.php?Book={tamil_book(book)}&Chapter={chapter}"),
        chapter,
        first,
        last,
    )
    return {
        "ta": Verse("ta", ta_ref, ta_text),
        "en": Verse("en", en_ref, en_text),
        "de": Verse("de", german_reference(de_ref), de_text),
    }
