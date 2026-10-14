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
import urllib.error
import urllib.request

from .captions import CHURCH

SIZE = "1088x1920"  # gpt-image-2 needs multiples of 16; slides crop to 1080 wide
QUALITY = "medium"
RULES = (
    "Rules: no people or human figures, no faces or hands, no text, letters, numbers, signs or logos, "
    "no depictions of God, Jesus or angels, no crosses or other religious symbols, no buildings in focus. "
    "Portrait composition. Keep the middle third calm, soft and low in detail, because white text will be "
    "placed there; slightly darker tones overall; put the main subject near the bottom or the edges."
)


class ImageError(Exception):
    """Azure did not return an image (refused, filtered or unreachable)."""


def enabled() -> bool:
    return os.environ.get("BACKGROUNDS", "").lower() == "ai" and all(
        os.environ.get(name) for name in ("AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_IMAGE_DEPLOYMENT")
    )


def prompt(verses: dict[str, dict[str, str]], topics: list[str]) -> str:
    """Describe the scene to paint, from the English verse and its topics."""
    english = verses["en"]
    themes = f" Themes: {', '.join(topics)}." if topics else ""
    return (
        "Create a background image for a daily Bible verse post.\n"
        f'Verse: "{english["text"]}" ({english["reference"]}).{themes}\n'
        "Show a natural landscape or a simple still-life scene whose imagery reflects the meaning of this "
        "verse, for example water, light, paths, fields, sky, trees, mountains, rocks, a lamp or bread, "
        "chosen to fit this particular verse.\n"
        f"Style: {CHURCH.get('image_style', 'a calm, softly lit nature photograph')}.\n"
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
        return generate(prompt(verses, topics), path)
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
