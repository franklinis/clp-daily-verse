"""Post text for each platform."""

from daily_verse import captions

VERSES = {
    "ta": {"reference": "லேவியராகமம் 20:26", "text": "கர்த்தராகிய நான் பரிசுத்தராயிருக்கிறபடியினாலே."},
    "en": {"reference": "Leviticus 20:26", "text": "And ye shall be holy unto me."},
    "de": {"reference": "3. Mose 20,26", "text": "Darum sollt ihr mir heilig sein."},
}
LONG = {lang: {"reference": v["reference"], "text": v["text"] * 40} for lang, v in VERSES.items()}


def test_church_details_are_complete() -> None:
    captions.check()
    assert captions.CHURCH["facebook"] == "https://www.facebook.com/christthelivingpetrachurch/"


def test_carousel_has_all_three_verses_and_german_wording() -> None:
    text = captions.carousel_text(VERSES, "instagram")
    assert "📖 லேவியராகமம் 20:26 · Leviticus 20:26 · 3. Mose 20,26" in text
    assert "“And ye shall be holy unto me.”" in text
    assert "„Darum sollt ihr mir heilig sein.“" in text
    assert "Gottesdienst sonntags 9:00 Uhr (auf Tamil)" in text
    assert "christ-livingpetra.de" in text and "https://" not in text
    assert "https://christ-livingpetra.de" in captions.carousel_text(VERSES, "facebook")


def test_instagram_limits() -> None:
    """2,200 characters and at most five hashtags, even for long verses."""
    for text in (captions.carousel_text(LONG, "instagram"), captions.reel_text(LONG, "instagram")):
        assert len(text) <= 2200
        assert text.count("#") <= 5


def test_reel_leaves_the_verse_to_the_video() -> None:
    text = captions.reel_text(VERSES, "instagram")
    assert "Leviticus 20:26" in text
    assert "And ye shall be holy" not in text


def test_youtube_title_and_description() -> None:
    title = captions.youtube_title(VERSES)
    assert title == "லேவியராகமம் 20:26 | இன்றைய வசனம் | Verse of the Day #shorts"
    assert len(title) <= 100
    description = captions.youtube_description(VERSES)
    assert "Leviticus 20:26 (KJV)\nAnd ye shall be holy unto me." in description
    assert "3. Mose 20,26 (Lutherbibel 1912)" in description
    assert "Kindergottesdienst" in description
    assert captions.CHURCH["facebook"] in description
    assert len(description) <= 5000


def test_long_passages_drop_german_then_english_from_the_caption() -> None:
    text = captions.carousel_text(LONG, "instagram")
    assert "Darum sollt" not in text
    assert "📖 லேவியராகமம் 20:26" in text
