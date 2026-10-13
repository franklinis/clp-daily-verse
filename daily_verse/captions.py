"""Post text for each platform, in Tamil, English and German.

Church details (services, address, links, hashtags) live in church.json at the
repository root, so wording can change without touching code.
"""

from __future__ import annotations

import json

from .render import ROOT

CHURCH = json.loads((ROOT / "church.json").read_text(encoding="utf-8"))
ORDER = ("ta", "en", "de")
CREDITS = "Bible: tamil-bible.com · King James Version · Lutherbibel 1912 · Verse selection: DailyVerses.net"
QUOTES = {"ta": ("“", "”"), "en": ("“", "”"), "de": ("„", "“")}
TRANSLATION = {"ta": "", "en": " (KJV)", "de": " (Lutherbibel 1912)"}

Verses = dict[str, dict[str, str]]


def _header(verses: Verses) -> list[str]:
    return [
        "இன்றைய வசனம் · Verse of the Day · Vers des Tages",
        "📖 " + " · ".join(verses[lang]["reference"] for lang in ORDER),
    ]


def _quoted(verses: Verses, lang: str) -> str:
    opening, closing = QUOTES[lang]
    return f"{opening}{verses[lang]['text']}{closing}"


def _invitation(website: str) -> list[str]:
    return [
        "🙏 " + " · ".join(CHURCH["invitation"][lang] for lang in ORDER),
        f"📍 {CHURCH['address']} · {website}",
        "💬 " + " · ".join(CHURCH["share"][lang] for lang in ("en", "de")),
    ]


def _hashtags(service: str) -> str:
    return " ".join(CHURCH["hashtags"][service])


INSTAGRAM_LIMIT = 2200


def carousel_text(verses: Verses, service: str) -> str:
    """Instagram / Facebook feed post: the verse in all three languages.

    If a long passage would pass Instagram's caption limit, German and then
    English are left to the slides.
    """
    # Instagram doesn't link URLs in captions, so show the short domain there.
    website = CHURCH["website"] if service == "facebook" else CHURCH["website"].removeprefix("https://")
    for shown in (ORDER, ("ta", "en"), ("ta",), ()):
        text = "\n".join([
            *_header(verses), "",
            *(line for lang in shown for line in (_quoted(verses, lang), "")),
            "Swipe ➜ தமிழ் · English · Deutsch", "",
            *_invitation(website), "",
            CREDITS, "",
            _hashtags(service),
        ])
        if len(text) <= INSTAGRAM_LIMIT:
            break
    return text


def reel_text(verses: Verses, service: str) -> str:
    """Instagram / Facebook Reel: shorter, the verse is in the video."""
    website = CHURCH["website"] if service == "facebook" else CHURCH["website"].removeprefix("https://")
    return "\n".join([*_header(verses), "", *_invitation(website), "", CREDITS, "", _hashtags(service)])


def youtube_title(verses: Verses) -> str:
    """Tamil first, as Tamil viewers search; YouTube allows 100 characters."""
    title = f"{verses['ta']['reference']} | இன்றைய வசனம் | Verse of the Day #shorts"
    if len(title) > 100:
        title = f"{verses['en']['reference']} | Verse of the Day #shorts"
    return title


def youtube_description(verses: Verses) -> str:
    """All three verses (searchable on YouTube), the church's schedule and links."""
    lines = ["இன்றைய வசனம் · Verse of the Day · Vers des Tages", ""]
    for lang in ORDER:
        lines += [verses[lang]["reference"] + TRANSLATION[lang], verses[lang]["text"], ""]
    lines += [f"{CHURCH['name']} · " + " · ".join(CHURCH["tagline"][lang] for lang in ORDER), ""]
    for item in CHURCH["schedule"]:
        lines += [f"🙏 {item['en']}", f"    {item['de']}", f"    {item['ta']}"]
    lines += [
        "",
        f"📍 {CHURCH['address']}",
        f"🔗 {CHURCH['website']}",
        f"👍 {CHURCH['facebook']}",
        f"📷 {CHURCH['instagram']}",
        "",
        CREDITS,
        "",
        _hashtags("youtube"),
    ]
    return "\n".join(lines)


def check() -> None:
    """Fail early if church.json is missing a language."""
    for key in ("tagline", "invitation", "share"):
        missing = set(ORDER) - set(CHURCH[key])
        if missing:
            raise ValueError(f"church.json {key} is missing {sorted(missing)}")
    for item in CHURCH["schedule"]:
        if set(ORDER) - set(item):
            raise ValueError(f"church.json schedule entry {item} needs ta, en and de")

