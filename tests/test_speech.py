"""Read-aloud: references as spoken, voices, SSML, timing and mixing (no Azure calls)."""

from datetime import date
import io
from pathlib import Path
import wave

import pytest

from daily_verse import speech, video


@pytest.mark.parametrize(
    ("lang", "reference", "spoken"),
    [
        ("en", "Leviticus 20:26", "Leviticus, chapter 20, verse 26."),
        ("en", "Psalm 23:1-2", "Psalm, chapter 23, verses 1 to 2."),
        ("de", "3. Mose 20,26", "Drittes Buch Mose, Kapitel 20, Vers 26."),
        ("de", "1. Korinther 13,4-7", "Erster Korinther, Kapitel 13, Verse 4 bis 7."),
        ("de", "Psalm 119,14", "Psalm, Kapitel 119, Vers 14."),
        ("ta", "லேவியராகமம் 20:26", "லேவியராகமம், 20 ஆம் அதிகாரம், 26 ஆம் வசனம்."),
        ("ta", "சங்கீதம் 23:1-2", "சங்கீதம், 23 ஆம் அதிகாரம், 1 முதல் 2 வரையிலான வசனங்கள்."),
        ("ta", "1 கொரிந்தியர் 8:6", "முதலாம் கொரிந்தியர், 8 ஆம் அதிகாரம், 6 ஆம் வசனம்."),
        ("ta", "I கொரிந்தியர் 8:6", "முதலாம் கொரிந்தியர், 8 ஆம் அதிகாரம், 6 ஆம் வசனம்."),
        ("ta", "2 இராஜாக்கள் 5:1", "இரண்டாம் இராஜாக்கள், 5 ஆம் அதிகாரம், 1 ஆம் வசனம்."),
        ("ta", "III யோவான் 1:2", "மூன்றாம் யோவான், 1 ஆம் அதிகாரம், 2 ஆம் வசனம்."),
    ],
)
def test_spoken_reference(lang: str, reference: str, spoken: str) -> None:
    assert speech.spoken_reference(lang, reference) == spoken


def test_voices_mix_genders_and_flip_daily() -> None:
    a, b = speech.voices_for(date(2026, 10, 14)), speech.voices_for(date(2026, 10, 15))
    assert {a["ta"], b["ta"]} == {"ta-IN-PallaviNeural", "ta-IN-ValluvarNeural"}
    for day in (a, b):  # neighbouring languages never share a gender
        genders = ["Pallavi" in day["ta"], "Sonia" in day["en"], "Katja" in day["de"]]
        assert genders[0] != genders[1] != genders[2]


def test_ssml_escapes_text_and_pauses_after_the_reference() -> None:
    document = speech.ssml("en", "en-GB-RyanNeural", "John 3:16", "Love & <grace>")
    assert 'xml:lang="en-GB"' in document and '<voice name="en-GB-RyanNeural">' in document
    assert 'John, chapter 3, verse 16.<break time="700ms"/>Love &amp; &lt;grace&gt;' in document
    assert '<prosody rate="-8%">' in document


def test_timing_gives_each_reading_room() -> None:
    seconds, starts = video.narrated_timing([4.0, 3.0, 5.0])
    assert seconds == pytest.approx([6.7, 6.5, 8.7])
    assert starts == pytest.approx([0.7, 7.4, 13.1])
    # Each reading (plus its pause) ends exactly when the next cross-fade begins: 5.9 s and 11.6 s.
    assert starts[0] + 4.0 + video.VOICE_TAIL == pytest.approx(seconds[0] - video.FADE)
    assert starts[1] + 3.0 + video.VOICE_TAIL == pytest.approx(seconds[0] + seconds[1] - 2 * video.FADE)


def _tone_wav(path: Path, seconds: float, rate: int = 24000) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x10\x27" * int(seconds * rate))  # constant non-zero samples
    return path


def test_combine_places_readings_at_their_start_times(tmp_path: Path) -> None:
    readings = [speech.Narration("ta", "v", _tone_wav(tmp_path / f"{i}.wav", 1.0), 1.0) for i in range(2)]
    out = speech.combine(readings, [0.5, 3.0], 5.0, tmp_path / "all.wav")
    with wave.open(str(out)) as wav:
        frames = wav.readframes(wav.getnframes())
        assert wav.getnframes() == 5 * 24000
    sample = lambda t: frames[int(t * 24000) * 2 : int(t * 24000) * 2 + 2]  # noqa: E731
    assert sample(0.2) == b"\x00\x00" and sample(1.0) == b"\x10\x27"
    assert sample(2.0) == b"\x00\x00" and sample(3.5) == b"\x10\x27"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_rest_fallback_posts_ssml_to_the_region(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "germanywestcentral")
    sent = []

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.headers, request.data.decode()))
        return _Response(_tone_wav(tmp_path / "tone.wav", 1.0).read_bytes())

    monkeypatch.setattr(speech.urllib.request, "urlopen", fake_urlopen)
    document = speech.ssml("de", "de-DE-KatjaNeural", "Johannes 3,16", "Also hat Gott")
    out = speech._synthesize_rest(document, tmp_path / "o.wav")
    url, headers, body = sent[0]
    assert url == "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"
    assert headers["X-microsoft-outputformat"] == speech.OUTPUT_FORMAT
    assert "Kapitel 3, Vers 16" in body and speech.wav_seconds(out) == 1.0


def test_narrate_reads_each_language_with_todays_voice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_synthesize(document, out):
        calls.append(document)
        return _tone_wav(out, 2.0), [speech.Word(0.1, 0.4, 5, "x")]

    monkeypatch.setattr(speech, "synthesize", fake_synthesize)
    verses = {
        "ta": {"reference": "யோவான் 3:16", "text": "தேவன்"},
        "en": {"reference": "John 3:16", "text": "For God"},
        "de": {"reference": "Johannes 3,16", "text": "Also hat Gott"},
    }
    readings = speech.narrate(verses, date(2026, 10, 14), tmp_path)
    assert [r.lang for r in readings] == ["ta", "en", "de"] and all(r.seconds == 2.0 for r in readings)
    assert readings[1].voice in calls[1] and readings[1].words and readings[1].document == calls[1]


def _reading(document: str, words: list[tuple[float, float, str]], seconds: float = 6.0) -> speech.Narration:
    """A narration whose words are found in `document` by their text."""
    found, cursor = [], document.index("<break")
    for start, end, text in words:
        cursor = document.index(text, cursor)
        found.append(speech.Word(start, end, cursor, text))
        cursor += len(text)
    return speech.Narration("en", "v", Path("x.wav"), seconds, tuple(found), document)


def test_word_times_follow_azure_offsets() -> None:
    document = speech.ssml("en", "en-GB-RyanNeural", "John 3:16", "For God so loved & the world")
    reading = _reading(document, [(2.0, 2.2, "For"), (2.3, 2.6, "God"), (2.7, 2.8, "so"), (2.9, 3.3, "loved"),
                                  (3.4, 3.6, "&amp;"), (3.7, 3.8, "the"), (3.9, 4.3, "world")])
    times = speech.word_times(reading, "For God so loved & the world")
    assert times == [(2.0, 2.2), (2.3, 2.6), (2.7, 2.8), (2.9, 3.3), (3.4, 3.6), (3.7, 3.8), (3.9, 4.3)]


def test_word_times_fill_words_azure_skipped() -> None:
    document = speech.ssml("en", "en-GB-RyanNeural", "John 3:16", "For God so loved")
    reading = _reading(document, [(2.0, 2.2, "For"), (2.3, 2.6, "God"), (2.9, 3.3, "loved")])
    assert speech.word_times(reading, "For God so loved")[2] == (2.6, 2.9)


def test_word_times_fall_back_to_even_spread() -> None:
    document = speech.ssml("ta", "ta-IN-PallaviNeural", "யோவான் 3:16", "தேவன் உலகத்தில் அன்பு")
    times = speech.word_times(speech.Narration("ta", "v", Path("x.wav"), 8.0, (), document), "தேவன் உலகத்தில் அன்பு")
    assert len(times) == 3 and times[0][0] > 0.7 and times[-1][1] <= 7.8 + 1e-9
    assert all(a[1] == pytest.approx(b[0]) for a, b in zip(times, times[1:], strict=False))


def test_highlight_timeline_lights_words_in_turn(tmp_path: Path) -> None:
    from PIL import Image

    looks = {}
    for mode, colour in (("dim", (60, 60, 60)), ("bright", (250, 250, 250)), ("accent", (200, 160, 120))):
        looks[mode] = tmp_path / f"{mode}.png"
        Image.new("RGB", (200, 100), colour).save(looks[mode])
    looks["boxes"] = [[10, 40, 30, 20], [60, 40, 30, 20]]
    listing = video.highlight_timeline(looks, [(1.0, 1.4), (1.5, 2.0)], 4.0, tmp_path / "frames")
    lines = listing.read_text().splitlines()
    durations = [float(line.split()[1]) for line in lines if line.startswith("duration")]
    assert durations == pytest.approx([1.0, 0.5, 0.8, 1.7]) and sum(durations) == pytest.approx(4.0)
    frames = sorted((tmp_path / "frames").glob("f*.png"))
    pixel = lambda i, x: Image.open(frames[i]).getpixel((x, 50))  # noqa: E731
    assert pixel(0, 25) == (60, 60, 60)                                   # before reading: dim
    assert pixel(1, 25) == (200, 160, 120) and pixel(1, 75) == (60, 60, 60)  # first word being read
    assert pixel(2, 25) == (250, 250, 250) and pixel(2, 75) == (200, 160, 120)
    assert pixel(3, 75) == (250, 250, 250)                                # all read
    assert lines[-1] == f"file '{frames[-1].name}'"


def test_video_with_voice_and_music(tmp_path: Path) -> None:
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    import subprocess

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    slides = []
    for i, colour in enumerate(("red", "green")):
        slide = tmp_path / f"{i}.png"
        subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=108x192",
                        "-frames:v", "1", str(slide)], check=True)
        slides.append(slide)
    seconds, starts = video.narrated_timing([1.0, 1.0])
    total = sum(seconds) - video.FADE
    readings = [speech.Narration("en", "v", _tone_wav(tmp_path / f"r{i}.wav", 1.0), 1.0) for i in range(2)]
    voice = speech.combine(readings, starts, total, tmp_path / "voice.wav")
    music = _tone_wav(tmp_path / "music.wav", total, rate=22050)
    out = video.make_video(slides, seconds, tmp_path / "o.mp4", size=(108, 192), music=music, narration=voice)
    assert imageio_ffmpeg.count_frames_and_secs(str(out))[1] == pytest.approx(total, abs=0.1)


def test_follow_along_video_encodes(tmp_path: Path) -> None:
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    from PIL import Image

    looks = {}
    for mode, colour in (("dim", (60, 60, 60)), ("bright", (250, 250, 250)), ("accent", (200, 160, 120))):
        looks[mode] = tmp_path / f"{mode}.png"
        Image.new("RGB", (108, 192), colour).save(looks[mode])
    looks["boxes"] = [[10, 80, 30, 20], [60, 80, 30, 20]]
    seconds, starts = video.narrated_timing([1.5])
    times = [(starts[0] + 0.2, starts[0] + 0.6), (starts[0] + 0.7, starts[0] + 1.3)]
    timeline = video.highlight_timeline(looks, times, seconds[0], tmp_path / "frames")
    voice = _tone_wav(tmp_path / "voice.wav", seconds[0])
    out = video.make_video([looks["bright"]], seconds, tmp_path / "o.mp4", size=(108, 192),
                           music=_tone_wav(tmp_path / "m.wav", seconds[0], 22050), narration=voice, timeline=timeline)
    assert imageio_ffmpeg.count_frames_and_secs(str(out))[1] == pytest.approx(seconds[0], abs=0.1)
