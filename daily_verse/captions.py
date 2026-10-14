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


def credits(text: str, selection: bool = True) -> str:
    """The credit line; without "Verse selection: DailyVerses.net" on days the church picked the verse."""
    return text if selection else " · ".join(part for part in text.split(" · ") if "DailyVerses" not in part)


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


def carousel_text(verses: Verses, service: str, selection: bool = True) -> str:
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
            credits(CREDITS, selection), "",
            _hashtags(service),
        ])
        if len(text) <= INSTAGRAM_LIMIT:
            break
    return text


# Single-language videos: one Reel / Short per language, entirely in that language.


def _website(service: str) -> str:
    return CHURCH["website"] if service == "facebook" else CHURCH["website"].removeprefix("https://")


def language_reel_text(verses: Verses, lang: str, service: str, selection: bool = True) -> str:
    """Instagram / Facebook Reel for one language: verse, invitation, credits, hashtags."""
    tags = CHURCH["language_hashtags"][lang][: 3 if service == "facebook" else 5]
    return "\n".join([
        CHURCH["label"][lang],
        f"📖 {verses[lang]['reference']}", "",
        _quoted(verses, lang), "",
        f"🙏 {CHURCH['invitation'][lang]}",
        f"📍 {CHURCH['address']} · {_website(service)}",
        f"💬 {CHURCH['share'][lang]}", "",
        credits(CHURCH["credits"][lang], selection), "",
        " ".join(tags),
    ])


def language_youtube_title(verses: Verses, lang: str) -> str:
    """e.g. "Psalm 119,14 | Vers des Tages #shorts" (YouTube allows 100 characters)."""
    title = f"{verses[lang]['reference']} | {CHURCH['label'][lang]} #shorts"
    return title if len(title) <= 100 else f"{CHURCH['label'][lang]} #shorts"


def language_youtube_description(verses: Verses, lang: str, selection: bool = True) -> str:
    """The verse, the church's schedule and links, all in one language."""
    lines = [
        CHURCH["label"][lang], "",
        verses[lang]["reference"] + TRANSLATION[lang], verses[lang]["text"], "",
        f"{CHURCH['name']} · {CHURCH['tagline'][lang]}", "",
        *(f"🙏 {item[lang]}" for item in CHURCH["schedule"]), "",
        f"📍 {CHURCH['address']}",
        f"🔗 {CHURCH['website']}",
        f"👍 {CHURCH['facebook']}",
        f"📷 {CHURCH['instagram']}", "",
        credits(CHURCH["credits"][lang], selection), "",
        " ".join(CHURCH["language_hashtags"][lang][:3]),
    ]
    return "\n".join(lines)


def check() -> None:
    """Fail early if church.json is missing a language."""
    for key in ("tagline", "label", "invitation", "share", "credits", "language_hashtags", "voices"):
        missing = set(ORDER) - set(CHURCH[key])
        if missing:
            raise ValueError(f"church.json {key} is missing {sorted(missing)}")
    for item in CHURCH["schedule"]:
        if set(ORDER) - set(item):
            raise ValueError(f"church.json schedule entry {item} needs ta, en and de")

