"""Verse-matched backgrounds (no Azure calls)."""

import base64
from datetime import date
import io
import json
from pathlib import Path

import pytest

from daily_verse import imagery, sources
from daily_verse.render import build_html

VERSES = {
    "ta": {"reference": "யோவான் 4:14", "text": "நான் கொடுக்கும் தண்ணீரை"},
    "en": {"reference": "John 4:14", "text": "But whosoever drinketh of the water that I shall give him shall never thirst"},
    "de": {"reference": "Johannes 4,14", "text": "Wer aber von dem Wasser trinken wird"},
}
AZURE = {"BACKGROUNDS": "ai", "AZURE_OPENAI_KEY": "k", "AZURE_OPENAI_ENDPOINT": "https://res.openai.azure.com/",
         "AZURE_IMAGE_DEPLOYMENT": "gpt-image-2"}


def _jpeg(colour: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 112), colour).save(buffer, "JPEG")
    return buffer.getvalue()


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_topics_come_from_the_dailyverses_tags() -> None:
    page = ('<div class="vr"><a href="/john/4/14/kjv" class="vc">John 4:14</a> '
            '<a href="/eternal-life/kjv" class="t">eternal life</a> <a href="/joy/kjv" class="t">joy</a></div>')
    assert sources.parse_topics(page) == ["eternal life", "joy"]
    assert sources.parse_topics("<p>no tags</p>") == []


def test_prompt_carries_the_verse_topics_and_rules() -> None:
    text = imagery.prompt(VERSES, ["eternal life", "water"])
    assert 'Verse: "But whosoever drinketh of the water' in text and "(John 4:14)" in text
    assert "Themes: eternal life, water." in text
    assert "people may appear" in text and "never as close-up faces" in text  # church.json image_people
    assert "no text" in text and "no depictions of God, Jesus, angels or named Bible characters" in text
    assert "middle third calm" in text


def test_generate_calls_azure_and_saves_the_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in AZURE.items():
        monkeypatch.setenv(name, value)
    sent = []

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.headers, json.loads(request.data)))
        return _Response(json.dumps({"data": [{"b64_json": base64.b64encode(_jpeg((10, 20, 30))).decode()}]}).encode())

    monkeypatch.setattr(imagery.urllib.request, "urlopen", fake_urlopen)
    out = imagery.generate("a spring", tmp_path / "scene.jpg")
    url, headers, body = sent[0]
    assert url == "https://res.openai.azure.com/openai/v1/images/generations?api-version=preview"
    assert headers["Api-key"] == "k"
    assert body["model"] == "gpt-image-2" and body["size"] == "1088x1920" and body["output_format"] == "jpeg"
    assert out.read_bytes()[:2] == b"\xff\xd8"


def test_refused_prompts_fall_back_to_mountains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in AZURE.items():
        monkeypatch.setenv(name, value)

    def refuse(request, timeout):
        raise imagery.urllib.error.HTTPError(request.full_url, 400, "Bad Request", {},
                                             io.BytesIO(b'{"error":{"code":"content_policy_violation"}}'))

    monkeypatch.setattr(imagery.urllib.request, "urlopen", refuse)
    assert imagery.scene_for(date(2026, 10, 15), VERSES, [], tmp_path) is None


def test_saved_scene_is_reused_and_switch_is_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = date(2026, 10, 15)
    monkeypatch.delenv("BACKGROUNDS", raising=False)
    assert imagery.scene_for(day, VERSES, [], tmp_path) is None  # switched off: mountains
    saved = tmp_path / imagery.scene_name(day)
    saved.parent.mkdir(parents=True)
    saved.write_bytes(_jpeg((10, 20, 30)))
    assert imagery.scene_for(day, VERSES, [], tmp_path) == saved  # already made: no new request


def test_brighter_images_get_a_darker_overlay(tmp_path: Path) -> None:
    dark, bright = tmp_path / "dark.jpg", tmp_path / "bright.jpg"
    dark.write_bytes(_jpeg((20, 25, 30)))
    bright.write_bytes(_jpeg((235, 230, 220)))
    assert imagery.shade(str(dark)) == 0.32
    assert imagery.shade(str(bright)) > 0.7


def test_slide_uses_the_scene_instead_of_mountains(tmp_path: Path) -> None:
    scene = tmp_path / "scene.jpg"
    scene.write_bytes(_jpeg((40, 60, 80)))
    verse = sources.Verse("en", "John 4:14", "Living water")
    with_scene = build_html(verse, date(2026, 10, 15), "video", scene)
    assert f'<img class="bg" src="{scene.resolve().as_uri()}"' in with_scene and "<svg" not in with_scene
    assert "<svg" in build_html(verse, date(2026, 10, 15), "video")


def test_art_direction_varies_by_day_and_follows_feasts() -> None:
    year = [date(2027, 1, 1) + __import__("datetime").timedelta(days=i) for i in range(60)]
    directions = {imagery.art_direction(d) for d in year}
    assert len(directions) > 40  # rarely the same light, season and colour twice
    assert imagery.art_direction(date(2026, 12, 25)).startswith("a quiet winter night under one bright star")
    assert imagery.art_direction(date(2026, 10, 15)) == imagery.art_direction(date(2026, 10, 15))
    assert "Art direction for today:" in imagery.prompt(VERSES, [], date(2026, 10, 15))


def test_every_palette_has_a_colour_mood() -> None:
    from daily_verse import background

    assert {p.name for p in background.SUNDAY + background.WEEKDAY} <= set(imagery.MOODS)
