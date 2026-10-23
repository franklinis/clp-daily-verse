"""Verse-matched background images from Azure (Microsoft Foundry) gpt-image models.

Once per day, the English verse and its DailyVerses.net topics are turned into
a prompt for a calm nature or still-life scene that reflects the verse, with
strict rules (no people, no text, no depictions of God). The image is saved
next to the day's slides and reused by every language and format; if Azure
refuses or fails, the day falls back to the generated mountain background.

Switched on by BACKGROUNDS=ai, with AZURE_OPENAI_KEY (secret),
AZURE_OPENAI_ENDPOINT (e.g. https://<resource>.openai.azure.com) and
AZURE_IMAGE_DEPLOYMENT (e.g. gpt-image-2). The style is set in church.json.
"""

from __future__ import annotations

import base64
from datetime import date
from functools import lru_cache
import json
import os
from pathlib import Path
import random
import urllib.error
import urllib.request

from .captions import CHURCH

SIZE = "1088x1920"  # gpt-image-2 needs multiples of 16; slides crop to 1080 wide
QUALITY = "medium"
NO_PEOPLE = "no people or human figures, no faces or hands, "
# With church.json "image_people": people can be part of the scene, but never the focus of attention:
# faces under the verse hurt readability, and close-up AI faces and hands are where generated images look wrong.
PEOPLE = (
    "people may appear when they fit the verse (for example a shepherd with sheep, a family at a table, "
    "someone walking a path, a person praying or working in a field), as ordinary present-day people who "
    "look like the Tamil community the church serves; show them small or at a distance, from behind, in "
    "silhouette or turned away, never as close-up faces or hands, and never in the middle third; "
)
RULES = (
    "Rules: " + (PEOPLE if CHURCH.get("image_people") else NO_PEOPLE) + "no text, letters, numbers, signs or logos, "
    "no depictions of God, Jesus, angels or named Bible characters, no crosses or other religious symbols, "
    "no buildings in focus. "
    "Portrait composition. Keep the middle third calm, soft and low in detail, because white text will be "
    "placed there; use a moderately low-key exposure (not bright or washed out, especially in the middle); "
    "put the main subject near the bottom or the edges."
)


class ImageError(Exception):
    """Azure did not return an image (refused, filtered or unreachable)."""


def enabled() -> bool:
    return os.environ.get("BACKGROUNDS", "").lower() == "ai" and all(
        os.environ.get(name) for name in ("AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_IMAGE_DEPLOYMENT")
    )


LIGHT = [
    "soft sunrise light", "clear fresh morning light", "bright midday sun under a blue sky", "warm golden afternoon",
    "glowing sunset", "deep blue hour just after sunset", "light breaking through clouds after rain",
    "soft overcast light", "a calm night lit by the moon and stars",
]
SEASONS = [
    "spring, with fresh green leaves and blossom", "lush high summer", "autumn, with red and gold leaves",
    "winter, with snow and frost", "the dry season, with warm earth tones",
]
# A colour mood for each palette in background.py, so photos and generated days feel like one series.
MOODS = {
    "dawn": "cool dawn blues", "ocean": "deep ocean blues", "indigo": "indigo and violet", "storm": "stormy blue-greys",
    "arctic": "icy blues and white", "harbour": "harbour blues with warm highlights", "dusk": "dusky purples",
    "lavender": "soft lavender", "plum": "deep plum", "rose dusk": "rose and mauve", "wine": "deep wine reds",
    "orchid": "orchid purples and peach", "earth": "warm earth browns", "terracotta": "terracotta and clay",
    "gold": "rich golds", "amber": "amber and honey", "sunrise": "sunrise pinks and oranges",
    "sunset": "sunset oranges and magentas", "copper": "copper and bronze", "desert": "sand and warm stone",
    "olive": "olive and sage greens", "teal": "teal and turquoise", "lagoon": "lagoon greens and blues",
    "slate": "slate greys", "charcoal": "charcoal and silver", "mist": "misty grey-greens",
    "midnight": "midnight blue", "aurora": "aurora greens", "starlight": "starry night blues",
    "violet night": "violet night", "petra": "deep forest greens", "emerald": "emerald greens",
    "forest": "pine greens", "sage": "sage greens",
}
FEAST_DIRECTION = {
    "christmas": "a quiet winter night under one bright star", "new year": "the first light of a new dawn",
    "good friday": "a sombre, still, overcast evening", "easter": "a radiant sunrise",
    "pentecost": "warm light and wind moving through the scene",
}


def art_direction(day: date) -> str:
    """Today's light, season and colour mood, so a year of images doesn't all look the same."""
    from .background import feast, palette_for

    rng = random.Random(day.toordinal() * 31)
    mood = MOODS.get(palette_for(day).name, "natural colours")
    if name := feast(day):
        return f"{FEAST_DIRECTION[name]}; colour mood: {mood}"
    return f"{rng.choice(LIGHT)}; {rng.choice(SEASONS)}; colour mood: {mood}"


def prompt(verses: dict[str, dict[str, str]], topics: list[str], day: date | None = None) -> str:
    """Describe the scene to paint, from the English verse, its topics and today's art direction."""
    english = verses["en"]
    themes = f" Themes: {', '.join(topics)}." if topics else ""
    direction = f"Art direction for today: {art_direction(day)}.\n" if day else ""
    return (
        "Create a background image for a daily Bible verse post.\n"
        f'Verse: "{english["text"]}" ({english["reference"]}).{themes}\n'
        "Choose one clear, specific image that captures this verse's meaning, for example flowing water, "
        "a path, a harvest field, a lamp, bread, a rock, a vine, a shepherd's meadow or a sky full of stars. "
        "If the verse names or implies a setting (a field, water, a building, sheep, a harvest), use it; "
        "otherwise vary the setting (forest, mountains, coast, desert, meadow, garden, river, sky). "
        "Avoid a generic misty landscape.\n"
        f"{direction}"
        f"Style: {CHURCH.get('image_style', 'cinematic nature photography')}.\n"
        f"{RULES}"
    )


def generate(text: str, out: Path) -> Path:
    """Ask Azure for one portrait image and save it as a JPEG at `out`."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].strip().rstrip("/")
    body = {
        "prompt": text,
        "model": os.environ["AZURE_IMAGE_DEPLOYMENT"].strip(),
        "size": SIZE,
        "quality": QUALITY,
        "n": 1,
        "output_format": "jpeg",
        "output_compression": 90,
    }
    request = urllib.request.Request(
        f"{endpoint}/openai/v1/images/generations?api-version=preview",
        data=json.dumps(body).encode(),
        headers={"api-key": os.environ["AZURE_OPENAI_KEY"].strip(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        raise ImageError(f"Azure image generation returned HTTP {err.code}: {detail}") from err
    except OSError as err:
        raise ImageError(f"Azure image generation unreachable: {err}") from err
    if usage := data.get("usage"):  # for cost tracking in the run log
        print(f"Image tokens: {json.dumps(usage)}")
    try:
        image = base64.b64decode(data["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise ImageError(f"Unexpected response from Azure: {str(data)[:200]}") from err
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    return out


def scene_name(day: date) -> str:
    return f"{day:%Y/%m/%d}-scene.jpg"


def scene_for(day: date, verses: dict[str, dict[str, str]], topics: list[str], media: Path) -> Path | None:
    """The day's background: reuse a saved one, otherwise generate it; None means use the mountains."""
    path = media / scene_name(day)
    if path.exists():
        return path
    if not enabled():
        return None
    try:
        return generate(prompt(verses, topics, day), path)
    except ImageError as err:
        print(f"::warning::{day}: no AI background ({err}); using the mountain background")
        return None


@lru_cache(maxsize=32)
def shade(path: str) -> float:
    """How dark the overlay must be for white text, from the brightness of the image's middle."""
    from PIL import Image, ImageStat

    image = Image.open(path).convert("L")
    width, height = image.size
    middle = image.crop((int(width * 0.1), int(height * 0.25), int(width * 0.9), int(height * 0.75)))
    brightness = ImageStat.Stat(middle.resize((64, 64))).mean[0] / 255
    return round(min(0.72, max(0.32, 0.18 + brightness * 0.75)), 2)
