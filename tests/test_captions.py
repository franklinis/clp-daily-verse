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
    texts = [captions.carousel_text(LONG, "instagram")]
    texts += [captions.language_reel_text(LONG, lang, "instagram") for lang in ("ta", "en", "de")]
    for text in texts:
        assert len(text) <= 2200
        assert text.count("#") <= 5


def test_language_reels_are_entirely_in_one_language() -> None:
    tamil = captions.language_reel_text(VERSES, "ta", "instagram")
    assert tamil.startswith("இன்றைய தேவ வார்த்தை\n📖 லேவியராகமம் 20:26")
    assert "கர்த்தராகிய நான்" in tamil and "And ye shall" not in tamil and "Darum" not in tamil
    assert "ஞாயிறு ஆராதனை காலை 9:00" in tamil and "#TamilBible" in tamil

    german = captions.language_reel_text(VERSES, "de", "facebook")
    assert german.startswith("Gottes Wort für heute\n📖 3. Mose 20,26")
    assert "\u201eDarum sollt ihr mir heilig sein.\u201c" in german
    assert "Gottesdienst sonntags 9:00 Uhr (auf Tamil)" in german
    assert "https://christ-livingpetra.de" in german and german.count("#") == 3


def test_language_youtube_title_and_description() -> None:
    assert captions.language_youtube_title(VERSES, "de") == "3. Mose 20,26 | Gottes Wort für heute #shorts"
    assert captions.language_youtube_title(VERSES, "ta") == "லேவியராகமம் 20:26 | இன்றைய தேவ வார்த்தை #shorts"
    description = captions.language_youtube_description(VERSES, "en")
    assert "Word of God for Today\n\nLeviticus 20:26\nAnd ye shall be holy unto me." in description
    assert "Sunday School (Tamil & English) · 9:45 AM" in description
    assert "Kindergottesdienst" not in description and "கர்த்தராகிய" not in description
    assert captions.CHURCH["facebook"] in description


def test_long_passages_drop_german_then_english_from_the_caption() -> None:
    text = captions.carousel_text(LONG, "instagram")
    assert "Darum sollt" not in text
    assert "📖 லேவியராகமம் 20:26" in text


def test_no_bible_or_source_credits_in_any_post() -> None:
    texts = [captions.carousel_text(VERSES, s) for s in ("instagram", "facebook")]
    texts += [captions.language_reel_text(VERSES, lang, s) for lang in ("ta", "en", "de") for s in ("instagram", "facebook")]
    texts += [captions.language_youtube_description(VERSES, lang) for lang in ("ta", "en", "de")]
    for text in texts:
        for credit in ("DailyVerses", "tamil-bible.com", "King James", "KJV", "Lutherbibel"):
            assert credit not in text
    assert texts[0].startswith("இன்றைய தேவ வார்த்தை · Word of God for Today · Gottes Wort für heute\n")
