"""Pick verses from a Microsoft Teams channel.

Someone @mentions the "DailyVerse" outgoing webhook in a church channel:

    @DailyVerse 20.10 Psalm 23:1
    @DailyVerse 21.10 Römer 8,28 theme: hope, trust
    @DailyVerse list            (upcoming picks)
    @DailyVerse clear 20.10     (back to DailyVerses.net)

An Azure Logic App passes the message on to the "Set verse" workflow (see
teams/logic-app.json), which checks it, saves custom-verses.csv and posts the
result back to the channel through a Teams Workflows webhook (TEAMS_WEBHOOK_URL).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import html
import json
import re
import urllib.request

MONTHS = {
    "jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2, "mar": 3, "marz": 3,
    "march": 3, "apr": 4, "april": 4, "may": 5, "mai": 5, "jun": 6, "june": 6, "juni": 6, "jul": 7,
    "july": 7, "juli": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "okt": 10, "october": 10, "oktober": 10, "nov": 11, "november": 11, "dec": 12, "dez": 12,
    "december": 12, "dezember": 12,
}
WEEKDAYS = {
    "monday": 0, "montag": 0, "mon": 0, "tuesday": 1, "dienstag": 1, "tue": 1, "wednesday": 2,
    "mittwoch": 2, "wed": 2, "thursday": 3, "donnerstag": 3, "thu": 3, "friday": 4, "freitag": 4,
    "fri": 4, "saturday": 5, "samstag": 5, "sat": 5, "sunday": 6, "sonntag": 6, "sun": 6,
}
HELP = (
    "Send one line per day: the date, then the verse.\n\n"
    "- `20.10 Psalm 23:1`\n"
    "- `21.10 Römer 8,28 theme: hope, trust` (theme words steer the background)\n"
    "- `list` shows the verses you've picked\n"
    "- `clear 20.10` gives the day back to DailyVerses.net\n\n"
    "A colon means English verse numbers (Psalm 51:10), a comma German ones (Psalm 51,12). "
    "Pick a verse at least 3 days ahead to have it in Buffer for review in time; "
    "you can change a day until you approve its posts in Buffer."
)


class MessageError(Exception):
    """A line of the message could not be understood."""


@dataclass(frozen=True)
class Command:
    kind: str  # "set", "clear", "list" or "help"
    line: str
    day: date | None = None
    reference: str = ""
    theme: str = ""


def message_lines(text: str) -> list[str]:
    """The lines of a Teams message, without the @mention and HTML."""
    text = re.sub(r"<at>.*?</at>", " ", text or "", flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _year(day_month: tuple[int, int], year: str | None, today: date) -> date:
    day, month = day_month
    if year:
        value = int(year)
        return date(value + 2000 if value < 100 else value, month, day)
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def parse_date(text: str, today: date) -> tuple[date, str]:
    """Read a date at the start of `text`; returns the date and the rest of the line."""
    lowered = text.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u")
    try:
        if match := re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\b", lowered):
            day = date(int(match[1]), int(match[2]), int(match[3]))
        elif match := re.match(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2})(?!\d))?\.?", lowered):
            day = _year((int(match[1]), int(match[2])), match[3], today)
        elif (match := re.match(r"(\d{1,2})\.?\s*([a-z]+)\.?(?:\s+(\d{4}))?\b", lowered)) and match[2] in MONTHS:
            day = _year((int(match[1]), MONTHS[match[2]]), match[3], today)
        elif (match := re.match(r"([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?\b", lowered)) \
                and match[1] in MONTHS:
            day = _year((int(match[2]), MONTHS[match[1]]), match[3], today)
        elif match := re.match(r"(tomorrow|morgen|ubermorgen)\b", lowered):
            day = today + timedelta(days=2 if match[1] == "ubermorgen" else 1)
        elif (match := re.match(r"([a-z]+)\b\.?", lowered)) and match[1] in WEEKDAYS:
            day = today + timedelta(days=(WEEKDAYS[match[1]] - today.weekday() - 1) % 7 + 1)
        else:
            raise MessageError(f"Start the line with a date, e.g. “20.10 Psalm 23:1” (got “{text}”)")
    except ValueError as err:
        raise MessageError(f"That date doesn't exist: “{text}”") from err
    rest = text[match.end():].strip().lstrip(":-–—=→ ").strip()
    return day, rest


def parse_line(line: str, today: date) -> Command:
    words = line.lower().split()
    if words[0] in {"help", "hilfe", "?"}:
        return Command("help", line)
    if words[0] in {"list", "liste", "show"}:
        return Command("list", line)
    if words[0] in {"clear", "remove", "delete", "loschen", "löschen", "entfernen"}:
        day, _ = parse_date(line.split(None, 1)[1] if len(words) > 1 else "", today)
        return Command("clear", line, day)
    day, rest = parse_date(line, today)
    if not rest:
        raise MessageError(f"Add the verse after the date, e.g. “{day:%d.%m} Psalm 23:1”")
    split = re.search(r"\s*(?:\||\b(?:theme|thema)\s*:)\s*", rest, re.I)
    reference, theme = (rest[:split.start()], rest[split.end():]) if split else (rest, "")
    return Command("set", line, day, reference.strip(), theme.strip().strip(",;"))


def parse_message(text: str, today: date) -> list[Command | MessageError]:
    """Every line as a command, or the error explaining why it couldn't be read."""
    lines = message_lines(text)
    if not lines:
        return [Command("help", "")]
    results: list[Command | MessageError] = []
    for line in lines:
        try:
            results.append(parse_line(line, today))
        except MessageError as err:
            results.append(err)
    return results


# Cards posted back to the channel.


def short_date(day: date) -> str:
    """"Tue 20 Oct"."""
    return f"{day:%a} {day.day} {day:%b}"


def _text(text: str, **style: object) -> dict:
    return {"type": "TextBlock", "text": text, "wrap": True, **style}


def card(body: list[dict], actions: list[dict] | None = None) -> dict:
    content = {"type": "AdaptiveCard", "version": "1.4", "body": body,
               "$schema": "http://adaptivecards.io/schemas/adaptive-card.json"}
    if actions:
        content["actions"] = actions
    return {"type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": content}]}


def results_card(results: list[dict]) -> dict:
    """The answer to a message: one block per line."""
    body: list[dict] = []
    for result in results:
        if body:
            body.append({"type": "TextBlock", "text": " ", "separator": True, "spacing": "Medium"})
        body.append(_text(result["title"], weight="Bolder", size="Medium"))
        if result.get("verses"):
            for lang in ("ta", "en", "de"):
                verse = result["verses"][lang]
                body.append(_text(f"**{verse['reference']}** {verse['text']}", spacing="Small"))
        if result.get("theme"):
            body.append(_text(f"Theme: {result['theme']}", isSubtle=True, spacing="Small"))
        if result.get("message"):
            body.append(_text(result["message"], isSubtle=not result.get("error"), spacing="Small",
                              color="Attention" if result.get("error") else "Default"))
    return card(body)


def ready_card(day: date, reference: str, image_url: str, posts: int, updated: bool) -> dict:
    """A custom day (or a changed day) is in Buffer, waiting for approval."""
    what = "updated with the new verse" if updated else "ready"
    return card(
        [
            _text(f"📅 {short_date(day)}: {reference}", weight="Bolder", size="Medium"),
            {"type": "Image", "url": image_url, "size": "Large", "altText": reference},
            _text(f"{posts} posts are {what} in Buffer as drafts. Approve them before 07:00 on {short_date(day)}."),
        ],
        [{"type": "Action.OpenUrl", "title": "Open Buffer", "url": "https://publish.buffer.com"}],
    )


def post(url: str, message: dict) -> None:
    request = urllib.request.Request(
        url, data=json.dumps(message).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30):
        pass
