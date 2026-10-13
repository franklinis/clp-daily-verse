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


def test_narrate_calls_azure_once_per_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westeurope")
    buffer = io.BytesIO()
    _tone_wav(tmp_path / "tone.wav", 2.0)
    sent = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.data.decode()))
        return Response((tmp_path / "tone.wav").read_bytes())

    monkeypatch.setattr(speech.urllib.request, "urlopen", fake_urlopen)
    verses = {
        "ta": {"reference": "யோவான் 3:16", "text": "தேவன்"},
        "en": {"reference": "John 3:16", "text": "For God"},
        "de": {"reference": "Johannes 3,16", "text": "Also hat Gott"},
    }
    readings = speech.narrate(verses, date(2026, 10, 14), tmp_path)
    assert [r.lang for r in readings] == ["ta", "en", "de"] and all(r.seconds == 2.0 for r in readings)
    assert all(url == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1" for url, _ in sent)
    assert "Kapitel 3, Vers 16" in sent[2][1]
    del buffer


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
